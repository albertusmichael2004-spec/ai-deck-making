import importlib.util
from pathlib import Path
from uuid import uuid4

from evidence.context import EvidenceContext
from layout.consulting import ConsultingLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.rendering.native import NativeRenderer
from qa.transaction import PresentationValidator
from state.project import Project


def test_real_zero_crossing_bridge_and_core_chart_types():
    repository=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location("native_boundary_case",repository/"tests/fixtures/consulting_exhibits.py")
    case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    project=Project.create(repository,"chart-boundaries-"+uuid4().hex[:10])
    brief,deck,slides,evidence,store=case.prepare(repository,project,types=("bridge","column","area","pie","stacked_bar","scatter","bubble"))
    # Distinct driver signs cross zero, proving floating intervals in the actual native renderer.
    source=project.path/"work/metrics.csv"
    source.write_text("category,value,trend_month,trend_value\nOpening,-1,January,10\nMaterials,2,February,9\nLabor,-3,March,8\nClosing,-2,April,7\n",encoding="utf-8")
    source_id=next(iter(store.load().value["sources"]))
    store.refresh(source_id)
    graph=store.load()
    # A pie needs nonnegative composition; use explicitly supplied positive trend values as a bounded fixture.
    for slide in slides:
        if slide["exhibit"]["type"]=="pie":
            ids=[key for key,node in graph.value["nodes"].items() if node.get("extraction",{}).get("column")=="trend_value"]
            labels=[key for key,node in graph.value["nodes"].items() if node.get("extraction",{}).get("column")=="trend_month"]
            slide["exhibit"]["category_evidence_ids"]=labels;slide["exhibit"]["series"][0]["evidence_ids"]=ids
            graph.value["bindings"][slide["exhibit"]["binding_id"]]["evidence_ids"]=[*labels,*ids]
            graph.dependencies.dependencies[slide["exhibit"]["binding_id"]]=[*labels,*ids]
        if slide["exhibit"]["type"]=="stacked_bar":
            ids=[key for key,node in graph.value["nodes"].items() if node.get("extraction",{}).get("column")=="trend_value"]
            slide["exhibit"]["series"].append({"name":"Controlled comparison","evidence_ids":ids})
            binding=graph.value["bindings"][slide["exhibit"]["binding_id"]]
            binding["evidence_ids"]=[*binding["evidence_ids"],*ids]
            graph.dependencies.dependencies[slide["exhibit"]["binding_id"]]=binding["evidence_ids"]
        slide["action_title"]="A controlled fixture verifies signed native chart geometry"
    store.save(graph);evidence=EvidenceContext(graph,project.policy)
    backend=OOXMLBackend(repository);output=project.path/"work/boundaries.pptx"
    PresentationCompiler(repository,ConsultingLayout(repository),backend).compile(brief,deck,slides,output,evidence)
    result=PresentationValidator(repository,backend,NativeRenderer(repository,90),project.path/"output/qa/native_boundary",evidence=evidence,slide_specs=slides)(output)
    assert result["passed"],result
