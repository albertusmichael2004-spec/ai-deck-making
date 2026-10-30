"""Manual reference ingestion; originals are authoritative, indexes rebuildable."""
import hashlib
import shutil
import re
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

from evidence.store import identity
from presentation.backends.ooxml import OOXMLBackend
from references.fingerprints import slide_fingerprint
from references.metadata import describe
from references.ranking import rank
from security.files import FileRegistry
from security.paths import PathPolicy
from state.errors import StudioError,ErrorCode
from state.io import read_json,read_yaml,write_json,sha256,fingerprint,native_path,logical_path
from state.locking import FileLock
from ir.validation import validate


class ReferenceStore:
    def __init__(self,repository,renderer=None,preferences=None,*,project_id=None):
        repository=repository.resolve()
        self.root=repository;self.base=repository/"library/references";self.project_id=project_id
        if project_id is not None:
            from state.project import Project
            from state.workspace import Workspaces
            project=Project.open(repository,project_id)
            expected=repository.resolve()/"projects"/project_id
            if logical_path(project.path)!=expected or Workspaces(repository).metadata(project).get("category","project")!="project":
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Project references require an explicitly selected named project")
            self.base=project.path/"references"
        expected=logical_path(self.base)
        if logical_path(native_path(self.base))!=expected:
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference storage cannot be redirected through a link or junction")
        self.policy=PathPolicy([self.base] if project_id else [repository],[self.base,repository/"runtime/reference_ingestion"])
        self.registry=FileRegistry(self.policy,read_yaml(repository/"config/security/files.yaml"))
        self.backend=OOXMLBackend(repository);self.renderer=renderer
        self.preferences=preferences
        self.manifest=self.base/"manifests/library.json";self.index=self.base/"index/references.json";self.lock=self.base/"index/ingestion.lock"

    def state(self):
        state=read_json(self.manifest) if self.manifest.exists() else {"schema_version":"1.0","pipeline_version":"1.0","decks":{},"aliases":{}}
        if state.get("schema_version") not in {"1.0","1.1"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unsupported reference manifest version")
        validate(self.root,"reference_manifest",state)
        for deck in state["decks"].values():
            for version in [deck,*deck.get("history",[])]:self.storage_path(Path(version["snapshot"]))
            for slide in deck["slides"]:
                for record in slide["artifacts"].values():self.storage_path(Path(record["path"]))
                if slide.get("promoted_original"):self.storage_path(Path(slide["promoted_original"]))
        return state

    def config(self):
        config=read_yaml(self.root/"config/references/sources.yaml")
        if self.project_id:
            config={**config,"schema_version":"1.1","sources":[{"path":logical_path(self.base/"originals").relative_to(self.root.resolve()).as_posix(),"library":"database","brand":"unknown","industry":"unknown","audience":"unknown"}]}
        validate(self.root,"reference_config",config)
        if config.get("schema_version") not in {"1.0","1.1"} or not isinstance(config.get("sources"),list):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid reference configuration")
        for source in config["sources"]:
            folder=self.policy.check(self.root/source["path"])
            if config["schema_version"]=="1.1" and folder!=native_path(self.library_base("database")/"originals"):
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Unified references must use their own scoped originals folder")
        weights=config["ranking"]
        if set(weights)!={"semantic","content_shape","visual","brand","approval"} or any(type(value) not in {int,float} or not 0<=value<=1 for value in weights.values()) or abs(sum(weights.values())-1)>1e-6:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Reference ranking weights must sum to one")
        return config

    def library_base(self,library):
        expected=self.base if self.project_id else self.base/library
        if logical_path(native_path(expected))!=logical_path(expected):
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference library cannot be redirected through a link or junction")
        return expected

    def storage_path(self,path):
        # A manifest is not authorization to read another project's references.
        path=self.policy.check(path)
        if not path.is_relative_to(native_path(self.base)):
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference artifact is outside its selected scope")
        return path

    def scan(self,state,config):
        owned={str(native_path(Path(version["snapshot"]))) for deck in state["decks"].values() for version in [deck,*deck.get("history",[])]}
        owned.update(str(native_path(Path(slide["promoted_original"]))) for deck in state["decks"].values() for slide in deck["slides"] if slide.get("promoted_original"))
        found={}
        for source in config["sources"]:
            folder=self.policy.check(self.root/source["path"])
            if not folder.is_dir():continue
            for path in folder.rglob("*"):
                if path.name in {"deck.pptx","approved.pptx"} and re.fullmatch(r"[a-f0-9]{64}",path.parent.name) and re.fullmatch(r"ref_[a-f0-9]{32}",path.parent.parent.name):continue
                if path.is_file() and path.suffix.lower()==".pptx" and str(native_path(path)) not in owned:
                    path=self.policy.check(path);name=str(logical_path(path))
                    if name in state.get("excluded_sources",[]):continue
                    if name in found and found[name]["library"]!=source["library"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Reference source folders overlap with conflicting library classifications")
                    found[name]={**source,"path":path,"fingerprint":fingerprint(path)}
        return found

    def ingest(self,*,dry_run=False,force=False):
        with FileLock(self.policy.check(self.lock,write=True)):
            state=self.state();config=self.config();found=self.scan(state,config)
            if config["schema_version"]=="1.1":state["schema_version"]="1.1"
            state["pipeline_version"]=config["pipeline_version"]
            report={"schema_version":"1.0","batch_id":uuid4().hex,"dry_run":dry_run,"items":[],"counts":{},"rendered_slides":0,"reused_slides":0}
            origin={deck["source_path"]:key for key,deck in state["decks"].items()}
            hashes={deck["file_sha256"]:key for key,deck in state["decks"].items() if deck.get("active",True)}
            for source_path,source in sorted(found.items()):
                file_hash=source["fingerprint"]["sha256"];reference_id=origin.get(source_path);old=state["decks"].get(reference_id)
                source_config={key:value for key,value in source.items() if key not in {"path","fingerprint"}}
                if file_hash in hashes and hashes[file_hash]!=reference_id:status="duplicate_skipped"
                elif old and old.get("active",True) and old["file_sha256"]==file_hash and old.get("source_config")==source_config and old.get("pipeline_version")==config["pipeline_version"] and not force:
                    status="unchanged_skipped"
                elif not old and file_hash in hashes:status="duplicate_skipped"
                else:status="changed_reingested" if old else "new_ingested"
                item={"source_path":source_path,"status":status,"file_sha256":file_hash}
                if dry_run and status in {"new_ingested","changed_reingested"}:
                    hashes[file_hash]=reference_id or identity("ref",source_path)
                if status=="duplicate_skipped":
                    item["reference_id"]=hashes[file_hash]
                    if not dry_run:
                        state["aliases"][source_path]={"reference_id":hashes[file_hash],"file_sha256":file_hash}
                        if old:old.update(active=False,superseded_by=hashes[file_hash])
                elif status in {"new_ingested","changed_reingested"} and not dry_run:
                    try:
                        reference_id=reference_id or identity("ref",source_path)
                        record,rendered,reused=self._ingest_deck(reference_id,source_path,source,old,config,force)
                        candidate=deepcopy(state);candidate["decks"][reference_id]=record;candidate["aliases"].pop(source_path,None)
                        # Publish the accepted deck atomically before changing in-memory state.
                        write_json(self.policy.check(self.manifest,write=True),candidate)
                        state=candidate
                        if old and hashes.get(old["file_sha256"])==reference_id and old["file_sha256"]!=file_hash:hashes.pop(old["file_sha256"])
                        hashes[file_hash]=reference_id;origin[source_path]=reference_id
                        report["rendered_slides"]+=rendered;report["reused_slides"]+=reused;item["reference_id"]=reference_id
                    except (StudioError,OSError,ValueError,KeyError) as exc:
                        item.update(status="failed",error=exc.as_dict() if isinstance(exc,StudioError) else {"code":"DATA_VALIDATION_ERROR","type":type(exc).__name__,"message":str(exc)})
                report["items"].append(item);report["counts"][item["status"]]=report["counts"].get(item["status"],0)+1
            if not dry_run:
                write_json(self.policy.check(self.manifest,write=True),state);self._write_index(state)
                write_json(self.policy.check(self.base/"manifests"/("batch_"+report["batch_id"]+".json"),write=True),report)
            report["passed"]=not report["counts"].get("failed",0)
            return report

    def _ingest_deck(self,reference_id,source_path,source,old,config,force):
        self.registry.inspect(source["path"],"reference")
        inspection=self.backend.inspect(source["path"]);package=self.backend._read(source["path"])
        file_hash=source["fingerprint"]["sha256"];library=source["library"]
        snapshot=self.policy.check(self.library_base(library)/"originals"/reference_id/file_hash/"deck.pptx",write=True)
        if snapshot.exists():
            if sha256(snapshot)!=file_hash:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Reference snapshot was modified")
        else:self.registry.materialize(source["path"],snapshot,"reference")
        if sha256(snapshot)!=file_hash:raise StudioError(ErrorCode.FILE_CONFLICT,"Reference changed during materialization")
        previous={slide["source_slide_id"]:slide for slide in (old or {}).get("slides",[])}
        from presentation.backends.xml import parse,NS
        palettes=set()
        for name,(_,payload) in package.items():
            if name.endswith(".xml") and name.startswith(("ppt/theme/","ppt/slideMasters/")):
                palettes.update(color.get("val") for color in parse(payload).findall(".//a:srgbClr",NS) if color.get("val"))
        descriptor={**source,"canvas":inspection["canvas"],"declared_palette":sorted(palettes),"theme_hashes":{name:hashlib.sha256(payload).hexdigest() for name,(_,payload) in package.items() if name.startswith("ppt/theme/") and name.endswith(".xml")}};pending=[];slides=[]
        for number,slide in enumerate(inspection["slides"],1):
            digest=slide_fingerprint(package,slide["part"]);prior=previous.get(slide["slide_id"])
            source_config={key:value for key,value in source.items() if key not in {"path","fingerprint"}}
            reused=prior and prior["fingerprint"]==digest and not force and (old or {}).get("pipeline_version")==config["pipeline_version"] and old.get("source_config")==source_config
            if reused and not all(native_path(Path(record["path"])).is_relative_to(native_path(self.library_base(prior["library"]))) for record in prior["artifacts"].values()):reused=False
            if reused:
                self._artifact(prior,"metadata");self._artifact(prior,"preview");self._artifact(prior,"structure")
                slides.append({**deepcopy(prior),"slide_number":number,"status":"unchanged"})
            else:
                slide_id=prior["slide_id"] if prior else identity("slide",reference_id+":"+slide["slide_id"])
                same=prior and prior["fingerprint"]==digest;history=deepcopy((prior or {}).get("approval_history",[]))
                if prior and not same and prior["approval"]!="unreviewed":history.append({"status":"deprecated","reason":"Reference slide content/dependencies changed","time":datetime.now(timezone.utc).isoformat()})
                slides.append({"slide_id":slide_id,"source_slide_id":slide["slide_id"],"slide_number":number,"fingerprint":digest,"approval":prior["approval"] if same else "unreviewed","approval_history":history,"library":prior["library"] if same else library,"status":"changed" if prior else "new"})
                pending.append(number)
        # Keep only the small edge graphs needed after rendering. The package
        # also holds all image/media bytes; release it before native validation
        # and the PowerPoint worker load their own copies of a large deck.
        pending_edges={number:self._edges(package,inspection["slides"][number-1]["part"]) for number in pending}
        del package
        if pending:
            if self.renderer is None:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"New reference slides require a real renderer")
            stage=self.root/"runtime/reference_ingestion"/uuid4().hex
            rendered=self.renderer.render(snapshot,stage,slide_indices=pending)
            if not rendered.get("passed") or {slide["index"] for slide in rendered["slides"]}!=set(pending) or rendered.get("input_sha256")!=file_hash:raise StudioError(ErrorCode.QA_FAILURE,"Reference preview proof is incomplete or stale")
            native={slide["index"]:slide for slide in rendered["slides"]}
            generation=uuid4().hex
            for number in pending:
                slide=slides[number-1];actual=inspection["slides"][number-1];measured=native[number]
                artifact_library=slide["library"]
                folder=self.library_base(artifact_library)/"metadata"/reference_id/generation/slide["slide_id"]
                preview=self.policy.check(self.library_base(artifact_library)/"previews"/reference_id/generation/(slide["slide_id"]+".png"),write=True);preview.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(native_path(Path(measured["render"])),preview)
                metadata=describe(actual,measured,descriptor,preview);elements=metadata["structural"].pop("elements")
                metadata.update(schema_version="1.0",reference_id=reference_id,slide_id=slide["slide_id"],provenance={"source_path":source_path,"source_sha256":file_hash,"source_slide_id":slide["source_slide_id"],"slide_fingerprint":slide["fingerprint"],"snapshot":str(logical_path(snapshot))},trust="untrusted_reference_data")
                structure={"schema_version":"1.0","inspection":actual,"native":measured,"element_graph":{"nodes":elements,"edges":pending_edges[number]}}
                paths={"metadata":self.policy.check(folder/"metadata.json",write=True),"structure":self.policy.check(folder/"structure.json",write=True),"preview":preview}
                write_json(paths["metadata"],metadata);write_json(paths["structure"],structure)
                slide["artifacts"]={key:{"path":str(logical_path(path)),"sha256":sha256(path)} for key,path in paths.items()}
                slide["summary"]={"title":metadata["semantic"]["title"],"tokens":metadata["semantic"]["tokens"],"content_shape":metadata["structural"]["content_shape"],"density":metadata["visual"]["nonwhite_fraction"],"brand":metadata["brand"]}
        for slide in slides:
            if slide["approval"]=="approved":
                approved=self.policy.check(self.library_base("database" if library=="database" else "approved_internal")/"originals"/reference_id/file_hash/"approved.pptx",write=True)
                if not approved.exists():self.registry.materialize(snapshot,approved,"reference")
                if sha256(approved)!=file_hash:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Approved reference snapshot was modified")
                slide["promoted_original"]=str(logical_path(approved))
        if fingerprint(source["path"])!=source["fingerprint"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Reference changed during ingestion; previous index remains authoritative")
        return {"reference_id":reference_id,"source_path":source_path,"file_sha256":file_hash,"snapshot":str(logical_path(snapshot)),"library":library,"active":True,"source_config":source_config,"pipeline_version":config["pipeline_version"],"last_ingested_at":datetime.now(timezone.utc).isoformat(),"slides":slides,"removed_slide_ids":[row["slide_id"] for key,row in previous.items() if key not in {slide["source_slide_id"] for slide in slides}],"history":[*(old or {}).get("history",[]),*([{key:old[key] for key in ["file_sha256","snapshot","last_ingested_at"]}] if old else [])]},len(pending),len(slides)-len(pending)

    def _edges(self,package,part):
        from presentation.backends.xml import NS,parse
        edges=[];node=parse(package[part][1])
        for group in node.findall(".//p:grpSp",NS):
            owner=group.find("p:nvGrpSpPr/p:cNvPr",NS)
            if owner is None:continue
            for child in group:
                if child.tag not in {f"{{{NS['p']}}}"+kind for kind in ["sp","pic","graphicFrame","grpSp","cxnSp"]}:continue
                properties=child.find(".//p:cNvPr",NS)
                if properties is not None:edges.append({"from_native_id":owner.get("id"),"to_native_id":properties.get("id"),"type":"group_contains"})
        for connector in node.findall(".//p:cxnSp",NS):
            owner=connector.find("p:nvCxnSpPr/p:cNvPr",NS)
            if owner is None:continue
            for relation in connector.findall(".//a:stCxn",NS)+connector.findall(".//a:endCxn",NS):edges.append({"from_native_id":owner.get("id"),"to_native_id":relation.get("id"),"type":"connector_anchor"})
        return edges

    def _index_rows(self,state):
        return [{"reference_id":key,"slide_id":slide["slide_id"],"library":slide["library"],"approval":slide["approval"],"summary":slide["summary"]} for key,deck in state["decks"].items() if deck.get("active",True) for slide in deck["slides"]]

    def _write_index(self,state):
        write_json(self.policy.check(self.index,write=True),{"schema_version":"1.0","manifest_sha256":sha256(self.manifest),"rows":self._index_rows(state)})

    def query(self,query,limit=8,context=None):
        if type(limit)!=int or not 1<=limit<=100 or "density" in query and not 0<=query["density"]<=1:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid reference query bounds")
        with FileLock(self.policy.check(self.lock,write=True)):
            state=self.state()
            if not self.manifest.exists():return []
            index=read_json(self.index) if self.index.exists() else None
            if not index or index.get("manifest_sha256")!=sha256(self.manifest) or index.get("rows")!=self._index_rows(state):self._write_index(state);index=read_json(self.index)
            ranked=rank(index["rows"],query,self.config()["ranking"])
            if self.preferences:
                ranked=[{**row,"pattern":"reference:"+row["reference_id"]+":"+row["slide_id"]} for row in ranked]
                ranked=self.preferences.rerank(ranked,context or {"brand":query.get("brand") or "*"})
            return ranked[:limit]

    def _slide(self,reference_id,slide_id):
        state=self.state();deck=state["decks"].get(reference_id)
        slide=next((row for row in (deck or {}).get("slides",[]) if row["slide_id"]==slide_id),None)
        if not slide:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown reference slide")
        return deck,slide

    def _artifact(self,slide,kind):
        record=slide["artifacts"][kind];path=self.storage_path(Path(record["path"]))
        if not path.is_file() or sha256(path)!=record["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Reference derivative is missing or modified; rerun ingestion with --force")
        return path

    def load(self,reference_id,slide_id,stage="metadata"):
        if stage not in {"metadata","preview","structure","original"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown progressive reference stage")
        deck,slide=self._slide(reference_id,slide_id)
        if stage=="original":
            path=self.storage_path(Path(slide.get("promoted_original",deck["snapshot"])))
            if not path.is_file() or sha256(path)!=deck["file_sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Reference original snapshot was modified")
            return {"path":str(logical_path(path)),"source_path":deck["source_path"],"sha256":deck["file_sha256"],"slide_number":slide["slide_number"],"trust":"untrusted_reference_data"}
        path=self._artifact(slide,stage)
        if stage=="preview":return {"path":str(logical_path(path)),"sha256":slide["artifacts"][stage]["sha256"],"trust":"untrusted_reference_data"}
        return {**read_json(path),"approval":slide["approval"],"library":slide["library"]}

    def promote(self,reference_id,slide_id,*,reason,actor="user"):
        if not reason.strip():raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Promotion requires an explicit approval reason")
        with FileLock(self.policy.check(self.lock,write=True)):
            state=self.state();deck,slide=self._slide(reference_id,slide_id)
            approved_library="database" if deck["library"]=="database" else "approved_internal"
            approved_base=self.library_base(approved_library)
            if slide["approval"]=="approved" and all(native_path(Path(record["path"])).is_relative_to(native_path(approved_base)) for record in slide["artifacts"].values()):
                self.load(reference_id,slide_id,"original")
                for kind in ["metadata","preview","structure"]:self._artifact(slide,kind)
                return {"status":"unchanged","reference_id":reference_id,"slide_id":slide_id}
            original=self.load(reference_id,slide_id,"original")
            destination=self.policy.check(approved_base/"originals"/reference_id/deck["file_sha256"]/"approved.pptx",write=True)
            if not destination.exists():self.registry.materialize(Path(original["path"]),destination,"reference")
            elif sha256(destination)!=deck["file_sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Approved reference snapshot was modified")
            selected=next(row for row in state["decks"][reference_id]["slides"] if row["slide_id"]==slide_id)
            generation=uuid4().hex
            for kind in ["metadata","preview","structure"]:
                previous=self._artifact(slide,kind)
                target=self.policy.check(approved_base/("previews" if kind=="preview" else "metadata")/reference_id/generation/(slide_id+".png" if kind=="preview" else slide_id+"_"+kind+".json"),write=True)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(previous,target)
                if sha256(target)!=slide["artifacts"][kind]["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Approved reference derivative copy changed")
                selected["artifacts"][kind]={"path":str(logical_path(target)),"sha256":sha256(target)}
            selected.update(approval="approved",library=approved_library,promoted_original=str(logical_path(destination)))
            selected["approval_history"].append({"status":"approved","actor":actor,"reason":reason,"time":datetime.now(timezone.utc).isoformat()})
            write_json(self.policy.check(self.manifest,write=True),state);self._write_index(state)
            if self.preferences and actor=="user":
                self.preferences.record(reason,"reference:"+reference_id+":"+slide_id,event_id="approval:"+reference_id+":"+slide_id+":"+deck["file_sha256"],declared_type="DESIGN_FEEDBACK",polarity="positive",context={"brand":slide["summary"]["brand"] if slide["summary"]["brand"]!="unknown" else "*"})
            return {"status":"promoted","reference_id":reference_id,"slide_id":slide_id}
