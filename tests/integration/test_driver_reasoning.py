import importlib.util
from pathlib import Path

import pytest

from reasoning.strategies import DriverReasoningStrategy
from state.errors import StudioError


def test_reasoning_changes_with_evidence_and_preserves_ties(repo):
    # Controlled cases contain no benchmark answers in knowledge retrieval.
    source=Path(__file__).parents[1]/"fixtures/basic_spec.json"
    target=repo/"tests/fixtures/basic_spec.json";target.parent.mkdir(parents=True);target.write_bytes(source.read_bytes())
    path=Path(__file__).parents[1]/"benchmarks/reasoning_subset.py"
    spec=importlib.util.spec_from_file_location("driver_benchmark",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results=[case() for case in module.cases(repo)]
    assert all(row["passed"] and row["score"]>=90 for row in results)
    assert len({row["core_answer"] for row in results})==3


def test_offline_strategy_refuses_unverified_attribution():
    with pytest.raises(StudioError):DriverReasoningStrategy().propose({"analysis":{"type":"driver_diagnosis"},"coverage_keys":["diagnosis","response"]},{})


def test_verified_negative_offsets_keep_their_sign_in_narrative_checks(repo):
    path=Path(__file__).parents[1]/"benchmarks/reasoning_subset.py"
    spec=importlib.util.spec_from_file_location("signed_driver_case",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=Path(__file__).parents[1]/"fixtures/basic_spec.json"
    target=repo/"tests/fixtures/basic_spec.json";target.parent.mkdir(parents=True);target.write_bytes(source.read_bytes())
    result=module.evaluate(repo,7,-2,"Materials","supported");assert result["passed"]
    from state.project import Project
    from state.io import read_json
    from evidence.store import EvidenceStore
    from reasoning.narrative import narrative_qa
    project=Project.open(repo,result["project_id"]);story=read_json(project.path/"state/storyline_graph.json")
    story["arguments"][0]["claim"]=story["arguments"][0]["claim"].replace("-2","2")
    assert not narrative_qa(story,EvidenceStore(repo,project).load(),project.policy,["diagnosis","response"])["passed"]
