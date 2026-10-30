import json
import os
import shutil

import pytest

from conftest import byte_validator, commit_bytes
from state.errors import ErrorCode, StudioError
from state.io import fingerprint, read_json, sha256, write_json
from state.project import Project


def test_commit_reopen_snapshot_rollback(project, repo):
    commit_bytes(project, b"valid:first")
    snapshot = project.snapshot()
    commit_bytes(project, b"valid:second")
    reopened = Project.open(repo, "test-project")
    assert reopened.state()["generation"] == 2
    reopened.rollback(snapshot, reopened.token())
    assert reopened.canonical.read_bytes() == b"valid:first"
    assert reopened.state()["generation"] == 3


def test_failed_validation_never_changes_canonical(project):
    commit_bytes(project, b"valid:original")
    original = fingerprint(project.canonical)
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"invalid")
    with pytest.raises(StudioError) as result: project.commit(identifier, byte_validator)
    assert result.value.code == ErrorCode.QA_FAILURE
    assert fingerprint(project.canonical) == original
    assert project.state()["generation"] == 1


def test_user_edit_during_validation_is_preserved(project):
    commit_bytes(project, b"valid:original")
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"valid:proposed")
    def concurrent_edit(path):
        project.canonical.write_bytes(b"user edit")
        return byte_validator(path)
    with pytest.raises(StudioError): project.commit(identifier, concurrent_edit)
    assert project.canonical.read_bytes() == b"user edit"
    with pytest.raises(StudioError): project.begin()


def test_generation_conflict_between_transactions(project):
    first, second = project.begin(), project.begin()
    project.candidate(first).write_bytes(b"valid:first")
    project.candidate(second).write_bytes(b"valid:second")
    project.commit(first, byte_validator)
    with pytest.raises(StudioError): project.commit(second, byte_validator)
    assert project.canonical.read_bytes() == b"valid:first"


def test_candidate_mutation_during_validation_rejected(project):
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"valid:proposed")
    def mutated(path):
        path.write_bytes(b"invalid")
        return {"passed": True, "errors": []}
    with pytest.raises(StudioError): project.commit(identifier, mutated)
    assert not project.canonical.exists()


def test_failed_atomic_replace_preserves_deck(project, monkeypatch):
    commit_bytes(project, b"valid:original")
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"valid:new")
    real_replace = os.replace
    def fail_candidate(source, target):
        if str(source).endswith("candidate.pptx"): raise OSError("disk failure")
        return real_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_candidate)
    with pytest.raises(OSError): project.commit(identifier, byte_validator)
    assert project.canonical.read_bytes() == b"valid:original"
    assert project.recover()[0]["status"] == "aborted"


def test_recovery_after_replace_before_state_write(project, monkeypatch):
    commit_bytes(project, b"valid:original")
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"valid:new")
    import state.project as module
    real_write = module.write_yaml
    def crash(*args): raise OSError("simulated crash after deck replacement")
    monkeypatch.setattr(module, "write_yaml", crash)
    with pytest.raises(OSError): project.commit(identifier, byte_validator)
    monkeypatch.setattr(module, "write_yaml", real_write)
    assert project.canonical.read_bytes() == b"valid:new"
    assert project.recover()[0]["status"] == "committed"
    assert project.state()["generation"] == 2
    assert project.recover() == []


def test_recovery_never_overwrites_user_work(project, monkeypatch):
    commit_bytes(project, b"valid:original")
    identifier = project.begin()
    project.candidate(identifier).write_bytes(b"valid:new")
    import state.project as module
    def crash(*args): raise OSError("crash")
    with monkeypatch.context() as patch:
        patch.setattr(module, "write_yaml", crash)
        with pytest.raises(OSError): project.commit(identifier, byte_validator)
    project.canonical.write_bytes(b"user edited after crash")
    assert project.recover()[0]["status"] == "conflict"
    assert project.canonical.read_bytes() == b"user edited after crash"


def test_corrupt_snapshot_and_stale_rollback_are_rejected(project):
    commit_bytes(project, b"valid:original")
    snapshot = project.snapshot()
    expected = project.token()
    commit_bytes(project, b"valid:new")
    with pytest.raises(StudioError): project.rollback(snapshot, expected)
    (project.path / "history/snapshots" / (snapshot + ".pptx")).write_bytes(b"corrupted")
    with pytest.raises(StudioError): project.rollback(snapshot, project.token())
    assert project.canonical.read_bytes() == b"valid:new"


def test_input_untouched_by_transaction(project):
    source = project.path / "input/sources/raw.csv"
    source.write_bytes(b"value\n3\n")
    original = sha256(source)
    commit_bytes(project, b"valid:deck")
    assert sha256(source) == original


def test_rollback_is_recoverable_after_interrupted_state_write(project, monkeypatch):
    commit_bytes(project, b"valid:first")
    snapshot = project.snapshot()
    commit_bytes(project, b"valid:second")
    import state.project as module
    real_write = module.write_yaml
    def crash(*args): raise OSError("rollback interrupted after atomic file replacement")
    with monkeypatch.context() as patch:
        patch.setattr(module, "write_yaml", crash)
        with pytest.raises(OSError): project.rollback(snapshot, project.token())
    assert project.canonical.read_bytes() == b"valid:first"
    assert project.recover()[0]["status"] == "committed"
    assert project.state()["generation"] == 3


def test_production_project_cannot_accept_structural_only_validation(repo):
    project=Project.create(repo,"production-project")
    transaction=project.begin()
    project.candidate(transaction).write_bytes(b"valid:primitive")
    with pytest.raises(StudioError):project.commit(transaction,byte_validator)
    assert not project.canonical.exists()


def test_legacy_state_migrates_explicitly_to_stronger_validation(repo):
    from state.io import write_yaml
    project=Project.create(repo,"legacy")
    state=project.state();state.pop("validation_policy");state["schema_version"]="1.0"
    write_yaml(project.state_path,state)
    migrated=Project.open(repo,"legacy").state()
    assert migrated["schema_version"]=="1.1" and migrated["validation_policy"]=="presentation"


@pytest.mark.parametrize("identifier", ["../../outside", "x", "a" * 33])
def test_transaction_traversal_rejected(project, identifier):
    with pytest.raises(StudioError): project.candidate(identifier)
