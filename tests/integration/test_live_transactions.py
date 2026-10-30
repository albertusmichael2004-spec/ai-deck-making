from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.live.session import LiveSession,objects
from qa.critic import Critic
from state.errors import StudioError
from state.io import read_json

module=importlib.util.spec_from_file_location("live_transaction_control",Path(__file__).parents[1]/"fixtures/live_control.py");control=importlib.util.module_from_spec(module);module.loader.exec_module(control)
module=importlib.util.spec_from_file_location("live_renderer_control",Path(__file__).with_name("test_offline_repair.py"));renderer=importlib.util.module_from_spec(module);module.loader.exec_module(renderer)


class Reviewer:
    last_usage={"tokens":100,"queries":0}
    def __init__(self,hook=None,fail_on=0):self.calls=0;self.hook=hook;self.fail_on=fail_on
    def complete_with_images(self,prompt,schema,images):
        self.calls+=1
        if self.hook:self.hook(self.calls)
        if self.calls==self.fail_on:raise RuntimeError("controlled post-apply interruption")
        context=json.loads(prompt.split("REVIEW DATA=",1)[1])
        return {"schema_version":"1.0","dimensions":{key:100 for key in ["content_accuracy","narrative_clarity","visual_hierarchy","layout_integrity","brand_compliance","editability","source_integrity"]},"slides":[{"slide_id":s["slide_id"],"message_score":100,"observation":"Controlled review"} for s in context["slides"]],"findings":[]}


def prepare(root,project):
    spec=read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json");source=project.path/"work/live_fixture.pptx"
    PresentationCompiler(root,AdaptiveLayoutCompiler(root),OOXMLBackend(root)).compile(**spec,destination=source)
    backend=control.Backend(root,project,source,renderer.ControlRenderer(root));session=LiveSession(root,project,backend);session.attach()
    inspection=backend.inspect();target=next(o for o in inspection["slides"][0]["objects"] if o["role"]=="body")
    scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MAY_CHANGE" if o["object_id"]==target["object_id"] and s["slide_id"]=="s01" else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
    patch={"schema_version":"1.0","patch_id":"controlled_live_patch","operations":[{"slide_id":"s01","object_id":target["object_id"],"expected_fingerprint":target["fingerprint"],"operation":"set_text","value":"The selected message remains editable."}]}
    return spec,backend,session,patch,scope


def test_live_authority_manual_save_preflight_post_review_and_replay(repo,project):
    spec,backend,session,patch,scope=prepare(repo,project)
    with pytest.raises(StudioError):project.begin()
    reviewer=Reviewer();identifier=uuid4().hex
    result=session.apply(patch,scope,spec,Critic(repo,reviewer),transaction_id=identifier)
    assert result["passed"] and reviewer.calls==2 and not backend.saved and project.state()["authority"]=="live"
    assert session.apply(patch,scope,spec,Critic(repo,reviewer),transaction_id=identifier)["no_op"] and reviewer.calls==2
    assert session.detach()["unsaved_preserved"] and project.state()["authority"]=="file"


def test_concurrent_user_edit_during_planning_never_gets_overwritten(repo,project):
    spec,backend,session,patch,scope=prepare(repo,project)
    def user_edit(call):
        if call==1:backend.apply({**patch["operations"][0],"value":"User's intervening revision"})
    with pytest.raises(StudioError,match="User changed"):session.apply(patch,scope,spec,Critic(repo,Reviewer(user_edit)))
    assert next(o["text"] for s in backend.inspect()["slides"] for o in s["objects"] if o["object_id"]==patch["operations"][0]["object_id"])=="User's intervening revision"


def test_recovery_restores_only_owned_mutation_without_undo_stack(repo,project):
    spec,backend,session,patch,scope=prepare(repo,project);before=backend.inspect();identifier=uuid4().hex
    with pytest.raises(RuntimeError):session.apply(patch,scope,spec,Critic(repo,Reviewer(fail_on=2)),transaction_id=identifier)
    result=session.recover(identifier)
    assert result["status"]=="recovered" and backend.inspect()["fingerprint"]==before["fingerprint"]


def test_recovery_preserves_later_user_edit_instead_of_rolling_it_back(repo,project):
    spec,backend,session,patch,scope=prepare(repo,project);identifier=uuid4().hex
    with pytest.raises(RuntimeError):session.apply(patch,scope,spec,Critic(repo,Reviewer(fail_on=2)),transaction_id=identifier)
    current=objects(backend.inspect())[("s01",patch["operations"][0]["object_id"])]
    backend.apply({**patch["operations"][0],"expected_fingerprint":current["fingerprint"],"value":"Later user work preserved"})
    result=session.recover(identifier)
    assert result["status"]=="recovery_conflict" and result["user_edits_preserved"]
    assert objects(backend.inspect())[("s01",patch["operations"][0]["object_id"])]["text"]=="Later user work preserved"


def test_live_attach_cannot_acquire_another_projects_input_or_working_deck(repo,project):
    spec,backend,session,patch,scope=prepare(repo,project)
    session.detach()
    from state.project import Project
    other=Project.create(repo,"other-live-target",validation_policy="kernel")
    backend.target=backend.local_target=str(other.path/"work/unrelated.pptx")
    with pytest.raises(StudioError,match="outside authorized"):
        session.attach()
    backend.target=backend.local_target=str(project.path/"input/original.pptx")
    with pytest.raises(StudioError,match="immutable"):
        session.attach()
