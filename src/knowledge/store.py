"""Manual package ingestion and provenance-bearing lexical retrieval."""
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from uuid import uuid4

from evidence.extraction import extract
from evidence.store import identity
from state.errors import StudioError,ErrorCode
from state.io import native_path,logical_path,read_json,read_yaml,write_json,sha256,atomic_bytes
from state.locking import FileLock
from ir.validation import validate


ISOLATED={"evaluation_isolated","inert_production_tooling","package_qa_or_cache","archive_backup"}
STRUCTURED={"structured_knowledge_chunks","topic_index","machine_contract"}
CANONICAL={"chunks":"normalized/chunks","topics":"normalized/topics","contracts":"normalized/contracts","provenance":"provenance/manifests","source_maps":"provenance/source_maps","index":"index/retrieval_metadata","playbooks":"normalized/playbooks","topic_index":"index/topic_index"}


def chunk_text(text,max_chars=2400):
    paragraphs=re.split(r"\n\s*\n",text.strip());buffer=""
    for paragraph in paragraphs:
        for offset in range(0,len(paragraph),max_chars):
            part=paragraph[offset:offset+max_chars]
            if buffer and len(buffer)+len(part)>max_chars:yield buffer;buffer=""
            buffer+=("\n\n" if buffer else "")+part
    if buffer:yield buffer


