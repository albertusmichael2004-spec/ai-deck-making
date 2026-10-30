from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

from presentation.rendering.native import NativeRenderer
from references.store import ReferenceStore
from state.io import fingerprint,read_json,write_json


def test_real_manual_reference_batch_incremental_and_progressive_load(repo):
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location("native_reference_case",root/"tests/integration/test_reference_store.py")
    case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    name="native-reference-"+uuid4().hex[:10]+".pptx"
    original,basic=case.create_reference(repo,name)
    before=fingerprint(original);store=ReferenceStore(repo,NativeRenderer(root,90))
    result=store.ingest();assert result["passed"],result
    item=next(item for item in result["items"] if item["source_path"].endswith(name));assert item["status"]=="new_ingested"
    reference_id=item["reference_id"];first=store.state()["decks"][reference_id]["slides"][0]
    metadata=store.load(reference_id,first["slide_id"]);preview=store.load(reference_id,first["slide_id"],"preview")
    assert metadata["visual"]["fonts"] and metadata["visual"]["nonwhite_fraction"]>0 and fingerprint(original)==before
    assert store.load(reference_id,first["slide_id"],"structure")["native"]["index"]==1
    again=store.ingest();assert next(item for item in again["items"] if item["source_path"].endswith(name))["status"]=="unchanged_skipped"
    changed=deepcopy(basic);changed["slides"][0]["action_title"]="Reference ingestion detects a changed native message"
    case.create_reference(repo,name,changed)
    result=store.ingest();assert result["passed"] and result["rendered_slides"]==1 and result["reused_slides"]>=1,result
    store.promote(reference_id,first["slide_id"],reason="Explicit native reference fixture approval",actor="integration_test")
    assert store.load(reference_id,first["slide_id"])["approval"]=="approved"
    write_json(root/"implementation/PHASE_REPORTS/phase_7_native_case.json",{"passed":True,"repository":str(repo),"evaluation_isolated":True,"reference_id":reference_id,"slide_id":first["slide_id"],"source":str(original),"source_preserved":True,"incremental_rendered_slides":result["rendered_slides"],"preview":store.load(reference_id,first["slide_id"],"preview"),"metadata":store.load(reference_id,first["slide_id"]),"promotion":"approved"})
