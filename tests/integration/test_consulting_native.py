import importlib.util
from pathlib import Path
from uuid import uuid4

from layout.consulting import ConsultingLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.rendering.native import NativeRenderer
from qa.transaction import PresentationValidator


def test_native_consulting_exhibits_render_and_pass_qa():
    # Uses real repository/native worker; fixtures never attach to a user's presentation.
    repository=Path(__file__).resolve().parents[2]
    from state.project import Project
    project=Project.create(repository,"exhibits-"+uuid4().hex[:10])
    path=repository/"tests/fixtures/consulting_exhibits.py"
    spec=importlib.util.spec_from_file_location("native_consulting_case",path)
    case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    brief,deck,slides,evidence,store=case.prepare(repository,project)
    output=project.path/"work/consulting.pptx";backend=OOXMLBackend(repository)
    PresentationCompiler(repository,ConsultingLayout(repository),backend).compile(brief,deck,slides,output,evidence)
    result=PresentationValidator(repository,backend,NativeRenderer(repository,90),project.path/"output/qa/consulting_native",evidence=evidence,slide_specs=slides)(output)
    assert result["passed"],result
