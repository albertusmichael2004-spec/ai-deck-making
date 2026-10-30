from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from reasoning.engine import ReasoningEngine
from reasoning.mece import check_mece
from reasoning.narrative import narrative_qa
from state.errors import StudioError,ErrorCode
from state.io import fingerprint,read_json

spec=importlib.util.spec_from_file_location("reasoning_case",Path(__file__).parents[1]/"fixtures/reasoning_case.py")
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)


def test_storyline_answer_first_lineage_summary_and_page_budget(repo,project):
    request,story,store=case.prepare(repo,project)
    provider=case.Provider(story)
    result=ReasoningEngine(repo,project,case.Knowledge(),provider).reason(**request)
    assert result["qa"]["passed"]
    assert result["plan"]["main"][0]["role"]=="executive_summary"
    assert len(result["plan"]["main"])+len(result["plan"]["appendix"])<=request["brief"]["page_budget"]
    assert result["plan"]["appendix"]
    assert result["plan"]["executive_summary"][0]["text"]==story["arguments"][0]["claim"]
    graph=store.load()
    recommendation=graph.resolve(result["lineage"]["recommendation_ids"]["r1"])
    assert recommendation["type"]=="recommendation" and recommendation["assumptions"]
    assert any(row["type"]=="raw_fact" for row in graph.trace(recommendation["evidence_id"]))
    assert "UNTRUSTED PROJECT EVIDENCE" in provider.prompts[0]


@pytest.mark.parametrize("change,code",[("number","numeric_contradiction"),("overlap","overlapping_issue_coverage"),("unsupported","recommendation_without_support"),("summary","core_answer_inconsistent"),("duplicate","repeated_slide_message"),("topic","topic_title_without_assertion"),("hypothesis","hypothesis_unproven")])
def test_narrative_rejects_material_defects_without_persisting(repo,project,change,code):
    request,story,store=case.prepare(repo,project)
    if change=="number":story["arguments"][0]["numeric_assertions"][0]["displayed"]="99"
    if change=="overlap":story["issues"][1]["coverage_keys"]=["diagnosis"]
    if change=="unsupported":story["recommendations"][0]["argument_ids"].append("missing")
    if change=="summary":story["core_answer"]["text"]="Cut labor first."
    if change=="duplicate":story["arguments"][1]["action_title"]=story["arguments"][0]["action_title"]
    if change=="topic":story["arguments"][0]["action_title"]="Financial analysis"
    if change=="hypothesis":story["hypotheses"][0]["evidence_ids"]=[]
    before=fingerprint(store.path)
    with pytest.raises(StudioError) as error:ReasoningEngine(repo,project,case.Knowledge(),case.Provider(story)).reason(**request)
    assert error.value.code==ErrorCode.QA_FAILURE
    assert any(row["code"]==code for row in error.value.details["findings"])
    assert fingerprint(store.path)==before
    assert not (project.path/"state/storyline_graph.json").exists()


def test_mece_cycle_and_missing_coverage_and_stale_evidence(repo,project):
    request,story,store=case.prepare(repo,project)
    issues=deepcopy(story["issues"]);issues[0]["parent_id"]="i2";issues[1]["parent_id"]="i1"
    assert "issue_tree_cycle" in check_mece(issues,request["coverage_keys"])
    graph=store.load();graph.value["nodes"][request["evidence_ids"][0]]["status"]="stale";store.save(graph)
    with pytest.raises(StudioError) as error:ReasoningEngine(repo,project,case.Knowledge(),case.Provider(story)).reason(**request)
    assert error.value.code==ErrorCode.RESEARCH_INCOMPLETE


def test_evidence_concurrency_rejects_stale_reasoning(repo,project):
    request,story,store=case.prepare(repo,project)
    class Concurrent(case.Provider):
        def complete(self,*args):
            graph=store.load();graph.value["nodes"][request["evidence_ids"][0]]["confidence"]=.99;store.save(graph)
            return super().complete(*args)
    with pytest.raises(StudioError) as error:ReasoningEngine(repo,project,case.Knowledge(),Concurrent(story)).reason(**request)
    assert error.value.code==ErrorCode.FILE_CONFLICT


def test_provider_schema_projection_never_relaxes_local_uniqueness(repo,project):
    from research.provider import provider_schema
    request,story,store=case.prepare(repo,project)
    schema=read_json(repo/"schemas/storyline_graph/1.0.json")
    projected=provider_schema(schema)
    assert "uniqueItems" not in projected["$defs"]["ids"] and schema["$defs"]["ids"]["uniqueItems"]
    story["core_answer"]["argument_ids"].append("a1")
    with pytest.raises(StudioError) as error:ReasoningEngine(repo,project,case.Knowledge(),case.Provider(story)).reason(**request)
    assert error.value.code==ErrorCode.DATA_VALIDATION_ERROR
