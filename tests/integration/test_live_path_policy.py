import pytest

from presentation.live.windows import live_policy
from state.errors import StudioError


def test_native_open_and_save_policy_rejects_original_inputs_before_com(repo,project):
    policy=live_policy(repo)
    for destination in [project.path/"input/original.pptx",repo/"library/knowledge/packages/original.pptx"]:
        with pytest.raises(StudioError):policy.check(destination,write=True)
    assert policy.check(project.path/"work/editable.pptx",write=True)==project.path/"work/editable.pptx"
