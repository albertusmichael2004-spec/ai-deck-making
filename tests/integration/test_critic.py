from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from evidence.context import EvidenceContext
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from qa.critic import Critic
from state.errors import StudioError

spec=importlib.util.spec_from_file_location("critic_design_case",Path(__file__).with_name("test_design_planning.py"));case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)


class Reviewer:
    last_usage={"tokens":100,"queries":0}
    def __init__(self,response):self.response,self.prompts,self.images=response,[],[]
    def complete_with_images(self,prompt,schema,images):self.prompts.append(prompt);self.images.extend(images);return deepcopy(self.response)


def prepare(repo,project):
    request,store,intent=case.prepare(repo,project);designed=DesignPlanner(repo,project).plan(request["brief"],{"a1":intent});context=EvidenceContext(store.load(),project.policy);backend=OOXMLBackend(repo);output=project.path/"work/critic_fixture.pptx"
    inspection=PresentationCompiler(repo,AdaptiveLayoutCompiler(repo),backend).compile(**designed,destination=output,evidence=context)
    # Native metrics here are a control fixture; the measured model/native smoke is separate.
    rendered={"passed":True,"input_sha256":inspection["sha256"],"canvas_pt":{"width":960,"height":540},"slides":[{"index":index+1,"render":str(repo/"runtime"/f"control_{index}.png"),"shapes":[]} for index in range(len(designed["slides"]))]}
    response={"schema_version":"1.0","dimensions":{key:100 for key in ["content_accuracy","narrative_clarity","visual_hierarchy","layout_integrity","brand_compliance","editability","source_integrity"]},"slides":[{"slide_id":slide["slide_id"],"message_score":100,"observation":"Controlled complete review"} for slide in designed["slides"]],"findings":[]}
    return designed,context,output,inspection,rendered,response


def test_critic_context_isolated_and_full_slide_review_required(repo,project):
    designed,context,output,inspection,rendered,response=prepare(repo,project);designed["builder_rationale"]="PRIVATE CREATOR TRACE DO NOT LEAK"
    reviewer=Reviewer(response);critic=Critic(repo,reviewer);result=critic.evaluate(designed,output,inspection,rendered,context)
    assert "PRIVATE CREATOR TRACE" not in reviewer.prompts[0] and "verified_evidence" in critic.last_context and len(reviewer.images)==3
    reviewer.response["slides"].pop()
    with pytest.raises(StudioError):critic.evaluate(designed,output,inspection,rendered,context)


def test_wrong_number_is_a_blocker_even_with_perfect_model_scores(repo,project):
    designed,context,output,inspection,rendered,response=prepare(repo,project)
    designed["slides"][1]["action_title"]="Materials cause 99 percentage points of margin decline"
    result=Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)
    assert not result["passed"] and any(row["code"]=="UNREGISTERED_NUMERICAL_COPY" and row["severity"]=="BLOCKER" for row in result["issues"])


def test_critic_rejects_invented_targets_and_stale_render_proof(repo,project):
    designed,context,output,inspection,rendered,response=prepare(repo,project)
    response["findings"]=[{"code":"EXHIBIT_TITLE_CONTRADICTION","severity":"MAJOR","slide_id":designed["slides"][0]["slide_id"],"object_id":"invented-shape","message":"Contradiction","evidence_ids":[],"repair_intent":"Rewrite title"}]
    with pytest.raises(StudioError):Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)
    rendered["input_sha256"]="0"*64
    with pytest.raises(StudioError):Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)


def test_major_semantic_findings_fail_without_reclassifying_them_as_style(repo,project):
    designed,context,output,inspection,rendered,response=prepare(repo,project)
    response["findings"]=[{"code":"CHART_MESSAGE_CONTRADICTION","severity":"MAJOR","slide_id":designed["slides"][1]["slide_id"],"object_id":None,"message":"Observed chart contradicts the message","evidence_ids":[],"repair_intent":"Align the assertion with verified exhibit data"}]
    result=Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)
    assert not result["passed"] and any(row["code"]=="CHART_MESSAGE_CONTRADICTION" for row in result["errors"])


def test_missing_visible_citation_blocks_even_a_perfect_qualitative_score(repo,project):
    designed,context,output,inspection,rendered,response=prepare(repo,project)
    for obj in inspection["slides"][0]["objects"]:
        if obj.get("role")=="source":obj["text"]="Source: unrelated file"
    result=Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)
    assert not result["passed"] and any(row["code"]=="SOURCE_CITATION_MISSING" and row["severity"]=="BLOCKER" for row in result["errors"])


@pytest.mark.parametrize("copy",["Materials account for 4% of decline.","The recorded loss is 4 USD."])
def test_a_matching_literal_cannot_bypass_incompatible_units(repo,project,copy):
    designed,context,output,inspection,rendered,response=prepare(repo,project)
    designed["slides"][1]["key_message"]=copy
    result=Critic(repo,Reviewer(response)).evaluate(designed,output,inspection,rendered,context)
    assert any(row["code"]=="UNREGISTERED_NUMERICAL_COPY" for row in result["errors"])