class KnowledgeStore:
    def __init__(self,repository):
        self.repository=repository
        self.root=native_path(repository/"library/knowledge")

    def _package(self,package_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+",package_id):raise StudioError(ErrorCode.SECURITY_BLOCK,"Invalid knowledge package identifier")
        path=self.root/"packages"/package_id
        if not path.is_dir():raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Knowledge package is not registered")
        return path

    def ingest(self,package_id):
        package=self._package(package_id)
        with FileLock(native_path(self.repository/"runtime/locks/knowledge.lock")):
            return self._ingest(package_id,package)

    def _ingest(self,package_id,package):
        metadata=read_yaml(package/"package_manifest.yaml")
        source=package/metadata["original_root"]
        if not source.resolve().is_relative_to(package.resolve()):raise StudioError(ErrorCode.SECURITY_BLOCK,"Package source escapes registry")
        original=read_json(package/metadata["source_inventory"])
        known={row["path"].replace("\\","/"):row for row in original["files"]}
        known.update({row["path"]:{**row,"role":"package_navigation" if row["path"].endswith(".md") else "package_manifest"} for row in metadata.get("restored_metadata",[])})
        files=[];duplicates={};unrecognized=[]
        for path in sorted(source.rglob("*")):
            if not path.is_file():continue
            if not path.resolve().is_relative_to(source.resolve()):raise StudioError(ErrorCode.SECURITY_BLOCK,"Knowledge source resolves outside its package")
            relative=path.relative_to(source).as_posix();record=known.get(relative)
            digest=sha256(path)
            if record and digest!=record["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Immutable knowledge package changed",file=relative)
            if record is None:
                unrecognized.append(relative);role="unclassified_keep_in_place"
            else:role=record["role"]
            duplicate=duplicates.get(digest);duplicates.setdefault(digest,relative)
            files.append({"path":relative,"sha256":digest,"bytes":path.stat().st_size,"role":role,"duplicate_of":duplicate})
        missing=set(known)-{row["path"] for row in files}
        if missing:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Knowledge package files are missing",files=sorted(missing))
        fingerprint=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        previous=read_json(package/"ingestion_manifest.json") if (package/"ingestion_manifest.json").exists() else None
        if previous and previous["fingerprint"]==fingerprint:
            self._verify_generation(package,previous)
            if previous.get("storage_layout")!="canonical_v1" or not {"playbooks","topic_index"}<=set(previous["artifacts"]):previous=self._publish_canonical(package,previous)
            return {**previous,"status":"unchanged"}
        generation=native_path(self.repository/"runtime/cache/knowledge_staging"/uuid4().hex)
        generation.mkdir(parents=True)
        provenance=[];chunks=[];topics=[];contracts=[];reused=[];limitations=[];source_maps={}
        # Validate machine-native source maps once, keeping their original row locators.
        for row in files:
            path=source/row["path"]
            if path.suffix.lower()==".csv" and row["role"] not in ISOLATED:
                with path.open(encoding="utf-8-sig",newline="") as stream:
                    reader=csv.DictReader(stream)
                    if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Package CSV has invalid columns",file=row["path"])
                    records=list(reader)
                if any(None in record or any(value is None for value in record.values()) for record in records):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Package source map row width is invalid",file=row["path"])
                source_maps[row["path"]]=records
        for row in files:
            path=source/row["path"];role=row["role"]
            provenance.append({**row,"original_path":str(path),"trust":"untrusted_package_content","runtime_retrieval":role not in ISOLATED and role!="unclassified_keep_in_place"})
            if role in ISOLATED or role=="unclassified_keep_in_place":continue
            base={"package_id":package_id,"original_path":str(path),"original_relative_path":row["path"],"source_sha256":row["sha256"],"source_role":role,"trust":"untrusted_package_content","knowledge_policy":"reasoning_guidance_not_project_fact"}
            if role=="structured_knowledge_chunks":
                records=[json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                identifiers=set()
                # Source IDs are scoped to the corresponding package source catalog.
                catalogs=[records for name,records in source_maps.items() if (name.startswith("Consulting Knowledge/") if row["path"].startswith("Consulting Knowledge/") else not name.startswith("Consulting Knowledge/"))]
                source_ids={record.get("id",record.get("source_id")) for catalog in catalogs for record in catalog}
                for index,item in enumerate(records,1):
                    if not all(key in item for key in ["chunk_id","topic_id","text","source_ids"]) or not isinstance(item["text"],str) or not item["text"].strip() or item["chunk_id"] in identifiers:
                        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Existing knowledge chunk is incompatible",file=row["path"],line=index)
                    identifiers.add(item["chunk_id"])
                    if not set(item["source_ids"])<=source_ids:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Existing chunk source IDs do not resolve",file=row["path"],line=index)
                    pdf=item.get("pdf_path")
                    if pdf:
                        referenced=(source/pdf).resolve()
                        if not referenced.is_relative_to(source.resolve()) or not referenced.is_file():raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chunk manual locator is invalid")
                    chunks.append({**base,"chunk_id":identity("kn",package_id+":"+row["path"]+":"+item["chunk_id"]),"source_chunk_id":item["chunk_id"],"topic_id":str(item["topic_id"]),"title":item.get("title",item.get("topic","")),"text":item["text"],"locator":f"line:{index}","kind":"playbook","source_ids":item["source_ids"],"source_relation":item.get("source_relation",item.get("content_type","guidance")),"synthetic":item.get("synthetic_case",item.get("example_status",False))})
                reused.append({"file":row["path"],"role":role,"records":len(records)})
            elif role=="topic_index":
                records=read_json(path)
                if not isinstance(records,list) or any(not isinstance(record,dict) or not record.get("title") or not ("id" in record or "topic_id" in record) for record in records):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Topic index is incompatible")
                topics.extend({**base,**record} for record in records);reused.append({"file":row["path"],"role":role,"records":len(records)})
            elif role=="machine_contract":
                content=read_json(path)
                if not isinstance(content,dict) or not content or any(not isinstance(key,str) or not isinstance(value,(str,list,dict)) for key,value in content.items()):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Agent output contract is incompatible")
                contracts.append({**base,"contract_id":identity("contract",package_id+":"+row["path"]),"contract":content})
                reused.append({"file":row["path"],"role":role,"records":1})
            elif role in {"knowledge_manual","package_navigation"}:
                extracted=extract(path)
                limitations.extend({"file":row["path"],**limit} for limit in extracted["limitations"])
                for record in extracted["records"]:
                    for index,text in enumerate(chunk_text(str(record["value"]))):
                        chunks.append({**base,"chunk_id":identity("kn",package_id+":"+row["path"]+":"+record["locator"]+":"+str(index)),"topic_id":path.parent.name,"title":path.stem,"text":text,"locator":record["locator"]+f"/chunk:{index}","kind":"manual","source_ids":[],"synthetic":"may_include_training_examples"})
            # Structured provenance stays native, never promoted to business facts or executable instructions.
        normalized={"chunks":chunks,"topics":topics,"contracts":contracts,"provenance":provenance,"source_maps":source_maps}
        validate(self.repository,"knowledge_chunks",{"schema_version":"1.0","chunks":chunks})
        artifacts={}
        for name,value in normalized.items():
            target=generation/(name+".json");write_json(target,value);artifacts[name]={"path":str(target),"sha256":sha256(target)}
        index=generation/"retrieval.sqlite"
        with sqlite3.connect(str(logical_path(index))) as connection:
            connection.execute("CREATE VIRTUAL TABLE chunks USING fts5(chunk_id UNINDEXED, topic, kind UNINDEXED, title, text, tokenize='unicode61')")
            connection.executemany("INSERT INTO chunks VALUES (?,?,?,?,?)",[(row["chunk_id"],row["topic_id"],row["kind"],row["title"],row["text"]) for row in chunks])
        artifacts["index"]={"path":str(index),"sha256":sha256(index)}
        manifest={"schema_version":"1.0","package_id":package_id,"fingerprint":fingerprint,"status":"ingested","files":len(files),"roles":dict(Counter(row["role"] for row in files)),"chunks":len(chunks),"contracts":len(contracts),"topics":len(topics),"reused":reused,"artifacts":artifacts,"unrecognized":unrecognized,"limitations":limitations,"evaluation_isolation":True,"production_scripts_executed":0,"archives_ingested":0}
        return self._publish_canonical(package,manifest)

    def _publish_canonical(self,package,manifest):
        staging=native_path(self.repository/"runtime/cache/knowledge_views"/uuid4().hex)
        for name in ["playbooks","topic_index"]:
            if name in manifest["artifacts"]:continue
            records=read_json(Path(manifest["artifacts"]["chunks" if name=="playbooks" else "topics"]["path"]))
            if name=="playbooks":
                view={}
                for row in records:
                    if row["kind"]=="playbook":view.setdefault(row["topic_id"],[]).append(row["chunk_id"])
            else:view=[{"topic_id":str(row.get("id",row.get("topic_id"))),"title":row["title"],"original_path":row["original_path"],"source_sha256":row["source_sha256"]} for row in records]
            target=staging/(name+".json");write_json(target,view)
            manifest["artifacts"][name]={"path":str(target),"sha256":sha256(target)}
        generation=uuid4().hex;previous={name:dict(record) for name,record in manifest["artifacts"].items()}
        for name,record in manifest["artifacts"].items():
            source=native_path(Path(record["path"]))
            target=self.root/CANONICAL[name]/manifest["package_id"]/generation/source.name
            atomic_bytes(target,source.read_bytes())
            if sha256(target)!=record["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Canonical knowledge copy verification failed")
            record["path"]=str(target)
        manifest["storage_layout"]="canonical_v1"
        manifest["layout_migration"]={"previous_artifacts":previous,"original_bytes_changed":False}
        self._verify_generation(package,manifest)
        # Per-package record is a compatibility view; global ingestion record is canonical.
        write_json(self.root/"ingestion/manifests"/(manifest["package_id"]+".json"),manifest)
        write_json(package/"ingestion_manifest.json",manifest)
        isolated=[row for row in read_json(Path(manifest["artifacts"]["provenance"]["path"])) if row["role"]=="evaluation_isolated"]
        write_json(self.root/"evaluations/eval_cases"/(manifest["package_id"]+".manifest.json"),isolated)
        return manifest

    def _verify_generation(self,package,manifest):
        validate(self.repository,"knowledge_ingestion",manifest)
        for name,record in manifest["artifacts"].items():
            path=native_path(Path(record["path"]))
            expected=self.root/CANONICAL[name]/manifest["package_id"] if manifest.get("storage_layout")=="canonical_v1" else package
            if not path.is_relative_to(expected) or not path.is_file() or sha256(path)!=record["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Normalized knowledge artifact changed")

    def retrieve(self,query,limit=8,topic=None,kind=None):
        if type(limit)!=int or not 1<=limit<=100:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid retrieval limit")
        terms=re.findall(r"\w+",query,flags=re.UNICODE)
        if not terms:return []
        match=" OR ".join('"'+term+'"' for term in terms)
        results=[]
        for package in (self.root/"packages").iterdir():
            if not (package/"ingestion_manifest.json").is_file():continue
            manifest=read_json(package/"ingestion_manifest.json");self._verify_generation(package,manifest)
            artifacts=manifest["artifacts"]
            records={row["chunk_id"]:row for row in read_json(Path(artifacts["chunks"]["path"]))}
            validate(self.repository,"knowledge_chunks",{"schema_version":"1.0","chunks":list(records.values())})
            index=Path(artifacts["index"]["path"])
            with sqlite3.connect(logical_path(index).as_uri()+"?mode=ro",uri=True) as connection:
                where="chunks MATCH ?";values=[match]
                if topic is not None:where+=" AND topic=?";values.append(topic)
                if kind is not None:where+=" AND kind=?";values.append(kind)
                rows=connection.execute("SELECT chunk_id,bm25(chunks,0,2,0,3,1) FROM chunks WHERE "+where+" ORDER BY 2 LIMIT ?",[*values,limit]).fetchall()
            for identifier,score in rows:
                record=records[identifier]
                if sha256(Path(record["original_path"]))!=record["source_sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Retrieved source changed after ingestion")
                results.append({**record,"score":-score})
        seen=set();unique=[]
        for row in sorted(results,key=lambda row:row["score"],reverse=True):
            content=" ".join(row["text"].lower().split())
            if content in seen:continue
            seen.add(content);unique.append(row)
        return unique[:limit]
