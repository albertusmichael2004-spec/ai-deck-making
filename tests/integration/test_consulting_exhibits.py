import io
import importlib.util
import zipfile
from pathlib import Path
from copy import deepcopy

import pytest
from pptx import Presentation
from openpyxl import load_workbook

from layout.chart_selection import select_chart
from layout.consulting import ConsultingLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from state.errors import StudioError,ErrorCode
from state.io import sha256

spec=importlib.util.spec_from_file_location("consulting_case",Path(__file__).parents[1]/"fixtures/consulting_exhibits.py")
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)


def test_editable_charts_tables_diagrams_and_embedded_values(repo,project):
    brief,deck,slides,evidence,store=case.prepare(repo,project)
    output=project.path/"work/consulting.pptx"
    result=PresentationCompiler(repo,ConsultingLayout(repo),OOXMLBackend(repo)).compile(brief,deck,slides,output,evidence)
    assert len(result["slides"])==len(slides)
    actual=Presentation(io.BytesIO(output.read_bytes()))
    assert actual.slides[0].shapes[-1].has_chart
    assert list(actual.slides[0].shapes[-1].chart.series[0].values)==[-4,1]
    assert actual.slides[3].shapes[-1].has_table
    assert actual.slides[3].shapes[-1].table.cell(2,0).text=="Materials"
    with zipfile.ZipFile(output) as archive:
        books=[name for name in archive.namelist() if name.endswith(".xlsx")]
        assert len(books)==3
        workbook=load_workbook(io.BytesIO(actual.slides[0].shapes[-1].chart.part.chart_workbook.xlsx_part.blob),data_only=True)
        assert [workbook.active.cell(row,2).value for row in range(2,4)]==[-4,1]
        assert not any(name.startswith("ppt/media/") for name in archive.namelist())


def test_binding_units_endpoint_and_density_are_mandatory(repo,project):
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("waterfall",))
    output=project.path/"work/bad.pptx";compiler=PresentationCompiler(repo,ConsultingLayout(repo),OOXMLBackend(repo))
    wrong=deepcopy(slides);wrong[0]["exhibit"]["unit"]="USD"
    with pytest.raises(StudioError):compiler.compile(brief,deck,wrong,output,evidence)
    wrong=deepcopy(slides);wrong[0]["exhibit"]["series"][0]["evidence_ids"][-1]=wrong[0]["exhibit"]["series"][0]["evidence_ids"][0]
    with pytest.raises(StudioError):compiler.compile(brief,deck,wrong,output,evidence)
    wrong=deepcopy(slides);wrong[0]["key_message"]="dense "*100
    with pytest.raises(StudioError) as error:compiler.compile(brief,deck,wrong,output,evidence)
    assert error.value.code==ErrorCode.QA_FAILURE


def test_chart_selection_and_zero_crossing_waterfall_geometry():
    from presentation.backends.business_objects import waterfall_series
    assert select_chart("ranking")=="bar" and select_chart("association")=="scatter"
    assert select_chart("composition",categories=7)=="stacked_bar"
    values=waterfall_series([-1,2,-3,-2])
    assert values[2][1][1]==1 and values[3][1][1]==-1
    assert values[4][1][2]==1 and values[5][1][2]==-2


def test_source_association_rejects_swapped_labels(repo,project):
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bar",))
    slides[0]["exhibit"]["category_evidence_ids"].reverse()
    with pytest.raises(StudioError) as error:evidence.resolve_exhibit(slides[0])
    assert "verified source record" in str(error.value)


