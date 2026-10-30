from pathlib import Path
from types import SimpleNamespace
import sys

import run


def test_launcher_selects_complete_interpreter_after_incomplete_one(tmp_path, monkeypatch):
    incomplete = tmp_path / "python314.exe"
    complete = tmp_path / "python312.exe"
    incomplete.touch()
    complete.touch()
    monkeypatch.setattr(run, "_candidate_interpreters", lambda: [incomplete, complete])
    monkeypatch.setattr(run, "_has_project_dependencies", lambda path: path == complete)

    assert run._find_project_interpreter() == complete


def test_dependency_probe_adds_bundled_runtime_packages(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    assert run._has_project_dependencies(Path("python.exe"))
    command, options = calls[0]
    assert command[0] == "python.exe" and command[1] == "-c"
    assert all(module in command[2] for module in run.REQUIRED_IMPORTS)
    assert command[3] == str(run.ROOT / "runtime" / "python_packages")
    assert options["cwd"] == run.ROOT and options["timeout"] == 15


def test_default_launcher_opens_activity_menu_and_others_remains_direct():
    assert run._studio_arguments(SimpleNamespace(others=False)) == ["--root", str(run.ROOT)]
    assert run._studio_arguments(SimpleNamespace(others=True)) == [
        "--root",
        str(run.ROOT),
        "project",
        "others",
    ]


def test_current_interpreter_probe_avoids_a_child_and_restores_search_path(monkeypatch):
    before=sys.path[:]
    monkeypatch.setattr(run.importlib.util,'find_spec',lambda name:object())
    def unexpected(*args,**kwargs):raise AssertionError('Current runtime must not launch a probe process')
    monkeypatch.setattr(run.subprocess,'run',unexpected)
    assert run._has_project_dependencies(Path(sys.executable))
    assert sys.path==before


def test_current_interpreter_missing_dependency_still_fails(monkeypatch):
    before=sys.path[:]
    monkeypatch.setattr(run.importlib.util,'find_spec',lambda name:None if name=='yaml' else object())
    assert not run._has_project_dependencies(Path(sys.executable))
    assert sys.path==before


def test_local_interpreter_candidates_do_not_scan_path(monkeypatch):
    def unexpected(command):raise AssertionError('PATH search must be deferred')
    monkeypatch.setattr(run.shutil,'which',unexpected)
    candidate=next(run._candidate_interpreters())
    assert '.venv' in candidate.parts


def test_fallback_enters_cli_without_restarting_launcher(tmp_path, monkeypatch):
    fallback = tmp_path / "python.exe"
    calls = []
    monkeypatch.setattr(run, "_find_project_interpreter", lambda: fallback)
    monkeypatch.setattr(run.os, "chdir", lambda path: None)
    monkeypatch.setattr(run.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(run.sys, "stdout", SimpleNamespace(isatty=lambda: True, write=lambda text: None, flush=lambda: None))
    monkeypatch.setattr(run.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=0))

    assert run.main(["--others"]) == 0
    command, options = calls[0]
    assert command == [str(fallback), "-m", "cli.main", "--root", str(run.ROOT), "project", "others"]
    assert str(run.ROOT / "runtime/python_packages") in options["env"]["PYTHONPATH"]
    assert options["cwd"] == run.ROOT
