import copy
from pathlib import Path

from PIL import Image

from qa.deterministic import DeterministicQA
from qa.regression import pixel_compare, protected_scope
from state.io import read_json


def native_fixture():
    obj = {"object_id":"title","native_id":"2","kind":"sp","role":"title","text":"Title","fingerprint":"a"}
    native = {"native_id":2,"x_pt":36,"y_pt":36,"width_pt":500,"height_pt":72,"text_bounds_pt":{"width":100,"height":34},"margins_pt":{"left":0,"right":0,"top":0,"bottom":0},"runs":[{"font_pt":28,"font_name":"Arial"}],"line_count":1}
    inspection = {"slides":[{"slide_id":"s01","objects":[obj]}]}
    rendered = {"passed":True,"canvas_pt":{"width":960,"height":540},"slides":[{"shapes":[native]}]}
    return inspection, rendered


def test_native_geometry_overflow_font_and_title_rules(repo):
    qa = DeterministicQA(repo)
    inspection, native = native_fixture()
    assert qa.check(inspection,native)["passed"]
    for field, value, code in [("x_pt",-20,"OUT_OF_BOUNDS"),("text_bounds_pt",{"width":100,"height":100},"TEXT_OVERFLOW"),("runs",[{"font_pt":8}],"FONT_TOO_SMALL"),("line_count",3,"TITLE_TOO_MANY_LINES")]:
        changed = copy.deepcopy(native);changed["slides"][0]["shapes"][0][field]=value
        result=qa.check(inspection,changed)
        assert not result["passed"] and code in {i["code"] for i in result["errors"]}


def test_missing_real_metrics_fails_honestly(repo):
    inspection,rendered=native_fixture();rendered["slides"][0]["shapes"][0].pop("text_bounds_pt")
    assert not DeterministicQA(repo).check(inspection,rendered)["passed"]
    rendered["slides"]=[]
    assert not DeterministicQA(repo).check(inspection,rendered)["passed"]


def test_planned_overlap_and_image_stretch(repo):
    inspection,native=native_fixture()
    second=copy.deepcopy(inspection["slides"][0]["objects"][0]);second.update(object_id="image",native_id="3",kind="pic",role=None,text="")
    inspection["slides"][0]["objects"].append(second)
    shape=copy.deepcopy(native["slides"][0]["shapes"][0]);shape.update(native_id=3,width_pt=200,height_pt=100)
    native["slides"][0]["shapes"].append(shape)
    qa=DeterministicQA(repo)
    assert not qa.check(inspection,native)["passed"]
    assert qa.check(inspection,native,allowed_overlaps=[("title","image")])["passed"]
    assert not qa.check(inspection,native,allowed_overlaps=[("title","image")],image_ratios=[{"slide_id":"s01","object_id":"image","expected_ratio":1}])["passed"]


def test_scope_and_visual_regression(repo):
    original,_=native_fixture();changed=copy.deepcopy(original);changed["slides"][0]["objects"][0]["fingerprint"]="b"
    assert not protected_scope(original,changed,{"objects":[]})["passed"]
    assert protected_scope(original,changed,{"objects":[{"slide_id":"s01","object_id":"title","protection":"MAY_CHANGE"}]})["passed"]
    before,after=repo/"runtime/before.png",repo/"runtime/after.png"
    Image.new("RGB",(100,100),"white").save(before);Image.new("RGB",(100,100),"white").save(after)
    assert pixel_compare(before,after,2,.001)["passed"]
    Image.new("RGB",(100,100),"black").save(after)
    assert not pixel_compare(before,after,2,.001)["passed"]
