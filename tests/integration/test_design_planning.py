import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from reasoning.engine import ReasoningEngine
from state.errors import StudioError

spec=importlib.util.spec_from_file_location("design_case",Path(__file__).parents[1]/"fixtures/reasoning_case.py")
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)


def prepare(repo,project):
    request,story,store=case.prepare(repo,project)
    ReasoningEngine(repo,project,case.Knowledge(),case.Provider(story)).reason(**request)
    request["brief"]["constraints"]["sources_required"]=True
    graph=store.load();locators={node["locator"]:key for key,node in graph.value["nodes"].items() if node["type"]=="raw_fact"}
    intent={"relationship":"ranking","category_evidence_ids":[locators[f"row:{i}/column:driver"] for i in [2,3]],"series":[{"name":"Margin loss","evidence_ids":[locators[f"row:{i}/column:margin_loss_pp"] for i in [2,3]]}],"unit":"percentage points","period":"2025"}
    return request,store,intent


def test_answer_first_storyline_to_source_bound_deck_is_idempotent(repo,project):
    request,store,intent=prepare(repo,project)
    planner=DesignPlanner(repo,project)
    designed=planner.plan(request["brief"],{"a1":intent})
    assert designed==planner.plan(request["brief"],{"a1":intent})
    assert len(designed["slides"])<=request["brief"]["page_budget"]
    assert designed["slides"][0]["purpose"]=="executive_summary"
    assert designed["slides"][1]["exhibit"]["type"]=="bar"
    assert designed["slides"][2]["exhibit"]["type"]=="recommendation"
    assert "validation" in designed["slides"][2]["exhibit"]["items"][-2]["body"]
    context=EvidenceContext(store.load(),project.policy)
    output=project.path/"work/answer_first.pptx"
    inspected=PresentationCompiler(repo,AdaptiveLayoutCompiler(repo),OOXMLBackend(repo)).compile(**designed,destination=output,evidence=context)
    assert len(inspected["slides"])==3


def test_design_rejects_changed_lineage_and_conflicting_intents(repo,project):
    request,store,intent=prepare(repo,project)
    bad=deepcopy(intent);bad["type"]="pie"
    with pytest.raises(StudioError):DesignPlanner(repo,project).plan(request["brief"],{"a1":bad})
    graph=store.load();claim=next(node for node in graph.value["nodes"].values() if node["type"]=="interpretation");claim["text"]="Altered unsupported statement";store.save(graph)
    with pytest.raises(StudioError):DesignPlanner(repo,project).plan(request["brief"],{"a1":intent})
