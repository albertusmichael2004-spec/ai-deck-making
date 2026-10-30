import copy
from pathlib import Path
from uuid import uuid4

import pytest

from layout.baseline import BaselineLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.rendering.native import NativeRenderer
from presentation.rendering.preview import contact_sheet
from qa.deterministic import DeterministicQA
from qa.regression import pixel_compare
from qa.transaction import PresentationValidator
from state.errors import StudioError
from state.io import fingerprint, read_json, sha256


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def native_case():
    output = ROOT / "runtime/native_tests" / uuid4().hex
    output.mkdir(parents=True)
    spec = read_json(ROOT / "tests/fixtures/basic_spec.json")
    backend = OOXMLBackend(ROOT)
    compiler = PresentationCompiler(ROOT, BaselineLayout(ROOT), backend)
    return output, spec, backend, compiler, NativeRenderer(ROOT)


def test_real_native_render_and_approved_golden_regression(native_case):
    output, spec, backend, compiler, renderer = native_case
    source = output / "source.pptx"
    compiler.compile(spec["brief"],spec["deck"],spec["slides"],source)
    before = fingerprint(source)
    result = renderer.render(source,output/"renders")
    assert result["renderer"] == "WindowsPowerPoint" and len(result["slides"]) == 2
    assert before == fingerprint(source)
    assert DeterministicQA(ROOT).check(backend.inspect(source),result)["passed"]
    contact_sheet(result,output/"preview.png")
    manifest = read_json(ROOT/"tests/golden/baseline/manifest.json")
    assert manifest["approved"] and manifest["renderer"] == result["renderer"]
    assert sha256(ROOT/"tests/golden/baseline/input.pptx") == manifest["input_sha256"]
    assert sha256(ROOT/"tests/fixtures/basic_spec.json") == manifest["spec_sha256"]
    for slide in result["slides"]:
        baseline = ROOT/"tests/golden/baseline"/f"slide_{slide['index']:03}.png"
        comparison = pixel_compare(baseline,Path(slide["render"]),manifest["pixel_tolerance"],manifest["changed_fraction_limit"])
        assert comparison["passed"], comparison


def test_real_native_overflow_is_rejected_and_candidate_is_not_committed(native_case,project):
    output,spec,backend,compiler,renderer=native_case
    original = project.begin()
    compiler.compile(spec["brief"],spec["deck"],spec["slides"],project.candidate(original))
    project.commit(original,backend.validate)
    canonical = fingerprint(project.canonical)
    candidate = project.begin()
    invalid = copy.deepcopy(spec)
    invalid["slides"][0]["objects"]=[{"object_id":"overflow","kind":"text","role":"title","text":"A very long title " * 80,"x":.5,"y":.5,"width":2,"height":.3,"font_pt":28,"protection":"MAY_CHANGE"}]
    compiler.compile(invalid["brief"],invalid["deck"],invalid["slides"],project.candidate(candidate))
    validator=PresentationValidator(ROOT,backend,renderer,output/"overflow_renders")
    with pytest.raises(StudioError):project.commit(candidate,validator)
    qa=read_json(output/"overflow_renders/qa_report.json")
    assert "TEXT_OVERFLOW" in {item["code"] for item in qa["errors"]}
    assert fingerprint(project.canonical)==canonical


def test_real_rendered_validation_commits_only_after_qa(native_case,project):
    output,spec,backend,compiler,renderer=native_case
    transaction=project.begin()
    compiler.compile(spec["brief"],spec["deck"],spec["slides"],project.candidate(transaction))
    validator=PresentationValidator(ROOT,backend,renderer,output/"validated_renders")
    state=project.commit(transaction,validator)
    assert state["generation"]==1
    assert read_json(output/"validated_renders/qa_report.json")["passed"]
