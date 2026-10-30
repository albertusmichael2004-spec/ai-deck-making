import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from presentation.rendering.native import NativeRenderer
from qa.transaction import PresentationValidator
from state.project import Project


@pytest.mark.parametrize("use_template",[False,True])
def test_reasoning_to_native_consulting_deck_commit(use_template):
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location("design_native_case",root/"tests/integration/test_design_planning.py")
    case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    project=Project.create(root,"consulting-e2e-"+uuid4().hex[:10])
    request,store,intent=case.prepare(root,project)
    backend=OOXMLBackend(root);template=None
    if use_template:
        from state.io import read_json,sha256
        basic=read_json(root/"tests/fixtures/basic_spec.json");source=project.path/"work/company_template.pptx"
        PresentationCompiler(root,AdaptiveLayoutCompiler(root),backend).compile(**basic,destination=source)
        original=sha256(source);template={"path":str(source),"layout_part":"ppt/slideLayouts/slideLayout7.xml"}
        request["brief"]["constraints"]["use_existing_template"]=True
    designed=DesignPlanner(root,project).plan(request["brief"],{"a1":intent},template=template)
    transaction=project.begin();backend=OOXMLBackend(root);context=EvidenceContext(store.load(),project.policy)
    PresentationCompiler(root,AdaptiveLayoutCompiler(root),backend).compile(**designed,destination=project.candidate(transaction),evidence=context)
    validator=PresentationValidator(root,backend,NativeRenderer(root,90),project.path/"output/qa/consulting_e2e",evidence=context,slide_specs=designed["slides"])
    result=project.commit(transaction,validator)
    assert project.canonical.is_file() and len(backend.inspect(project.canonical)["slides"])==3
    assert result["generation"]==1
    if template:assert sha256(source)==original


def test_research_snapshot_to_native_bound_table():
    import base64
    from evidence.store import EvidenceStore
    from research.documents import decode_document
    from state.io import read_json,write_json
    root=Path(__file__).resolve().parents[2];project=Project.create(root,"research-design-"+uuid4().hex[:10])
    raw=b"Controlled fixture measurement is 10 units for 2025."
    document={**decode_document(raw,"text/plain","https://example.com/controlled-fixture"),"url":"https://example.com/controlled-fixture","mime":"text/plain","raw_base64":base64.b64encode(raw).decode()}
    finding={"value":"10","unit":"units","period":"2025","geography":"global","definition":"controlled fixture measurement","published_at":"2025-01-01","quote":raw.decode(),"locator":"document:text","question_fit":1,"definitive":True,"answer_type":"numeric"}
    source=project.path/"work/research_snapshot.json";write_json(source,{"format":"studio_research_snapshot_v1","document":document,"findings":[finding],"publisher":"Controlled test publisher"})
    store=EvidenceStore(root,project);record=store.ingest(source,units={"default":{"label":"units"}},data_period="2025");graph=store.load();key=record["evidence_ids"][0]
    assert len(record["evidence_ids"])==1 and graph.resolve(key)["value"]=="10"
    basic=read_json(root/"tests/fixtures/basic_spec.json");slide=basic["slides"][0];basic["slides"]=[slide];basic["deck"]["slide_ids"]=[slide["slide_id"]];basic["deck"]["storyline"]=["controlled research fixture"]
    slide.update(action_title="The controlled research fixture reports the measured value",key_message="This synthetic source tests immutable research provenance through native output.",claim_ids=[key],source_note_ids=[record["source_id"]],layout={"archetype":"single_exhibit"},exhibit={"type":"table","binding_id":"research_fixture_binding","headers":["Fixture measurement (units)"],"rows":[[key]]})
    basic["brief"]["constraints"]["sources_required"]=True;graph.bind("research_fixture_binding",[key],slide["slide_id"],"research_table");store.save(graph)
    backend=OOXMLBackend(root);context=EvidenceContext(graph,project.policy);output=project.path/"work/researched.pptx"
    PresentationCompiler(root,AdaptiveLayoutCompiler(root),backend).compile(**basic,destination=output,evidence=context)
    result=PresentationValidator(root,backend,NativeRenderer(root,90),project.path/"output/qa/research_design",evidence=context,slide_specs=[slide])(output)
    assert result["passed"] and "Controlled test publisher" in context.source_note(record["source_id"])
