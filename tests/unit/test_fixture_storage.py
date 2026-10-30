from state.paths import project_path
from state.project import Project
from state.workspace import Workspaces
from state.io import native_path


def test_synthetic_projects_live_under_runtime_and_remain_openable(repo):
    fixture=Project.create(repo,"qa-smoke-abcde12345",validation_policy="kernel")
    assert fixture.path.parent==native_path(repo/"runtime/test_projects")
    assert not (repo/"projects"/fixture.path.name).exists()
    assert Project.open(repo,fixture.path.name).path==fixture.path
    assert Workspaces(repo).list()==[]
    assert [row["project_id"] for row in Workspaces(repo).list(include_fixtures=True)]==[fixture.path.name]


def test_user_projects_stay_in_projects_and_legacy_paths_are_respected(repo):
    user=Project.create(repo,"my-user-project",validation_policy="kernel")
    assert user.path.parent==native_path(repo/"projects")
    legacy=repo/"projects/bench-abcde12345";legacy.mkdir()
    assert project_path(repo,legacy.name)==legacy


def test_runtime_fixture_inputs_keep_native_write_protection(repo):
    import pytest
    from presentation.live.windows import live_policy
    from state.errors import StudioError
    fixture=Project.create(repo,"live-native-abcde12345",validation_policy="kernel")
    with pytest.raises(StudioError):live_policy(repo).check(fixture.path/"input/original.pptx",write=True)
