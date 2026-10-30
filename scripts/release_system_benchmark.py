"""Resumable controlled multi-industry full-system cases with actual native/model gates."""
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from evidence.store import EvidenceStore
from orchestration.pipeline import OfflinePipeline
from orchestration.offline import OfflineLoop
from knowledge.store import KnowledgeStore
from presentation.backends.ooxml import OOXMLBackend
from presentation.rendering.native import NativeRenderer
from qa.critic import Critic
from research.provider import CodexProvider
from state.io import read_json,write_json,sha256
from state.project import Project

CASES=[{"industry":"manufacturing","drivers":[["Materials",4],["Labor",1]],"focus":"Materials","hypothesis":"supported"},{"industry":"retail","drivers":[["Merchandise",3],["Fulfillment",3]],"focus":"joint Merchandise and Fulfillment","hypothesis":"refuted"},{"industry":"financial_services","drivers":[["Credit losses",7],["Funding efficiency",-2]],"focus":"Credit losses","hypothesis":"supported"}]


def prepare(case):
    project=Project.create(ROOT,"release-"+case["industry"]+"-"+uuid4().hex[:8])
    source=project.path/"work/attributed_drivers.csv"
    source.write_text("driver,margin_loss_pp\n"+"".join(f"{name},{value}\n" for name,value in case["drivers"]),encoding="utf-8")
    metadata={"units":{"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},"data_period":"2025"}
    store=EvidenceStore(ROOT,project);ingested=store.ingest(source,**metadata)
    locators={row["locator"]:key for key,row in store.load().value["nodes"].items()}
    driver_ids=[{"name_evidence_id":locators[f"row:{row}/column:driver"],"impact_evidence_id":locators[f"row:{row}/column:margin_loss_pp"]} for row in [2,3]]
    brief=read_json(ROOT/"tests/fixtures/basic_spec.json")["brief"]
    brief.update(brief_id="release-"+case["industry"],page_budget=4,decision_required="Which recorded margin-loss driver should "+case["industry"].replace("_"," ")+" management review first?",objective="Controlled synthetic benchmark: validate attributed contributions and conditional decision priority, not executable savings")
    brief["constraints"]["sources_required"]=True
    request={"brief":brief,"sources":[{"path":str(source),**metadata}],"reasoning":{"strategy":"driver","coverage_keys":["diagnosis","response"],"evidence_ids":ingested["evidence_ids"],"appendix_budget":0,"analysis":{"type":"driver_diagnosis","attribution_status":"verified_driver_contribution","drivers":driver_ids}},"exhibit_intents":{"a1":{"relationship":"ranking","category_evidence_ids":[r["name_evidence_id"] for r in driver_ids],"series":[{"name":"Recorded margin loss","evidence_ids":[r["impact_evidence_id"] for r in driver_ids]}],"unit":"percentage points","period":"2025"}},"budgets":{"max_iterations":3,"max_tokens":192000,"max_seconds":900}}
    write_json(project.path/"state/release_benchmark_request.json",request)
    return {"industry":case["industry"],"project_id":project.path.name,"fixture":True,"source_sha256":sha256(source),"status":"prepared"}


def main():
    path=ROOT/"implementation/PHASE_REPORTS/phase_11_system_cases.json"
    report=read_json(path) if path.exists() else {"schema_version":"1.0","passed":False,"cases":[]}
    for case in CASES:
        row=next((r for r in report["cases"] if r["industry"]==case["industry"]),None)
        if row is None:row=prepare(case);report["cases"].append(row);write_json(path,report)
        project=Project.open(ROOT,row["project_id"]);request=read_json(project.path/"state/release_benchmark_request.json")
        if sha256(Path(request["sources"][0]["path"]))!=row["source_sha256"]:raise ValueError("Controlled source changed")
        if row.get("passed"):
            if sha256(project.canonical)!=row["candidate_sha256"]:raise ValueError("Previously accepted canonical changed")
            continue
        if row.get("checks",{}).get("evidence_grounding") is False and "quality_patch" not in row:
            prior=read_json(project.path/"work/offline_runs"/row["run_id"]/"run.json")
            spec=read_json(project.path/"work/offline_runs"/row["run_id"]/prior["spec"])
            inspection=OOXMLBackend(ROOT).inspect(project.canonical)
            slide=next(s for s in inspection["slides"] if next(d for d in spec["slides"] if d["slide_id"]==s["slide_id"])["exhibit"]["type"]=="recommendation")
            target=next(obj for obj in slide["objects"] if obj["role"]=="body")
            patch={"schema_version":"1.0","patch_id":"clarify_proposed_analysis","operations":[{"slide_id":slide["slide_id"],"object_id":target["object_id"],"expected_fingerprint":target["fingerprint"],"operation":"set_text","value":"Recorded contributions inform priority; proposed actions require validation before approval."}]}
            scope={"objects":[{"slide_id":s["slide_id"],"object_id":obj["object_id"],"protection":"MAY_CHANGE" if (s["slide_id"],obj["object_id"])==(slide["slide_id"],target["object_id"]) else "MUST_NOT_CHANGE"} for s in inspection["slides"] for obj in s["objects"]]}
            row["prior_attempts"]=[{key:value for key,value in row.items()}]
            row["quality_patch"]={"run_id":uuid4().hex,"spec":spec,"scope":scope,"patch":patch};write_json(path,report)
        run_ids=list((project.path/"work/offline_runs").glob("*/run.json"))
        resume=run_ids[0].parent.name if len(run_ids)==1 else None
        if len(run_ids)>1 and "quality_patch" not in row:raise ValueError("Ambiguous benchmark resume")
        provider=CodexProvider(ROOT,240)
        started=time.monotonic()
        if "quality_patch" in row:
            planned=row["quality_patch"]
            loop=OfflineLoop(ROOT,project,OOXMLBackend(ROOT),NativeRenderer(ROOT),Critic(ROOT,provider,KnowledgeStore(ROOT)))
            result=loop.run(planned["spec"],scope=planned["scope"],initial_patch=planned["patch"],run_id=planned["run_id"],**request["budgets"])
        else:result=OfflinePipeline(ROOT,project,provider).execute(request,run_id=resume)
        write_json(project.path/"output/qa/release_system_result.json",result)
        if not result["passed"]:
            row.update(status="failed",result=result);write_json(path,report);return 1
        state=result["state"];review=Path(state["history"][-1]["review_directory"])
        critic=read_json(review/"critic_report.json");native=read_json(review/"render_report.json")
        story=read_json(project.path/"state/storyline_graph.json");spec=read_json(project.path/"state/offline_prepared_spec.json")
        actual=[value for slide in native["slides"] for obj in slide["shapes"] for series in obj.get("chart_series",[]) for value in series["values"]]
        expected=[value for _,value in case["drivers"]]
        checks={"numerical_correctness":sorted(actual)==sorted(expected),"evidence_grounding":critic["dimensions"]["content_accuracy"]>=90 and critic["dimensions"]["source_integrity"]>=90,"reasoning_storyline":case["focus"] in story["core_answer"]["text"] and story["hypotheses"][0]["status"]==case["hypothesis"] and read_json(project.path/"output/qa/narrative_qa.json")["passed"],"exhibit_selection":spec["slides"][1]["exhibit"]["type"]=="bar","visual_quality":critic["passed"] and critic["score"]>=90,"source_citation_compliance":all(slide["source_note_ids"] for slide in spec["slides"]),"hard_failure_rules":not critic["errors"] and state["history"][-1]["qa_passed"],"canonical_commit":sha256(project.canonical)==state["candidate_sha256"],"bounded":state["iteration"]<=3 and state["tokens"]<=192000 and state["elapsed_seconds"]<=900}
        replay=loop.run(planned["spec"],scope=planned["scope"],initial_patch=planned["patch"],run_id=planned["run_id"],**request["budgets"]) if "quality_patch" in row else OfflinePipeline(ROOT,project,CodexProvider(ROOT,240)).execute(request,run_id=result["run_id"])
        checks["cached_replay"]=replay["passed"] and replay["no_op"] and replay["state"]["tokens"]==state["tokens"]
        scores={key:100 if passed else 0 for key,passed in checks.items()}
        scores["visual_quality"]=critic["score"]
        row.update(status="complete",passed=all(checks.values()),checks=checks,scores=scores,critic_dimensions=critic["dimensions"],candidate_sha256=state["candidate_sha256"],run_id=result["run_id"],tokens=state["tokens"],elapsed_seconds=time.monotonic()-started,monetary_cost_usd=state["cost_usd"] if state.get("cost_telemetry_known") else None,review_directory=str(review),source_values=expected)
        write_json(path,report);print({"industry":case["industry"],"passed":row["passed"],"score":critic["score"],"tokens":state["tokens"]},flush=True)
        if not row["passed"]:return 1
    report["passed"]=len(report["cases"])==len(CASES) and all(row["passed"] for row in report["cases"])
    write_json(path,report);return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
