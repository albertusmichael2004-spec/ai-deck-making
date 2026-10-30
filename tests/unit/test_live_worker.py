from argparse import Namespace
from types import SimpleNamespace
from pathlib import Path
import subprocess

import pytest

from cli.live_commands import execute
from state.io import write_json
from state.errors import StudioError


def arguments():return Namespace(action="inspect",project_id="test-project",target=None)


def test_live_worker_deadline_never_terminates_office(repo,monkeypatch):
    calls=[]
    def timeout(command,**options):
        calls.append(command)
        assert options["timeout"]==900 and "shell" not in options
        raise subprocess.TimeoutExpired(command,900)
    monkeypatch.setattr(subprocess,"run",timeout)
    with pytest.raises(StudioError,match="PowerPoint/retained"):execute(repo,arguments())
    assert len(calls)==1 and calls[0][1:3]==["-m","cli.live_worker"]


def test_live_worker_returns_structured_result_and_errors(repo,monkeypatch):
    def run(command,**options):
        write_json(Path(command[-1]),{"result":{"passed":True}})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,"run",run)
    assert execute(repo,arguments())["passed"]
