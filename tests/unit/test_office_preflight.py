import importlib
import json
from types import SimpleNamespace
import pytest
from presentation.backends.windows_probe import WindowsPowerPointProbe


def test_probe_returns_actionable_office_error_instead_of_raw_com(monkeypatch):
    import pythoncom
    import win32com.client
    class Deck:
        Name="Working deck"
        @property
        def FullName(self):
            raise pythoncom.com_error(-2147352567,"Exception occurred",(0,"PowerPoint","Automation rights are not granted",None,0,-2147188160),None)
    app=SimpleNamespace(Version="16.0",Presentations=SimpleNamespace(Count=1,Item=lambda index:Deck()))
    calls=[]
    monkeypatch.setattr(win32com.client,"GetActiveObject",lambda name:app)
    monkeypatch.setattr(pythoncom,"CoInitialize",lambda:calls.append("init"))
    monkeypatch.setattr(pythoncom,"CoUninitialize",lambda:calls.append("uninit"))
    result=WindowsPowerPointProbe().probe()
    assert result["available"] is True
    assert result["presentations"][0]["metadata_available"] is False
    assert result["presentations"][0]["diagnostic"]["reason"]=="office_automation_denied"
    assert calls==["init","uninit"]


@pytest.mark.parametrize("kind",["memory","win32"])
def test_cli_reports_memory_exhaustion_as_user_action(monkeypatch,capsys,kind):
    module=importlib.import_module("cli.main")
    def fail(*args):
        if kind=="memory":raise MemoryError()
        error=OSError("Insufficient memory resources");error.winerror=8
        raise error
    monkeypatch.setattr(module,"repository_root",fail)
    assert module.main(["status"])==1
    result=json.loads(capsys.readouterr().out)
    assert result["code"]=="USER_ACTION_REQUIRED" and "memory" in result["message"].lower()
