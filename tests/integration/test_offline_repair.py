from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from orchestration.offline import OfflineLoop
from orchestration.repair import PatchExecutor
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.incremental import IncrementalCompiler,affected_slides
from qa.critic import Critic
from qa.regression import protected_scope
from state.errors import StudioError
from state.io import read_json,write_json,sha256

module=importlib.util.spec_from_file_location("repair_control",Path(__file__).with_name("test_critic.py"));case=importlib.util.module_from_spec(module);module.loader.exec_module(case)


class ControlRenderer:
    """Explicit kernel fixture; never used as native production gate evidence."""
    def render(self,source,output):
        from PIL import Image
        output.mkdir(parents=True)
        inspection=OOXMLBackend(self.root).inspect(source)
        rows=[]
        for index,slide in enumerate(inspection["slides"]):
            image=output/f"slide_{index}.png";Image.new("RGB",(1600,900),"white").save(image)
            metrics=[]
            for obj in slide["objects"]:
                g=obj["geometry"];w,h=g["width"]*72,g["height"]*72
                row={"native_id":obj["native_id"],"x_pt":g["x"]*72,"y_pt":g["y"]*72,"width_pt":w,"height_pt":h,"text_bounds_pt":{"width":max(1,w-10),"height":max(1,h-10)},"margins_pt":{"left":0,"right":0,"top":0,"bottom":0},"runs":[{"font_pt":14}],"line_count":1}
                if obj.get("content_type")=="chart":row["chart_series"]=[{"values":item["values"],"categories":item["categories"]} for item in obj["chart_data"]]
                metrics.append(row)
            rows.append({"index":index+1,"render":str(image),"shapes":metrics})
        result={"passed":True,"renderer":"control_kernel_fixture","input_sha256":sha256(source),"canvas_pt":{"width":960,"height":540},"slides":rows}
        write_json(output/"render_report.json",result);return result
    def __init__(self,root):self.root=root


def prepare(repo,project):
    designed,context,output,inspection,rendered,response=case.prepare(repo,project)
    backend=OOXMLBackend(repo);compiler=PresentationCompiler(repo,AdaptiveLayoutCompiler(repo),backend)
    scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MAY_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
    return designed,context,backend,compiler,scope,response


class Repair:
    def __init__(self,no_op=False):self.no_op=no_op
    def propose(self,spec,inspection,findings,scope):
        slide=inspection["slides"][0];title=next(o for o in slide["objects"] if o["role"]=="title")
        return {"schema_version":"1.0","plan_id":uuid4().hex,"reason":"Remove unsupported copy","candidate_sha256":inspection["sha256"],"analytical_evidence_ids":[],"scope":scope,"patch":{"schema_version":"1.0","patch_id":uuid4().hex,"operations":[{"slide_id":slide["slide_id"],"object_id":title["object_id"],"expected_fingerprint":title["fingerprint"],"operation":"set_text","value":title["text"] if self.no_op else "Prioritize a Materials review while protecting operating reliability."}]}}


