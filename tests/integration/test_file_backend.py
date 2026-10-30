import copy
import io
import zipfile
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
from PIL import Image
from lxml import etree as ET

from ir.identity import object_id
from layout.baseline import BaselineLayout
from presentation.backends.ooxml import OOXMLBackend, NS
from presentation.compiler.compiler import PresentationCompiler
from state.errors import StudioError
from state.io import read_json, sha256


@pytest.fixture
def backend(repo): return OOXMLBackend(repo)


@pytest.fixture
def spec(): return read_json(Path(__file__).resolve().parents[1] / "fixtures/basic_spec.json")


def compile_deck(repo, backend, spec, output):
    return PresentationCompiler(repo, BaselineLayout(repo), backend).compile(spec["brief"], spec["deck"], spec["slides"], output)


def patch_for(slide, obj, value):
    return {"schema_version":"1.0","patch_id":"patch-test","operations":[{"slide_id":slide["slide_id"],"object_id":obj["object_id"],"operation":"set_text","expected_fingerprint":obj["fingerprint"],"value":value}]}


def scope_for(inspect, target):
    return {"objects":[{"slide_id":slide["slide_id"],"object_id":obj["object_id"],"protection":"MUST_CHANGE" if obj["object_id"]==target else "MUST_NOT_CHANGE"} for slide in inspect["slides"] for obj in slide["objects"]]}


def test_compiler_creates_editable_reopenable_powerpoint(repo, backend, spec):
    output = repo / "runtime/compiled.pptx"
    result = compile_deck(repo, backend, spec, output)
    deck = Presentation(output)
    assert len(deck.slides) == 2
    assert len(deck.slides[0].shapes) == 2
    assert deck.slides[0].shapes[0].text == spec["slides"][0]["action_title"]
    assert result["slides"][0]["objects"][0]["object_id"] == object_id("deck-test","s01","title")
    assert backend.validate(output)["passed"]
    assert not backend.validate(output)["rendered"]
    repeated = repo / "runtime/repeated.pptx"
    compile_deck(repo, backend, spec, repeated)
    assert backend.inspect(repeated)["slides"] == result["slides"]


def test_invalid_ir_and_unsupported_capabilities_fail_honestly(repo, backend, spec):
    for change in [lambda s:s["brief"].update(page_budget=1), lambda s:s["deck"].update(slide_ids=["s02","s01"]), lambda s:s["slides"][0].update(schema_version="2.0"), lambda s:s["slides"][0]["exhibit"].update(type="waterfall")]:
        invalid = copy.deepcopy(spec)
        change(invalid)
        with pytest.raises(StudioError): compile_deck(repo, backend, invalid, repo / "runtime/invalid.pptx")


def test_scoped_mutation_preserves_every_untouched_part(repo, backend, spec):
    original, output = repo / "runtime/original.pptx", repo / "runtime/edit.pptx"
    inspect = compile_deck(repo, backend, spec, original)
    slide, obj = inspect["slides"][0], inspect["slides"][0]["objects"][0]
    report = backend.patch(original, output, patch_for(slide,obj,"Revised title"), scope_for(inspect,obj["object_id"]))
    assert Presentation(output).slides[0].shapes[0].text == "Revised title"
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(output) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name not in report["changed_parts"]: assert before.read(name) == after.read(name), name
    after = backend.inspect(output)
    assert after["slides"][1] == inspect["slides"][1]
    assert after["slides"][0]["objects"][1] == inspect["slides"][0]["objects"][1]
    assert Presentation(original).slides[0].shapes[0].text != "Revised title"


def test_protected_and_stale_targets_block_mutation(repo, backend, spec):
    original, output = repo / "runtime/original.pptx", repo / "runtime/edit.pptx"
    inspect = compile_deck(repo, backend, spec, original)
    slide, obj = inspect["slides"][0], inspect["slides"][0]["objects"][0]
    patch = patch_for(slide,obj,"Revised")
    scope = scope_for(inspect,obj["object_id"])
    scope["objects"][0]["protection"] = "MUST_NOT_CHANGE"
    with pytest.raises(StudioError): backend.patch(original,output,patch,scope)
    assert not output.exists()
    patch["operations"][0]["expected_fingerprint"] = "0" * 64
    with pytest.raises(StudioError): backend.patch(original,output,patch,scope_for(inspect,obj["object_id"]))


