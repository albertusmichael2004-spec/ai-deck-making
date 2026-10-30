from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from presentation.compiler.incremental import IncrementalCompiler
from presentation.rendering.native import NativeRenderer
from qa.regression import pixel_compare
from qa.transaction import PresentationValidator
from state.io import read_json,write_json
from state.project import Project


def test_incremental_native_chart_reopens_and_protected_slides_keep_identical_pixels():
    root=Path(__file__).resolve().parents[2]
    module=importlib.util.spec_from_file_location("incremental_native_control",Path(__file__).with_name("test_design_planning.py"));case=importlib.util.module_from_spec(module);module.loader.exec_module(case)
    project=Project.create(root,"incremental-native-"+uuid4().hex[:10]);request,store,intent=case.prepare(root,project)
    previous=DesignPlanner(root,project).plan(request["brief"],{"a1":intent})
    backend=OOXMLBackend(root);compiler=PresentationCompiler(root,AdaptiveLayoutCompiler(root),backend);context=EvidenceContext(store.load(),project.policy)
    source=project.path/"work/before.pptx";compiler.compile(**previous,destination=source,evidence=context)
    before_directory=project.path/"output/qa/incremental_before";after_directory=project.path/"output/qa/incremental_after";renderer=NativeRenderer(root)
    assert PresentationValidator(root,backend,renderer,before_directory,evidence=context,slide_specs=previous["slides"])(source)["passed"]
    revised=deepcopy(previous);revised["slides"][1]["key_message"]="Materials account for 4 percentage points of recorded margin decline."
    scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MAY_CHANGE" if s["slide_id"]==previous["slides"][1]["slide_id"] else "MUST_NOT_CHANGE"} for s in backend.inspect(source)["slides"] for o in s["objects"]]}
    output=project.path/"work/after.pptx";compiled=IncrementalCompiler(root,compiler).compile(source,output,previous,revised,context,[],scope)
    qa=PresentationValidator(root,backend,renderer,after_directory,backend.inspect(source),scope,evidence=context,slide_specs=revised["slides"])(output)
    assert qa["passed"]
    images_before=read_json(before_directory/"render_report.json")["slides"];images_after=read_json(after_directory/"render_report.json")["slides"]
    comparisons=[pixel_compare(Path(images_before[index]["render"]),Path(images_after[index]["render"]),0,0) for index in [0,2]]
    assert all(row["passed"] for row in comparisons)
    result={"passed":True,"project_id":project.path.name,"fixture":True,"recompiled_slides":compiled["recompiled_slides"],"protected_pixel_comparisons":comparisons,"native_qa":qa,"chart_values":next(o["chart_data"][0]["values"] for o in backend.inspect(output)["slides"][1]["objects"] if o.get("content_type")=="chart")}
    write_json(root/"implementation/PHASE_REPORTS/phase_9_incremental_native.json",result)
