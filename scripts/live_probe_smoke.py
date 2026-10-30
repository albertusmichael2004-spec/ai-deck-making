"""Probe actual running-instance attach using a minimized owned fixture only."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.live.windows import WindowsLiveBackend
from presentation.live.session import LiveSession
from state.io import read_json,write_json,logical_path
from state.project import Project
from presentation.live.paths import local_identity


def main():
    import pythoncom
    import win32com.client
    app=None;deck=None;owned=False;backend=None
    project=Project.create(ROOT,"live-probe-"+uuid4().hex[:10]);source=project.path/"work/live_probe.pptx"
    PresentationCompiler(ROOT,AdaptiveLayoutCompiler(ROOT),OOXMLBackend(ROOT)).compile(**read_json(ROOT/"tests/fixtures/basic_spec.json"),destination=source)
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Owned live probe refuses to take over open user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        deck=app.Presentations.Open(str(logical_path(source)),False,False,True)
        deck.Windows.Item(1).WindowState=2
        deck.Slides.Item(1).Shapes.Item(1).Select()
        backend=WindowsLiveBackend.attach(ROOT,source)
        session=LiveSession(ROOT,project,backend);session.attach()
        result={"passed":True,"fixture":True,"project_id":project.path.name,"version":str(app.Version),"inspection":backend.inspect(),"selection":session.selection(),"snapshot":backend.snapshot(),"comments":backend.comments()}
        session.detach();write_json(ROOT/"implementation/PHASE_REPORTS/phase_10_probe.json",result)
        print({"passed":True,"selection_type":result["selection"]["selection_type"],"slides":len(result["inspection"]["slides"]),"snapshot":result["snapshot"]["saved"]})
    finally:
        if backend is not None:backend.release()
        if app is not None and owned:
            if backend is not None:backend.deck=None;backend.app=None
            session=backend=deck=None
            import gc
            gc.collect()
            for fixture in list(app.Presentations):
                if local_identity(str(fixture.FullName))==local_identity(source):
                    if not bool(fixture.Saved):fixture.Save()
                    fixture.Close()
            fixture=None
            gc.collect()
        if app is not None and owned and int(app.Presentations.Count)==0:app.Quit()


if __name__=="__main__":main()
