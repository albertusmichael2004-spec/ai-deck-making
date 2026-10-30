import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

from presentation.backends.ooxml import OOXMLBackend


def worker(monkeypatch, app, *, borrowed=True):
    # Exercise ownership/error handling with COM stubs; no Office process starts.
    import pythoncom
    import win32com.client
    monkeypatch.setattr(win32com.client,"DispatchEx",lambda name:app)
    def get_active(name):
        if borrowed:return app
        raise pythoncom.com_error(-2147221021,"No running application",None,None)
    monkeypatch.setattr(win32com.client,"GetActiveObject",get_active)
    calls=[]
    monkeypatch.setattr(pythoncom,"CoInitialize",lambda:calls.append("init"))
    monkeypatch.setattr(pythoncom,"CoUninitialize",lambda:calls.append("uninit"))
    monkeypatch.setattr(OOXMLBackend,"__init__",lambda self,root:setattr(self,"policy",SimpleNamespace(check=lambda path,**kwargs:path)))
    monkeypatch.setattr(OOXMLBackend,"validate",lambda self,path:{"passed":True})
    spec=importlib.util.spec_from_file_location("native_render_diagnostic_worker",Path(__file__).resolve().parents[2]/"scripts/powerpoint_render_worker.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module,calls


@pytest.mark.parametrize("count",[0,2])
def test_running_app_renders_only_owned_readonly_copy_and_never_quits(tmp_path,monkeypatch,count):
    source=tmp_path/"input.pptx";events=[]
    deck=SimpleNamespace(FullName=str(source),ReadOnly=True,PageSetup=SimpleNamespace(SlideWidth=960,SlideHeight=540),Close=lambda:events.append("close_copy"))
    def open_copy(path,read_only,untitled,visible):
        assert Path(path)==source and read_only and not untitled and not visible
        events.append("open_copy");return deck
    def forbidden(*args):raise AssertionError("Must not quit user's application")
    app=SimpleNamespace(Version="16.0",Presentations=SimpleNamespace(Count=count,Open=open_copy),Quit=forbidden)
    module,calls=worker(monkeypatch,app)
    monkeypatch.setattr("presentation.rendering.metrics.export_slides",lambda *args,**kwargs:[])
    result=module.render(tmp_path/"input.pptx",tmp_path/"output")
    assert result["passed"] and result["preexisting_presentations"]==count
    assert result["session_mode"]=="borrowed" and events==["open_copy","close_copy"]
    assert calls==["init","uninit"]


def test_cleanup_failure_preserves_original_office_error(tmp_path,monkeypatch):
    class Presentations:
        reads=0
        @property
        def Count(self):
            self.reads+=1
            if self.reads>1:raise RuntimeError("Automation rights are not granted")
            return 0
        def Open(self,*args):raise RuntimeError("Automation rights are not granted")
    app=SimpleNamespace(Presentations=Presentations(),Quit=lambda:pytest.fail("No owned empty instance was verified"))
    module,calls=worker(monkeypatch,app,borrowed=False)
    result=module.render(tmp_path/"input.pptx",tmp_path/"output")
    assert not result["passed"] and len(result["errors"])==2
    assert result["errors"][0]["reason"]=="office_automation_denied"
    assert result["errors"][1]["stage"]=="cleanup"
    assert calls==["init","uninit"]
