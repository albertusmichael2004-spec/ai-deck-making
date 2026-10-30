from pathlib import Path
import shutil

import pytest

from state.paths import initialize_folders
from state.project import Project


@pytest.fixture
def repo(tmp_path):
    source = Path(__file__).resolve().parents[1]
    for directory in ["schemas", "config"]:
        shutil.copytree(source / directory, tmp_path / directory)
    (tmp_path / ".studio-root").write_text("test", encoding="utf-8")
    initialize_folders(tmp_path)
    return tmp_path


@pytest.fixture
def project(repo):
    return Project.create(repo, "test-project", validation_policy="kernel")


def byte_validator(path):
    return {"passed": path.read_bytes().startswith(b"valid:"), "errors": []}


def commit_bytes(project, value):
    identifier = project.begin()
    project.candidate(identifier).write_bytes(value)
    project.commit(identifier, byte_validator)
    return identifier