def test_bounded_repair_commits_only_after_both_reviews_and_replay_is_noop(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    designed["slides"][0]["action_title"]="Prioritize a 99 percentage points recovery."
    loop=OfflineLoop(repo,project,backend,ControlRenderer(repo),Critic(repo,case.Reviewer(response)),Repair())
    run_id=uuid4().hex;result=loop.run(designed,scope=scope,run_id=run_id)
    assert result["passed"] and result["state"]["iteration"]==1 and len(result["state"]["history"])==2
    assert project.state()["generation"]==1 and result["state"]["history"][0]["critic_passed"] is False
    assert loop.run(designed,scope=scope,run_id=run_id)["no_op"]


@pytest.mark.parametrize("budget,noop,reason",[(0,False,"iteration_budget"),(2,True,"no_op_repair")])
def test_failed_and_noop_repairs_never_commit(repo,project,budget,noop,reason):
    designed,context,backend,compiler,scope,response=prepare(repo,project);designed["slides"][0]["action_title"]="Recover 99 percentage points."
    result=OfflineLoop(repo,project,backend,ControlRenderer(repo),Critic(repo,case.Reviewer(response)),Repair(noop)).run(designed,scope=scope,max_iterations=budget)
    assert not result["passed"] and result["state"]["stop_reason"]==reason and not project.canonical.exists()


def test_scoped_repair_rejects_widened_scope_and_stale_candidate(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    source=project.path/"work/critic_fixture.pptx";plan=Repair().propose(designed,backend.inspect(source),[],scope)
    protected=deepcopy(scope)
    for obj in protected["objects"]:obj["protection"]="MUST_NOT_CHANGE"
    executor=PatchExecutor(repo,backend)
    with pytest.raises(StudioError):executor.apply(source,project.path/"work/unsafe.pptx",designed,plan,context,protected)
    plan["candidate_sha256"]="0"*64
    with pytest.raises(StudioError):executor.apply(source,project.path/"work/stale.pptx",designed,plan,context,scope)


def test_crash_resume_rechecks_evidence_and_replays_pending_native_review(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    class Crash:
        provider=case.Reviewer(response)
        def evaluate(self,*args,**kwargs):raise RuntimeError("simulated interruption after render")
    run_id=uuid4().hex;loop=OfflineLoop(repo,project,backend,ControlRenderer(repo),Crash())
    with pytest.raises(RuntimeError):loop.run(designed,scope=scope,run_id=run_id)
    loop.critic=Critic(repo,case.Reviewer(response))
    assert loop.run(designed,scope=scope,run_id=run_id)["passed"]
    assert project.state()["generation"]==1


def test_incremental_copy_recompiles_one_slide_preserving_other_parts(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    source=project.path/"work/critic_fixture.pptx";revised=deepcopy(designed)
    revised["slides"][1]["key_message"]="Materials account for 4 percentage points of recorded margin decline."
    output=project.path/"work/incremental.pptx"
    result=IncrementalCompiler(repo,compiler).compile(source,output,designed,revised,context,[],scope)
    assert result["recompiled_slides"]==[designed["slides"][1]["slide_id"]]
    old=backend._read(source);new=backend._read(output)
    unchanged=[slide["part"] for slide in backend.inspect(source)["slides"] if slide["slide_id"]!=designed["slides"][1]["slide_id"]]
    assert all(old[name][1]==new[name][1] for name in unchanged)
    assert all(old[name][1]==new[name][1] for name in old if name.startswith("ppt/slideMasters/"))
    assert backend.validate(output)["passed"]


def test_dependency_refresh_marks_analytical_claims_stale_and_refuses_silent_reuse(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    from evidence.store import EvidenceStore
    store=EvidenceStore(repo,project);source=next(iter(store.load().value["sources"].values()))
    original=Path(source["original_path"]);original.write_text(original.read_text().replace("Materials,4","Materials,2"),encoding="utf-8")
    refresh=store.refresh(source["source_id"]);updated=EvidenceContext(store.load(),project.policy)
    assert affected_slides(designed,updated.graph,refresh["affected"])
    with pytest.raises(StudioError,match="invalidated claims"):
        IncrementalCompiler(repo,compiler).compile(project.path/"work/critic_fixture.pptx",project.path/"work/unsafe_refresh.pptx",designed,designed,updated,refresh["affected"],scope)


def test_chart_dependencies_are_protected_even_when_frame_xml_is_identical():
    before={"slides":[{"slide_id":"s","objects":[{"object_id":"chart","fingerprint":"same","chart":{"series":[4,1]}}]}]}
    after=deepcopy(before);after["slides"][0]["objects"][0]["chart"]["series"]=[99,1]
    assert not protected_scope(before,after,{"objects":[]})["passed"]


def test_interruption_before_atomic_commit_resumes_with_new_review(repo,project,monkeypatch):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    loop=OfflineLoop(repo,project,backend,ControlRenderer(repo),Critic(repo,case.Reviewer(response)))
    run_id=uuid4().hex;original=project.commit
    def crash(*args,**kwargs):raise RuntimeError("interrupted immediately before commit")
    monkeypatch.setattr(project,"commit",crash)
    with pytest.raises(RuntimeError):loop.run(designed,scope=scope,run_id=run_id)
    monkeypatch.setattr(project,"commit",original)
    assert loop.run(designed,scope=scope,run_id=run_id)["passed"]


def test_existing_deck_cannot_be_whole_replaced_and_noop_patch_does_not_advance_generation(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    loop=OfflineLoop(repo,project,backend,ControlRenderer(repo),Critic(repo,case.Reviewer(response)))
    assert loop.run(designed,scope=scope)["passed"]
    with pytest.raises(StudioError,match="Existing decks"):loop.run(designed,scope=scope)
    plan=Repair(True).propose(designed,backend.inspect(project.canonical),[],scope)
    assert loop.run(designed,scope=scope,initial_patch=plan["patch"])["no_op"]
    assert project.state()["generation"]==1


def test_resume_never_overwrites_concurrent_canonical_change(repo,project):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    class Crash:
        provider=case.Reviewer(response)
        def evaluate(self,*args,**kwargs):raise RuntimeError("interruption")
    run_id=uuid4().hex;loop=OfflineLoop(repo,project,backend,ControlRenderer(repo),Crash())
    with pytest.raises(RuntimeError):loop.run(designed,scope=scope,run_id=run_id)
    project.canonical.write_bytes(b"user draft")
    with pytest.raises(StudioError,match="User changed"):loop.run(designed,scope=scope,run_id=run_id)
    assert project.canonical.read_bytes()==b"user draft"


@pytest.mark.parametrize("budget",[{"max_iterations":11},{"max_tokens":0},{"max_seconds":float("nan")}])
def test_invalid_or_unbounded_loop_budgets_fail_before_transaction(repo,project,budget):
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    with pytest.raises(StudioError):OfflineLoop(repo,project,backend,ControlRenderer(repo),Critic(repo,case.Reviewer(response))).run(designed,**budget)
    assert not list((project.path/"work/transactions").iterdir())


def test_request_to_evidence_storyline_design_review_commit_pipeline(repo,project,monkeypatch):
    import json
    from orchestration import pipeline
    from evidence.store import EvidenceStore
    class Knowledge:
        def retrieve(self,*args,**kwargs):return []
    class Provider:
        last_usage={"tokens":100,"queries":0}
        def complete_with_images(self,prompt,schema,images):
            context=json.loads(prompt.split("REVIEW DATA=",1)[1])
            return {"schema_version":"1.0","dimensions":{key:100 for key in ["content_accuracy","narrative_clarity","visual_hierarchy","layout_integrity","brand_compliance","editability","source_integrity"]},"slides":[{"slide_id":s["slide_id"],"message_score":100,"observation":"Controlled complete integration review"} for s in context["slides"]],"findings":[]}
    source=project.path/"work/drivers.csv";source.write_text("driver,margin_loss_pp\nMaterials,4\nLabor,1\n",encoding="utf-8")
    store=EvidenceStore(repo,project);ingested=store.ingest(source,units={"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},data_period="2025")
    cells={node["locator"]:key for key,node in store.load().value["nodes"].items()}
    brief=read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json")["brief"];brief["constraints"]["sources_required"]=True;brief["page_budget"]=4
    request={"brief":brief,"sources":[{"path":str(source),"units":{"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},"data_period":"2025"}],"reasoning":{"strategy":"driver","coverage_keys":["diagnosis","response"],"analysis":{"type":"driver_diagnosis","attribution_status":"verified_driver_contribution","drivers":[{"name_evidence_id":cells[f"row:{i}/column:driver"],"impact_evidence_id":cells[f"row:{i}/column:margin_loss_pp"]} for i in [2,3]]}}}
    monkeypatch.setattr(pipeline,"KnowledgeStore",lambda root:Knowledge())
    monkeypatch.setattr(pipeline,"NativeRenderer",ControlRenderer)
    result=pipeline.OfflinePipeline(repo,project,Provider()).execute(request)
    assert result["passed"] and project.state()["generation"]==1 and (project.path/"state/storyline_graph.json").exists()


def test_axis_repair_changes_only_chart_part_and_protects_workbook_values(repo,project):
    from presentation.backends.xml import parse,serialize
    from presentation.backends.business_inspection import C
    from qa.exhibits import data_exhibits
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    source=project.path/"work/critic_fixture.pptx";package=backend._read(source)
    frame=next(o for o in backend.inspect(source)["slides"][1]["objects"] if o.get("content_type")=="chart");part=frame["chart_part"]
    chart=parse(package[part][1]);chart.find(".//c:catAx/c:crosses",C).set("val","max")
    package[part]=(package[part][0],serialize(chart));bad=project.path/"work/axis_corruption.pptx";backend._write(package,bad)
    before=backend.inspect(bad);frame=next(o for o in before["slides"][1]["objects"] if o.get("content_type")=="chart")
    proof=ControlRenderer(repo).render(bad,project.path/"work/axis_control")
    assert any(row["code"]=="CHART_ORIGIN_NOT_ZERO" for row in data_exhibits(designed["slides"],context,before,proof))
    patch={"schema_version":"1.1","patch_id":"axis","operations":[{"slide_id":before["slides"][1]["slide_id"],"object_id":frame["object_id"],"operation":"repair_chart_axis","value":"zero_origin","expected_fingerprint":frame["fingerprint"]}]}
    output=project.path/"work/axis_repaired.pptx";outcome=backend.patch(bad,output,patch,scope)
    assert outcome["changed_parts"]==[part] and outcome["changed_targets"]
    assert frame["fingerprint"]!=next(o["fingerprint"] for o in backend.inspect(output)["slides"][1]["objects"] if o["object_id"]==frame["object_id"])
    after_package=backend._read(output)
    assert all(after_package[name][1]==package[name][1] for name in package if name!=part)
    assert next(o["chart_data"][0]["values"] for o in backend.inspect(output)["slides"][1]["objects"] if o.get("content_type")=="chart")==[4,1]


def test_analytical_refresh_regenerates_current_claims_and_keeps_stable_slide_ids(repo,project):
    from orchestration.analytical import AnalyticalRefresh
    from evidence.store import EvidenceStore
    from reasoning.strategies import DriverReasoningStrategy
    designed,context,backend,compiler,scope,response=prepare(repo,project)
    source=project.path/"work/critic_fixture.pptx";store=EvidenceStore(repo,project);record=next(iter(store.load().value["sources"].values()))
    original=Path(record["original_path"]);original.write_text(original.read_text().replace("Materials,4","Materials,2"),encoding="utf-8")
    cells={row["locator"]:key for key,row in store.load().value["nodes"].items() if row["type"]=="raw_fact"}
    class Knowledge:
        def retrieve(self,*args,**kwargs):return []
    reasoning={"coverage_keys":["diagnosis","response"],"evidence_ids":record["evidence_ids"],"analysis":{"type":"driver_diagnosis","attribution_status":"verified_driver_contribution","drivers":[{"name_evidence_id":cells[f"row:{i}/column:driver"],"impact_evidence_id":cells[f"row:{i}/column:margin_loss_pp"]} for i in [2,3]]}}
    intent={"relationship":"ranking","category_evidence_ids":[cells[f"row:{i}/column:driver"] for i in [2,3]],"series":[{"name":"Recorded margin loss","evidence_ids":[cells[f"row:{i}/column:margin_loss_pp"] for i in [2,3]]}],"unit":"percentage points","period":"2025"}
    result=AnalyticalRefresh(repo,project,Knowledge(),strategy=DriverReasoningStrategy()).prepare(designed,[record["source_id"]],reasoning,{"a1":intent})
    revised=result["spec"];updated=EvidenceContext(store.load(),project.policy)
    assert revised["deck"]["deck_id"]==designed["deck"]["deck_id"] and revised["deck"]["slide_ids"]==designed["deck"]["slide_ids"]
    assert all(updated.graph.resolve(key)["status"]=="current" for s in revised["slides"] for key in s["claim_ids"])
    output=project.path/"work/refreshed.pptx"
    IncrementalCompiler(repo,compiler).compile(source,output,designed,revised,updated,result["changed_evidence_ids"],scope)
    assert next(o["chart_data"][0]["values"] for o in backend.inspect(output)["slides"][1]["objects"] if o.get("content_type")=="chart")==[2,1]
