import json
from pathlib import Path

import pytest

from knowledge.store import KnowledgeStore
from state.errors import StudioError,ErrorCode
from state.io import write_json,write_yaml,sha256,read_json


def package(repo):
    root=repo/"library/knowledge/packages/fixture";source=root/"original_package";source.mkdir(parents=True)
    rows=[]
    def add(name,content,role):
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding="utf-8")
        rows.append({"path":name,"sha256":sha256(path),"role":role,"bytes":path.stat().st_size})
    add("Source_Map.csv","id,publisher,title\nS1,Primary,Methods\n","source_provenance")
    add("knowledge_chunks.jsonl",json.dumps({"chunk_id":"k1","topic_id":"MECE","text":"MECE partitions the decision into mutually exclusive collectively exhaustive issues.","source_ids":["S1"],"title":"MECE"})+"\n","structured_knowledge_chunks")
    add("topic_index.json",json.dumps([{"id":"MECE","title":"MECE"}]),"topic_index")
    add("Agent_Output_Contract.json",json.dumps({"claim":"string","evidence":"source + locator"}),"machine_contract")
    add("manual.md","# Pyramid\n\nPresent the answer before the supporting arguments.","knowledge_manual")
    add("evaluations.jsonl",'{"answer":"holdout_canary_secret"}\n',"evaluation_isolated")
    add("build.py","raise RuntimeError('must never execute')","inert_production_tooling")
    add("backup.zip","inert duplicate backup","archive_backup")
    write_json(root/"bootstrap_inventory.json",{"files":rows})
    write_yaml(root/"package_manifest.yaml",{"original_root":"original_package","source_inventory":"bootstrap_inventory.json"})
    return root


def test_native_roles_reuse_provenance_isolation_and_idempotence(repo):
    root=package(repo);store=KnowledgeStore(repo)
    report=store.ingest("fixture")
    assert report["chunks"]==3 and report["topics"]==1 and report["contracts"]==1
    assert report["production_scripts_executed"]==0 and report["archives_ingested"]==0
    assert store.ingest("fixture")["status"]=="unchanged"
    assert store.retrieve("holdout_canary_secret")==[]
    hits=store.retrieve("MECE",kind="playbook")
    assert hits[0]["source_ids"]==["S1"] and hits[0]["locator"]=="line:1"
    assert hits[0]["knowledge_policy"]=="reasoning_guidance_not_project_fact"
    assert report["storage_layout"]=="canonical_v1"
    assert (repo/"library/knowledge/ingestion/manifests/fixture.json").exists()
    assert (repo/"library/knowledge/evaluations/eval_cases/fixture.manifest.json").exists()


def test_changed_original_and_index_are_blocked(repo):
    root=package(repo);store=KnowledgeStore(repo);report=store.ingest("fixture")
    original=root/"original_package/manual.md";original.write_text("tampered")
    with pytest.raises(StudioError) as error:store.ingest("fixture")
    assert error.value.code==ErrorCode.SOURCE_CONFLICT
    with pytest.raises(StudioError):store.retrieve("Pyramid")
    index=Path(report["artifacts"]["index"]["path"]);index.write_bytes(b"broken")
    with pytest.raises(StudioError):store.retrieve("MECE")


def test_unrecognized_files_kept_in_place_not_retrieved(repo):
    root=package(repo);path=root/"original_package/unrecognized.md";path.write_text("unknown_canary")
    report=KnowledgeStore(repo).ingest("fixture")
    assert report["unrecognized"]==["unrecognized.md"]
    assert path.exists() and KnowledgeStore(repo).retrieve("unknown_canary")==[]
