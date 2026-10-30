from copy import deepcopy
import zipfile
import pytest
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Inches
from presentation.backends.ooxml import OOXMLBackend
from presentation.backends.xml import NS, parse
from presentation.backends.chart_mutations import C
from presentation.rendering.diagnostics import office_failure, occupied_instance
from state.errors import StudioError
from ir.validation import validate


def fixture(repo, project):
    deck=Presentation(); slide=deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(1), Inches(4), Inches(1))
    data=CategoryChartData(); data.categories=["2026","2029"]; data.add_series("Volume",[3,27])
    slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(6), Inches(4), data)
    source=project.path/"work/styles_source.pptx"; deck.save(source)
    backend=OOXMLBackend(repo); inspection=backend.inspect(source); slide=inspection["slides"][0]
    connector=next(o for o in slide["objects"] if o["kind"]=="cxnSp")
    chart=next(o for o in slide["objects"] if o.get("content_type")=="chart")
    def operation(obj, name, value):
        return {"slide_id":slide["slide_id"],"object_id":obj["object_id"],"expected_fingerprint":obj["fingerprint"],"operation":name,"value":value}
    patch={"schema_version":"1.2","patch_id":"styles","operations":[
        operation(connector,"connector_to_shape",{"geometry":{"x":1,"y":1,"width":3,"height":0.15}}),
        operation(connector,"set_gradient_fill",{"angle_deg":0,"stops":[{"position":0,"color":"123456"},{"position":1,"color":"abcdef"}]}),
        operation(chart,"set_chart_colors",{"series":[{"index":0,"color":"FF0000","points":[{"index":0,"color":"00FF00"},{"index":1,"color":"0000FF"}]}]})]}
    scope={"objects":[{"slide_id":slide["slide_id"],"object_id":o["object_id"],"protection":"MUST_CHANGE"} for o in slide["objects"]]}
    return backend, source, patch, scope, chart


def test_style_edit_preserves_values_workbook_and_unmodified_parts(repo,project):
    backend,source,patch,scope,chart=fixture(repo,project)
    output=project.path/"work/styles_output.pptx"; result=backend.patch(source,output,patch,scope)
    after=backend.inspect(output)["slides"][0]["objects"]
    frame=next(o for o in after if o["object_id"]==chart["object_id"])
    assert frame["chart_data"][0]["values"]==[3,27]
    assert frame["chart_data"][0]["categories"]==["2026","2029"]
    assert after[0]["kind"]=="sp" and after[0]["object_id"]==patch["operations"][0]["object_id"]
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        assert a.namelist()==b.namelist()
        assert all(a.read(n)==b.read(n) for n in a.namelist() if n not in result["changed_parts"])
        assert all(a.read(n)==b.read(n) for n in a.namelist() if n.endswith(".xlsx"))
        xml=parse(b.read(chart["chart_part"]))
        assert [n.text for n in xml.findall(".//c:numCache/c:pt/c:v",C)]==["3","27"]
        assert xml.find(".//c:ser/c:spPr/a:solidFill/a:srgbClr",C).get("val")=="FF0000"
        assert [n.get("val") for n in xml.findall(".//c:dPt/c:spPr/a:solidFill/a:srgbClr",C)]==["00FF00","0000FF"]
        slide=parse(b.read(next(n for n in result["changed_parts"] if n.startswith("ppt/slides/"))))
        assert [n.get("val") for n in slide.findall(".//a:gradFill/a:gsLst/a:gs/a:srgbClr",NS)]==["123456","ABCDEF"]


@pytest.mark.parametrize("case",["bad_stop","duplicate_series","bad_point","protected","stale","legacy","collapsed"])
def test_style_failure_never_writes_destination(repo,project,case):
    backend,source,patch,scope,chart=fixture(repo,project)
    if case=="bad_stop":patch["operations"][1]["value"]["stops"][1]["position"]=0
    if case=="duplicate_series":patch["operations"][2]["value"]["series"]*=2
    if case=="bad_point":patch["operations"][2]["value"]["series"][0]["points"][0]["index"]=99
    if case=="protected":scope["objects"][0]["protection"]="MUST_NOT_CHANGE"
    if case=="stale":patch["operations"][2]["expected_fingerprint"]="0"*64
    if case=="legacy":patch["schema_version"]="1.1"
    if case=="collapsed":patch["operations"][0]["value"]["geometry"]["height"]=1e-12
    output=project.path/"work/never_written.pptx"
    with pytest.raises(StudioError):backend.patch(source,output,patch,scope)
    assert not output.exists()


def test_patch_plan_can_carry_style_contract(repo,project):
    _,_,patch,scope,_=fixture(repo,project)
    validate(repo,"patch_plan",{"schema_version":"1.1","plan_id":"style","reason":"Apply requested palette","candidate_sha256":"0"*64,"patch":patch,"scope":scope,"analytical_evidence_ids":[]})


def test_office_errors_explain_recovery_and_do_not_change_ownership():
    exc=Exception(-2147352567,"Exception occurred",(0,"PowerPoint","Automation rights are not granted",None,0,-2147188160),None)
    row=office_failure(exc)
    assert row["reason"]=="office_automation_denied" and "cannot grant" in row["recovery_action"]
    assert occupied_instance(2)["open_presentations"]==2
    assert "Save and close" in occupied_instance(2)["recovery_action"]
