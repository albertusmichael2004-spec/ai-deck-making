from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from evidence.extraction import extract
from evidence.graph import EvidenceGraph
from evidence.calculation import calculate,validate_units
from ir.validation import validate
from security.files import FileRegistry
from security.paths import PathPolicy
from state.errors import StudioError, ErrorCode
from state.io import read_json, read_yaml, write_json, sha256, native_path
from state.locking import FileLock


def identity(prefix, value):
    return prefix + "_" + uuid5(NAMESPACE_URL, value).hex


class EvidenceStore:
    """Project evidence state, with immutable source versions and explicit refresh."""
    def __init__(self, repository: Path, project, read_roots=None):
        self.repository, self.project = repository, project
        self.path = project.path / "state/evidence_graph.json"
        policy = PathPolicy(read_roots or [repository], [project.path / "input/sources"])
        self.registry = FileRegistry(policy, read_yaml(repository / "config/security/files.yaml"))

    def load(self):
        graph = EvidenceGraph(read_json(self.path) if self.path.exists() else None)
        validate(self.repository, "evidence_graph", graph.value)
        for source in graph.value["sources"].values():
            for version in [source,*source.get("previous_versions",[])]:
                path=self.project.policy.check(Path(version["materialized_path"]))
                if not path.is_file() or sha256(path)!=version["sha256"]:
                    raise StudioError(ErrorCode.SOURCE_CONFLICT,"Immutable source version is missing or changed")
        for node in graph.value["nodes"].values():
            if any(key not in graph.value["nodes"] for key in node.get("supported_by",[])):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Stored lineage has unresolved dependencies")
            if node["type"]=="calculated_fact" and set(node["variables"].values()) != set(node["supported_by"]):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Calculation variables do not match declared dependencies")
            if set(graph.value["dependencies"].get(node["evidence_id"],[])) != set(node.get("supported_by",[])):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Stored dependency graph differs from evidence lineage")
        graph.dependencies.order()
        return graph

    def save(self, graph):
        validate(self.repository, "evidence_graph", graph.value)
        self.project.policy.check(self.path, write=True)
        write_json(self.path, graph.value)
        write_json(self.project.path / "state/data_bindings.json", graph.value["bindings"])
        write_json(self.project.path / "state/dependency_graph.json", graph.value["dependencies"])

    def ingest(self, source: Path, *, units=None, source_date=None, data_period=None):
        with FileLock(self.project.policy.check(self.project.path / "work/evidence.lock",write=True)):
            return self._ingest(source, units, source_date, data_period)

    def _ingest(self, source, units, source_date, data_period):
        inspected=self.registry.inspect(source,"supporting_source")
        logical=str(self.registry.policy.check(source))
        source_id=identity("src",logical)
        graph=self.load();old=graph.value["sources"].get(source_id)
        context={"units":units or {},"source_date":source_date,"data_period":data_period}
        if old and old["sha256"]==inspected["sha256"] and old.get("ingestion_context")==context:
            return {"source_id":source_id,"status":"unchanged","evidence_ids":old["evidence_ids"],"affected":[]}
        destination=self.project.path/"input/sources"/source_id/inspected["sha256"]/source.name
        if destination.exists():
            if sha256(destination)!=inspected["sha256"]:
                raise StudioError(ErrorCode.SOURCE_CONFLICT,"Immutable input version was modified")
        else:self.registry.materialize(source,destination,"supporting_source")
        extraction=extract(destination)
        now=datetime.now(timezone.utc).isoformat()
        version={**inspected,"source_id":source_id,"original_path":logical,"materialized_path":str(destination),"source_date":source_date,"retrieved_at":now,"data_period":data_period,"last_refresh":now,"ingestion_context":context,"limitations":extraction["limitations"],"evidence_ids":[],"previous_versions":[*(old or {}).get("previous_versions",[]),*([{"sha256":old["sha256"],"materialized_path":old["materialized_path"],"retrieved_at":old["retrieved_at"]}] if old and old["sha256"]!=inspected["sha256"] else [])]}
        graph.value["sources"][source_id]=version
        version.update(extraction.get("source_metadata",{}))
        changed=[]
        records={}
        for record in extraction["records"]:
            identifier=identity("ev",source_id+":"+record["locator"])
            unit=(units or {}).get(record.get("column",record.get("sheet","default")),(units or {}).get("default",{"label":"unspecified"}))
            node={"evidence_id":identifier,"type":"raw_fact","source_id":source_id,"source_sha256":inspected["sha256"],"locator":record["locator"],"value":record["value"],"unit":unit,"confidence":1,"assumptions":[],"status":"unverified" if record.get("formula") or record.get("error") else "current","freshness":{"source_date":source_date,"retrieved_at":now,"data_period":data_period,"last_refresh":now},"extraction":record}
            prior=graph.value["nodes"].get(identifier)
            if prior is None:graph.register(node);changed.append(identifier)
            else:
                if any(prior.get(key)!=node.get(key) for key in ["value","unit","status"]) or any(prior.get("freshness",{}).get(key)!=node["freshness"][key] for key in ["source_date","data_period"]):changed.append(identifier)
                graph.value["nodes"][identifier]=node
            version["evidence_ids"].append(identifier);records[identifier]=node
        for identifier in (old or {}).get("evidence_ids",[]):
            if identifier not in records:
                graph.value["nodes"][identifier]["status"]="missing"
                changed.append(identifier)
        affected=graph.dependencies.affected(changed)
        for identifier in graph.dependencies.order():
            node=graph.value["nodes"].get(identifier)
            if identifier not in affected or node is None or node["type"]=="raw_fact":continue
            if node["type"]=="calculated_fact":
                inputs={k:graph.resolve(v) for k,v in node["variables"].items()}
                if any(value["status"]!="current" for value in inputs.values()):node["status"]="stale"
                else:
                    try:validate_units(inputs,node["unit"])
                    except StudioError:
                        node["status"]="stale"
                        continue
                    node.setdefault("calculation_history",[]).append({"value":node["value"],"input_snapshot":node["input_snapshot"]})
                    try:node["value"]=calculate(node["formula"],{k:v["value"] for k,v in inputs.items()},{k:v["unit"] for k,v in inputs.items()},node["unit"])
                    except StudioError:
                        node["status"]="stale"
                        continue
                    node["status"]="current"
                    node["input_snapshot"]={key:{"evidence_id":value["evidence_id"],"value":value["value"],"unit":value["unit"],"source_sha256":value.get("source_sha256")} for key,value in inputs.items()}
            else:node["status"]="stale"
        self.save(graph)
        return {"source_id":source_id,"status":"refreshed" if old else "ingested","evidence_ids":version["evidence_ids"],"affected":sorted(affected),"limitations":extraction["limitations"]}

    def refresh(self, source_id):
        graph=self.load()
        source=graph.value["sources"].get(source_id)
        if source is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Source not registered")
        units=source["ingestion_context"]["units"]
        return self.ingest(Path(source["original_path"]),units=units,source_date=source["source_date"],data_period=source["data_period"])
