"""Nonempty controlled reasoning benchmark; assertions are independent business expectations."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from evidence.store import EvidenceStore
from reasoning.engine import ReasoningEngine
from reasoning.strategies import DriverReasoningStrategy
from state.project import Project
from state.io import read_json


class NoKnowledge:
    def retrieve(self,*args,**kwargs):return []


def evaluate(repository,first,second,expected_focus,expected_hypothesis,**options):
    project=Project.create(repository,"bench-"+uuid4().hex[:12])
    source=project.path/"work/drivers.csv"
    source.write_text(f"driver,margin_loss_pp\nMaterials,{first}\nLabor,{second}\n",encoding="utf-8")
    store=EvidenceStore(repository,project)
    ingested=store.ingest(source,units={"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},data_period="2025")
    graph=store.load();locators={row["locator"]:key for key,row in graph.value["nodes"].items()}
    brief=read_json(repository/"tests/fixtures/basic_spec.json")["brief"]
    brief["decision_required"]="Which margin recovery action should management prioritize?";brief["page_budget"]=4
    analysis={"type":"driver_diagnosis","attribution_status":"verified_driver_contribution","drivers":[{"name_evidence_id":locators[f"row:{row}/column:driver"],"impact_evidence_id":locators[f"row:{row}/column:margin_loss_pp"]} for row in [2,3]]}
    result=ReasoningEngine(repository,project,NoKnowledge(),strategy=DriverReasoningStrategy()).reason(brief,["diagnosis","response"],ingested["evidence_ids"],appendix_budget=1,analysis=analysis)
    story=result["storyline"]
    checks={"decision_focus":expected_focus in story["core_answer"]["text"],"hypothesis_revises":story["hypotheses"][0]["status"]==expected_hypothesis,"source_trace":all(graph.resolve(assertion["evidence_id"])["value"]==assertion["displayed"] for argument in story["arguments"] for assertion in argument["numeric_assertions"]),"conditional_recommendation":any("require further validation" in assumption for assumption in story["recommendations"][0]["assumptions"]),"answer_first":result["plan"]["main"][0]["role"]=="executive_summary","page_budget":len(result["plan"]["main"])+len(result["plan"]["appendix"])<=4,"qa":result["qa"]["passed"]}
    score=100*sum(checks.values())/len(checks)
    return {"passed":all(checks.values()) and score>=90,"score":score,"checks":checks,"project_id":project.path.name,"core_answer":story["core_answer"]["text"]}


def cases(repository):
    def materials_led_decline():return evaluate(repository,4,1,"Materials","supported")
    def labor_led_decline():return evaluate(repository,1,3,"Labor","supported")
    def tied_drivers_disprove_single_winner():return evaluate(repository,2,2,"joint Materials and Labor","refuted")
    return [materials_led_decline,labor_led_decline,tied_drivers_disprove_single_winner]