def complex_fixture(path):
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    title = slide.shapes.add_textbox(Inches(.5),Inches(.5),Inches(8),Inches(1))
    title.text = "Original title"
    title.text_frame.paragraphs[0].runs[0].hyperlink.address = "https://example.com"
    group = slide.shapes.add_group_shape()
    child = group.shapes.add_textbox(Inches(1),Inches(2),Inches(3),Inches(1));child.text = "Protected grouped text"
    chart = CategoryChartData();chart.categories=["A","B"];chart.add_series("Revenue",[10,20])
    slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(5),Inches(2),Inches(3),Inches(2),chart)
    table = slide.shapes.add_table(2,2,Inches(1),Inches(4),Inches(3),Inches(1)).table;table.cell(0,0).text="Input"
    image=io.BytesIO();Image.new("RGB",(10,10),"red").save(image,format="PNG");image.seek(0)
    slide.shapes.add_picture(image,Inches(8),Inches(1),width=Inches(1))
    slide.notes_slide.notes_text_frame.text = "Preserve these speaker notes"
    deck.slides.add_slide(deck.slide_layouts[6])
    deck.save(path)
    with zipfile.ZipFile(path) as source: parts={i.filename:(i,source.read(i)) for i in source.infolist()}
    node=ET.fromstring(parts["ppt/slides/slide1.xml"][1])
    timing=ET.SubElement(node,f"{{{NS['p']}}}timing"); ET.SubElement(timing,f"{{{NS['p']}}}tnLst")
    info=parts["ppt/slides/slide1.xml"][0];parts["ppt/slides/slide1.xml"]=(info,ET.tostring(node))
    with zipfile.ZipFile(path,"w") as output:
        for info,payload in parts.values():output.writestr(info,payload)


def test_complex_roundtrip_keeps_charts_notes_media_masters_groups_links_animations(repo,backend):
    original,output=repo/"runtime/complex.pptx",repo/"runtime/edited.pptx"
    complex_fixture(original)
    inspection=backend.inspect(original);slide=inspection["slides"][0];title=slide["objects"][0]
    report=backend.patch(original,output,patch_for(slide,title,"Only title changes"),scope_for(inspection,title["object_id"]))
    with zipfile.ZipFile(original) as before,zipfile.ZipFile(output) as after:
        for name in before.namelist():
            if name not in report["changed_parts"]: assert before.read(name)==after.read(name)
        node=ET.fromstring(after.read(slide["part"]))
        assert node.find("p:timing/p:tnLst",NS) is not None
    deck=Presentation(output)
    assert deck.slides[0].shapes[0].text=="Only title changes"
    assert deck.slides[0].shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.address=="https://example.com"
    assert any(s.has_chart for s in deck.slides[0].shapes)
    assert "Preserve these" in deck.slides[0].notes_slide.notes_text_frame.text
    assert deck.slides[0].shapes[1].shapes[0].text=="Protected grouped text"


def test_group_protection_applies_to_descendant_edits(repo,backend):
    original,output=repo/"runtime/complex.pptx",repo/"runtime/edited.pptx"
    complex_fixture(original)
    inspection=backend.inspect(original);slide=inspection["slides"][0]
    group=next(obj for obj in slide["objects"] if obj["kind"]=="grpSp")
    child=next(obj for obj in slide["objects"] if obj["text"]=="Protected grouped text")
    with pytest.raises(StudioError):backend.patch(original,output,patch_for(slide,child,"Changed"),scope_for(inspection,child["object_id"]))
    assert not output.exists()


def test_backend_cannot_write_canonical_or_immutable_input(repo,backend,spec):
    for destination in [repo/"projects/demo/presentation/canonical.pptx",repo/"projects/demo/input/target/test.pptx",repo/"library/knowledge/packages/test.pptx"]:
        with pytest.raises(StudioError):compile_deck(repo,backend,spec,destination)


def test_native_geometry_and_fill_primitives(repo,backend,spec):
    original,output=repo/"runtime/original.pptx",repo/"runtime/edited.pptx"
    inspection=compile_deck(repo,backend,spec,original);slide=inspection["slides"][0];obj=slide["objects"][0]
    geometry={"x":.75,"y":.5,"width":10,"height":1}
    patch=patch_for(slide,obj,geometry);patch["operations"][0]["operation"]="set_geometry"
    fill=copy.deepcopy(patch["operations"][0]);fill.update(operation="set_fill",value="112233");patch["operations"].append(fill)
    backend.patch(original,output,patch,scope_for(inspection,obj["object_id"]))
    shape=Presentation(output).slides[0].shapes[0]
    assert shape.left==Inches(.75) and shape.width==Inches(10)
    assert str(shape.fill.fore_color.rgb)=="112233"


def test_same_canonical_deck_iterations_use_latest_state(project,repo,backend,spec):
    identifier=project.begin()
    compile_deck(repo,backend,spec,project.candidate(identifier));project.commit(identifier,backend.validate)
    snapshot=project.snapshot()
    for title in ["Iteration one","Iteration two"]:
        inspection=backend.inspect(project.canonical);slide=inspection["slides"][0];obj=slide["objects"][0]
        identifier=project.begin()
        backend.patch(project.canonical,project.candidate(identifier),patch_for(slide,obj,title),scope_for(inspection,obj["object_id"]))
        project.commit(identifier,backend.validate)
        assert Presentation(project.canonical).slides[0].shapes[0].text==title
    assert project.state()["generation"]==3
    project.rollback(snapshot,project.token())
    assert Presentation(project.canonical).slides[0].shapes[0].text==spec["slides"][0]["action_title"]
