"""Independent assertions against genuine native Phase 6 output artifacts."""
import csv
import zipfile

from state.io import native_path,read_json,sha256
from presentation.backends.ooxml import OOXMLBackend


def cases(root):
    def latest(prefix,predicate=lambda path:True):
        bases=[native_path(root/"projects"),native_path(root/"runtime/test_projects")]
        matches=[path for base in bases if base.exists() for path in base.iterdir() if path.name.startswith(prefix) and predicate(path)]
        if not matches:raise ValueError("Required native benchmark output is missing: "+prefix)
        return max(matches,key=lambda path:path.stat().st_mtime_ns)

    def score(checks,path):
        result=100*sum(checks.values())/len(checks)
        return {"passed":all(checks.values()) and result>=90,"score":result,"threshold":90,"checks":checks,"project":path.name}

    def story_case(template):
        path=latest("consulting-e2e-",lambda path:(path/"presentation/canonical.pptx").is_file() and (path/"work/company_template.pptx").is_file()==template)
        deck=path/"presentation/canonical.pptx";spec=read_json(path/"state/design_spec.json");qa=read_json(path/"output/qa/consulting_e2e/qa_report.json");render=read_json(path/"output/qa/consulting_e2e/render_report.json")
        inspection=OOXMLBackend(root).inspect(deck)
        with (path/"work/costs.csv").open(newline="",encoding="utf-8") as stream:source=list(csv.DictReader(stream))
        chart=next(shape for shape in render["slides"][1]["shapes"] if "chart_series" in shape)
        titles=[shape["text"] for shape in render["slides"][0]["shapes"] if shape.get("text") and shape["name"]=="studio:"+next(obj["object_id"] for obj in inspection["slides"][0]["objects"] if obj["role"]=="title")]
        rec_text=" ".join(shape.get("text","") for shape in render["slides"][-1]["shapes"]).lower()
        checks={"fixture_values_independently_read":[row["margin_loss_pp"] for row in source]==["4","1"],"native_chart_values":chart["chart_series"][0]["values"]==[4,1],"answer_first":" ".join(titles[0].split())==spec["deck"]["core_answer"],"conditional_recommendation_visible":"validation" in rec_text and "supplier" in rec_text,"native_qa_proof":qa["passed"] and render["input_sha256"]==sha256(deck),"all_pages_have_sources":all(any("Source: costs.csv" in shape.get("text","") for shape in slide["shapes"]) for slide in render["slides"])}
        if template:
            with zipfile.ZipFile(path/"work/company_template.pptx") as original,zipfile.ZipFile(deck) as output:
                checks["template_style_preserved"]=all(original.read(name)==output.read(name) for name in original.namelist() if name.startswith(("ppt/slideMasters/","ppt/slideLayouts/","ppt/theme/")))
        return score(checks,path)

    def supplied_storyline():return story_case(False)
    def template_storyline():return story_case(True)

    def research_provenance():
        path=latest("research-design-",lambda path:(path/"output/qa/research_design/qa_report.json").is_file())
        deck=path/"work/researched.pptx";render=read_json(path/"output/qa/research_design/render_report.json");qa=read_json(path/"output/qa/research_design/qa_report.json");inspection=OOXMLBackend(root).inspect(deck)
        table=next(obj for obj in inspection["slides"][0]["objects"] if obj["content_type"]=="table")
        text=" ".join(shape.get("text","") for shape in render["slides"][0]["shapes"])
        return score({"native_qa_proof":qa["passed"] and render["input_sha256"]==sha256(deck),"bound_table_value":table["table_data"]==[["Fixture measurement (units)"],["10"]],"publisher_visible":"Controlled test publisher" in text,"original_url_visible":"https://example.com/controlled-fixture" in text,"fixture_disclosed":"synthetic source" in text},path)

    def signed_bridge():
        path=latest("chart-boundaries-",lambda path:(path/"output/qa/native_boundary/qa_report.json").is_file())
        deck=path/"work/boundaries.pptx";render=read_json(path/"output/qa/native_boundary/render_report.json");qa=read_json(path/"output/qa/native_boundary/qa_report.json")
        series=next(shape["chart_series"] for shape in render["slides"][0]["shapes"] if "chart_series" in shape)
        labels={label["point_index"]:label["text"] for row in series for label in row["labels"] if label["text"].strip()}
        scatter=next(shape["chart_series"] for shape in render["slides"][5]["shapes"] if "chart_series" in shape)
        bubble=next(shape["chart_series"] for shape in render["slides"][6]["shapes"] if "chart_series" in shape)
        return score({"native_qa_proof":qa["passed"] and render["input_sha256"]==sha256(deck),"original_signed_labels":labels=={0:"-1",1:"2",2:"-3",3:"-2"},"scatter_x":scatter[0]["x_values"]==[-1,2,-3,-2],"bubble_workbook_binding":bubble[0].get("sizes_formula")=="Sheet1!$C$2:$C$5","native_readable_labels":all(label["font_pt"]>=12 for row in series for label in row["labels"] if label["text"].strip())},path)
    return [supplied_storyline,template_storyline,research_provenance,signed_bridge]