def test_template_style_parts_preserved_and_content_not_reused(repo,project):
    from presentation.backends.native_shapes import make_slide
    from presentation.backends.xml import NS,parse,serialize
    from state.io import atomic_bytes
    basic=case.read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json")
    backend=OOXMLBackend(repo);template=project.path/"work/company_template.pptx"
    from layout.baseline import BaselineLayout
    PresentationCompiler(repo,BaselineLayout(repo),backend).compile(basic["brief"],basic["deck"],basic["slides"],template)
    package=backend._read(template);master=parse(package["ppt/slideMasters/slideMaster1.xml"][1]);tree=master.find("p:cSld/p:spTree",NS)
    logo=make_slide({"slide_id":"logo","background":"FFFFFF","objects":[{"object_id":"brand-logo","kind":"text","role":"label","text":"ACME","x":11.8,"y":7.0,"width":1,"height":.3,"font_pt":12,"color":"172B4D"}]})
    tree.append(deepcopy(logo.find("p:cSld/p:spTree/p:sp",NS)))
    package["ppt/slideMasters/slideMaster1.xml"]=(package["ppt/slideMasters/slideMaster1.xml"][0],serialize(master));backend._write(package,template)
    original_hash=sha256(template)
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bar","table"))
    brief["constraints"]["use_existing_template"]=True;deck["schema_version"]="1.1";deck["template"]={"path":str(template),"layout_part":"ppt/slideLayouts/slideLayout7.xml"}
    output=project.path/"work/branded.pptx"
    result=PresentationCompiler(repo,ConsultingLayout(repo),backend).compile(brief,deck,slides,output,evidence)
    assert len(result["slides"])==2 and sha256(template)==original_hash
    built=backend._read(output)
    for name,(_,data) in package.items():
        if name.startswith(("ppt/slideMasters/","ppt/slideLayouts/","ppt/theme/")):assert built[name][1]==data
    assert not any("studio_s01.xml" in name for name in built)


def test_workbook_tampering_is_detected_independently(repo,project):
    from qa.exhibits import data_exhibits
    from state.io import atomic_bytes
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bar",))
    backend=OOXMLBackend(repo);output=project.path/"work/chart.pptx"
    PresentationCompiler(repo,ConsultingLayout(repo),backend).compile(brief,deck,slides,output,evidence)
    package=backend._read(output);name=next(name for name in package if name.endswith(".xlsx"));book=load_workbook(io.BytesIO(package[name][1]));book.active["B2"]=99;modified=io.BytesIO();book.save(modified);package[name]=(package[name][0],modified.getvalue());backend._write(package,output)
    inspection=backend.inspect(output);frame=next(obj for obj in inspection["slides"][0]["objects"] if obj["content_type"]=="chart")
    native={"slides":[{"shapes":[{"native_id":int(frame["native_id"]),"chart_series":[{"values":[-4,1]}]}]}]}
    findings=data_exhibits(slides,evidence,inspection,native)
    assert any(row["code"]=="CHART_WORKBOOK_MISMATCH" for row in findings)


def test_brand_grid_font_fallback_and_template_canvas_are_explicit(repo,project):
    from layout.brand import BrandRegistry
    from state.io import read_yaml,write_yaml
    tokens=read_yaml(repo/"config/brands/default_consulting.yaml")
    tokens["brand_id"]="test_brand";tokens["fonts"]["family"]="Unavailable Studio Font"
    write_yaml(repo/"config/brands/test_brand.yaml",tokens)
    selected=BrandRegistry(repo).get("test_brand")
    assert selected["fonts"]["family"]=="Arial" and selected["warnings"][0]["code"]=="FONT_FALLBACK"
    tokens["grid"]["message_y_in"]=.5;write_yaml(repo/"config/brands/test_brand.yaml",tokens)
    with pytest.raises(StudioError):BrandRegistry(repo).get("test_brand")
    basic=case.read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json");backend=OOXMLBackend(repo)
    template=project.path/"work/style.pptx"
    from layout.baseline import BaselineLayout
    PresentationCompiler(repo,BaselineLayout(repo),backend).compile(**basic,destination=template)
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bar",))
    brief["constraints"]["use_existing_template"]=True;deck["schema_version"]="1.1";deck["template"]={"path":str(template),"layout_part":"ppt/slideLayouts/slideLayout7.xml"};deck["canvas"]["height_in"]=8
    with pytest.raises(StudioError):PresentationCompiler(repo,ConsultingLayout(repo),backend).compile(brief,deck,slides,project.path/"work/mismatch.pptx",evidence)


def test_exhibit_note_coverage_and_nonpositive_bubble_sizes_rejected(repo,project):
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bubble",))
    wrong=deepcopy(slides[0]);wrong["source_note_ids"]=[]
    with pytest.raises(StudioError):evidence.resolve_exhibit(wrong)
    wrong=deepcopy(slides[0]);wrong["exhibit"]["series"][2]["evidence_ids"]=wrong["exhibit"]["series"][0]["evidence_ids"]
    with pytest.raises(StudioError):evidence.resolve_exhibit(wrong)
