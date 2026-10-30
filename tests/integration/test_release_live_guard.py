import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from qa.critic import Critic
from state.errors import StudioError

module=importlib.util.spec_from_file_location("release_guard_control",Path(__file__).with_name("test_live_transactions.py"));case=importlib.util.module_from_spec(module);module.loader.exec_module(case)


def test_unreviewed_interrupted_mutation_cannot_save_detach_or_start_new_mutation(repo,project):
    spec,backend,session,patch,scope=case.prepare(repo,project);identifier=uuid4().hex
    with pytest.raises(RuntimeError):session.apply(patch,scope,spec,Critic(repo,case.Reviewer(fail_on=2)),transaction_id=identifier)
    for action in [lambda:session.save("save_existing"),session.detach,lambda:session.apply(patch,scope,spec,Critic(repo,case.Reviewer()))]:
        with pytest.raises(StudioError,match="Resolve retained"):action()
    assert project.state()["authority"]=="live" and not backend.saved
    assert session.recover(identifier)["status"]=="recovered"
    assert session.detach()["passed"]
