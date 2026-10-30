"""Measured independent image review using only a repository-owned fixture."""
import sys
import argparse
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]

from evidence.context import EvidenceContext
from evidence.store import EvidenceStore
from knowledge.store import KnowledgeStore
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from presentation.rendering.native import NativeRenderer
from qa.critic import Critic
from qa.transaction import PresentationValidator
from reasoning.engine import ReasoningEngine
from reasoning.strategies import DriverReasoningStrategy
from research.provider import CodexProvider
from state.io import read_json,write_json
from state.project import Project
from state.errors import StudioError


def main(resume=None):
    if resume:
        project=Project.open(ROOT,resume);store=EvidenceStore(ROOT,project);spec=read_json(project.path/"state/design_spec.json");candidate=project.path/"work/critic_candidate.pptx";directory=project.path/"output/qa/critic_live";backend=OOXMLBackend(ROOT);context=EvidenceContext(store.load(),project.policy)
        review=Critic(ROOT,CodexProvider(ROOT,180),KnowledgeStore(ROOT)).evaluate(spec,candidate,backend.inspect(candidate),read_json(directory/"render_report.json"),context,output=directory/("critic_report_"+uuid4().hex+".json"))
        result={"passed":review["passed"],"project_id":project.path.name,"native_qa":read_json(directory/"qa_report.json")["passed"],"review":review,"model_context_isolated":True,"fixture":True}
        write_json(ROOT/"implementation/PHASE_REPORTS/phase_8_live_smoke.json",result);print(result);return 0 if result["passed"] else 1
    project=Project.create(ROOT,"critic-smoke-"+uuid4().hex[:10])
    source=project.path/"work/drivers.csv";source.write_text("driver,margin_loss_pp\nMaterials,4\nLabor,1\n",encoding="utf-8")
    store=EvidenceStore(ROOT,project);ingested=store.ingest(source,units={"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},data_period="2025");graph=store.load();cells={node["locator"]:key for key,node in graph.value["nodes"].items()}
    brief=read_json(ROOT/"tests/fixtures/basic_spec.json")["brief"];brief.update(audience="Finance and operating leaders",objective="Recommend a conditional diagnostic priority from supplied verified margin-loss contributions.",decision_required="Which margin recovery action should management prioritize?",page_budget=4);brief["constraints"]["sources_required"]=True
    drivers=[{"name_evidence_id":cells[f"row:{row}/column:driver"],"impact_evidence_id":cells[f"row:{row}/column:margin_loss_pp"]} for row in [2,3]]
    ReasoningEngine(ROOT,project,KnowledgeStore(ROOT),strategy=DriverReasoningStrategy()).reason(brief,["diagnosis","response"],ingested["evidence_ids"],analysis={"type":"driver_diagnosis","attribution_status":"verified_driver_contribution","drivers":drivers})
    exhibit={"relationship":"ranking","category_evidence_ids":[row["name_evidence_id"] for row in drivers],"series":[{"name":"Recorded margin loss","evidence_ids":[row["impact_evidence_id"] for row in drivers]}],"unit":"percentage points","period":"2025"}
    spec=DesignPlanner(ROOT,project).plan(brief,{"a1":exhibit});backend=OOXMLBackend(ROOT);context=EvidenceContext(store.load(),project.policy);candidate=project.path/"work/critic_candidate.pptx"
    PresentationCompiler(ROOT,AdaptiveLayoutCompiler(ROOT),backend).compile(**spec,destination=candidate,evidence=context)
    directory=project.path/"output/qa/critic_live";qa=PresentationValidator(ROOT,backend,NativeRenderer(ROOT),directory,evidence=context,slide_specs=spec["slides"])(candidate)
    if not qa["passed"]:raise ValueError("Native prerequisite failed: "+str(qa))
    review=Critic(ROOT,CodexProvider(ROOT,180),KnowledgeStore(ROOT)).evaluate(spec,candidate,backend.inspect(candidate),read_json(directory/"render_report.json"),context,output=directory/"critic_report.json")
    result={"passed":review["passed"],"project_id":project.path.name,"native_qa":qa["passed"],"review":review,"model_context_isolated":True,"fixture":True}
    write_json(ROOT/"implementation/PHASE_REPORTS/phase_8_live_smoke.json",result)
    print({"passed":result["passed"],"project_id":project.path.name,"score":review["score"],"usage":review["usage"],"findings":review["issues"]})
    return 0 if result["passed"] else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--project");args=parser.parse_args()
    try:raise SystemExit(main(args.project))
    except StudioError as exc:
        result={"passed":False,"error":exc.as_dict()};write_json(ROOT/"implementation/PHASE_REPORTS/phase_8_live_smoke.json",result);print(result);raise SystemExit(1)
