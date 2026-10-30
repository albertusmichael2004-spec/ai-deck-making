import importlib.util
from pathlib import Path
from uuid import uuid4

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from presentation.rendering.native import NativeRenderer
from qa.critic import Critic
from state.project import Project


def test_critic_with_real_native_metrics_cannot_override_wrong_copy():
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location("critic_native_control",root/"tests/integration/test_critic.py");case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    project=Project.create(root,"critic-native-"+uuid4().hex[:10]);request,store,intent=case.case.prepare(root,project);designed=DesignPlanner(root,project).plan(request["brief"],{"a1":intent});context=EvidenceContext(store.load(),project.policy)
    candidate=project.path/"work/native_critic.pptx";backend=OOXMLBackend(root);PresentationCompiler(root,AdaptiveLayoutCompiler(root),backend).compile(**designed,destination=candidate,evidence=context)
    rendered=NativeRenderer(root).render(candidate,project.path/"output/qa/critic_control")
    response={"schema_version":"1.0","dimensions":{key:100 for key in ["content_accuracy","narrative_clarity","visual_hierarchy","layout_integrity","brand_compliance","editability","source_integrity"]},"slides":[{"slide_id":slide["slide_id"],"message_score":100,"observation":"Complete control review"} for slide in designed["slides"]],"findings":[]}
    reviewer=case.Reviewer(response);critic=Critic(root,reviewer)
    assert critic.evaluate(designed,candidate,backend.inspect(candidate),rendered,context)["passed"]
    designed["slides"][1]["key_message"]="Materials account for 99 percentage points of decline."
    result=critic.evaluate(designed,candidate,backend.inspect(candidate),rendered,context)
    assert not result["passed"] and any(row["code"]=="UNREGISTERED_NUMERICAL_COPY" for row in result["errors"])
