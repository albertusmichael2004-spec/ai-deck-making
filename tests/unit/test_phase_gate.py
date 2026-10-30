import importlib.util
from pathlib import Path
import zipfile

import pytest

from state.errors import StudioError
from state.io import read_yaml, write_json, write_yaml


def checkpoint_module():
    path = Path(__file__).resolve().parents[2] / "scripts/checkpoint.py"
    spec = importlib.util.spec_from_file_location("phase_checkpoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_gate(repo):
    (repo / "implementation").mkdir(exist_ok=True)
    write_yaml(repo / "implementation/IMPLEMENTATION_STATUS.yaml", {"schema_version": "1.0", "architecture_version": "6.6", "current_phase": 0, "status": "in_progress", "completed_phases": [], "phases": {0: {"status": "in_progress"}}, "tests": {}, "last_checkpoint": None})
    write_yaml(repo / "REQUIREMENTS.yaml", {"phases": [{"requirements": ["kernel"]}]})
    report = repo / "implementation/gate.json"
    write_json(report, {"phase": 0, "engineering_review_passed": True, "acceptance": [{"requirement": "kernel", "passed": True}], "test_reports": ["implementation/tests.xml"]})
    (repo / "implementation/tests.xml").write_text('<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>')
    return report


def test_gate_cannot_skip_phase_or_accept_failing_tests(repo):
    module = checkpoint_module()
    report = setup_gate(repo)
    with pytest.raises(StudioError): module.checkpoint(repo, 1, report)
    (repo / "implementation/tests.xml").write_text('<testsuites><testsuite tests="3" failures="1" errors="0" skipped="0"/></testsuites>')
    with pytest.raises(StudioError): module.checkpoint(repo, 0, report)
    assert read_yaml(repo / "implementation/IMPLEMENTATION_STATUS.yaml")["completed_phases"] == []


def test_successful_checkpoint_is_verified_and_recoverable(repo):
    module = checkpoint_module()
    report = setup_gate(repo)
    result = module.checkpoint(repo, 0, report)
    with zipfile.ZipFile(repo / result["path"]) as archive:
        assert archive.testzip() is None
        assert "CHECKPOINT_MANIFEST.json" in archive.namelist()
        assert "implementation/IMPLEMENTATION_STATUS.yaml" in archive.namelist()
    assert read_yaml(repo / "implementation/IMPLEMENTATION_STATUS.yaml")["completed_phases"] == [0]
    with pytest.raises(StudioError): module.checkpoint(repo, 0, report)
