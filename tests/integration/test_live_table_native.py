import importlib.util
from pathlib import Path
from uuid import uuid4

from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.live.com import set_property
from presentation.live.paths import local_identity
from presentation.live.session import LiveSession
from presentation.live.windows import WindowsLiveBackend
from state.io import logical_path,write_json
from state.project import Project


def test_native_table_scope_capture_and_copy_save_preserve_original_unsaved_state():
    import pythoncom
    import win32com.client
    root=Path(__file__).resolve().parents[2];project=Project.create(root,"live-table-"+uuid4().hex[:10])
    module=importlib.util.spec_from_file_location("live_table_fixture",Path(__file__).parents[1]/"fixtures/consulting_exhibits.py");case=importlib.util.module_from_spec(module);module.loader.exec_module(case)
    brief,deck_spec,slides,evidence,store=case.prepare(root,project,types=("table",))
    source=project.path/"work/live_table.pptx";PresentationCompiler(root,AdaptiveLayoutCompiler(root),OOXMLBackend(root)).compile(brief,deck_spec,slides,source,evidence=evidence)
    app=None;owned=False;backend=None
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Table integration refuses to interfere with user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        opened=app.Presentations.Open(str(logical_path(source)),False,False,True);opened.Windows.Item(1).WindowState=2
        backend=WindowsLiveBackend.attach(root,source);deck=backend.deck;set_property(deck,"AutoSaveOn",False)
        table=next(shape for shape in deck.Slides.Item(1).Shapes if bool(shape.HasTable));table.Select()
        session=LiveSession(root,project,backend);session.attach("manual")
        context=session.selection();assert context["objects"][0]["content_type"]=="table"
        body=next(shape for shape in deck.Slides.Item(1).Shapes if str(shape.AlternativeText)=="studio-role:body")
        body.TextFrame.TextRange.Text="Keep the recorded table values intact."
        before=backend.inspect();snapshot=backend.snapshot()
        assert not snapshot["saved"] and not bool(deck.Saved)
        copy=project.path/"output/live_table_copy.pptx";result=backend.save("save_copy",copy_path=copy)
        assert copy.exists() and result["unsaved_preserved"] and not bool(deck.Saved) and backend.inspect()["fingerprint"]==before["fingerprint"]
        write_json(root/"implementation/PHASE_REPORTS/phase_10_table_native.json",{"passed":True,"fixture":True,"project_id":project.path.name,"native_table_selection":True,"copy_saved":True,"dirty_preserved":True,"snapshot_current":True})
        session.detach()
    finally:
        if backend is not None:backend.release()
        if app is not None and owned:
            # Drop borrowed child proxies while their owning objects are still alive.
            if backend is not None:backend.deck=None;backend.app=None
            session=backend=batch=opened=deck=title=chart=body=table=None
            import gc
            gc.collect()
            for fixture in list(app.Presentations):
                if local_identity(str(fixture.FullName))==local_identity(source):
                    if not bool(fixture.Saved):fixture.Save()
                    fixture.Close()
            fixture=deck=None
            gc.collect()
            if int(app.Presentations.Count)==0:app.Quit()
