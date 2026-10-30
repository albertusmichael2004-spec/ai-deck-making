"""Native failure recovery and concurrent user edits on an owned fixture."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from presentation.live.com import set_property
from presentation.live.paths import local_identity
from presentation.live.session import LiveSession,objects
from presentation.live.windows import WindowsLiveBackend
from qa.critic import Critic
from state.errors import StudioError
from state.io import logical_path,write_json


def test_native_recovery_and_concurrent_user_guard():
    import win32com.client
    root=Path(__file__).resolve().parents[2]
    module=importlib.util.spec_from_file_location("native_recovery_fixture",Path(__file__).parents[1]/"fixtures/live_fixture.py");fixture=importlib.util.module_from_spec(module);module.loader.exec_module(fixture)
    module=importlib.util.spec_from_file_location("native_recovery_reviewer",Path(__file__).with_name("test_live_transactions.py"));reviewer=importlib.util.module_from_spec(module);module.loader.exec_module(reviewer)
    project,source,spec=fixture.prepare(root);app=None;owned=False;backend=None
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Refusing to interfere with open user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        deck=app.Presentations.Open(str(logical_path(source)),False,False,True);deck.Windows.Item(1).WindowState=2
        backend=WindowsLiveBackend.attach(root,source);deck=backend.deck;set_property(deck,"AutoSaveOn",False)
        session=LiveSession(root,project,backend);session.attach("manual")
        before=backend.inspect();slide=before["slides"][1];target=next(obj for obj in slide["objects"] if obj["role"]=="body")
        key=(slide["slide_id"],target["object_id"])
        scope={"objects":[{"slide_id":s["slide_id"],"object_id":obj["object_id"],"protection":"MAY_CHANGE" if (s["slide_id"],obj["object_id"])==key else "MUST_NOT_CHANGE"} for s in before["slides"] for obj in s["objects"]]}
        patch={"schema_version":"1.0","patch_id":"recovery_copy","operations":[{"slide_id":key[0],"object_id":key[1],"expected_fingerprint":target["fingerprint"],"operation":"set_text","value":"Recorded contributions support a Materials-first review."}]}
        identifier=uuid4().hex
        with pytest.raises(RuntimeError,match="controlled post-apply"):
            session.apply(patch,scope,spec,Critic(root,reviewer.Reviewer(fail_on=2)),transaction_id=identifier)
        recovered=session.recover(identifier)
        assert recovered["status"]=="recovered" and backend.inspect()["fingerprint"]==before["fingerprint"]
        def user_edit(call):
            if call==1:
                title=next(shape for shape in deck.Slides.Item(3).Shapes if str(shape.AlternativeText)=="studio-role:title")
                title.TextFrame.TextRange.Text=spec["slides"][2]["action_title"]+"."
        with pytest.raises(StudioError,match="User changed"):
            session.apply(patch,scope,spec,Critic(root,reviewer.Reviewer(hook=user_edit)))
        assert objects(backend.inspect())[key]["text"]==target["text"]
        assert not bool(deck.Saved)
        write_json(root/"implementation/PHASE_REPORTS/phase_10_recovery_native.json",{"passed":True,"fixture":True,"project_id":project.path.name,"exact_recovery":True,"concurrent_user_edit_preserved":True,"original_not_saved":True,"transaction_id":identifier,"reviewer":"controlled failure injection; native rendering and mutation"})
        session.detach()
    finally:
        if backend is not None:backend.release()
        if app is not None and owned:
            # Drop borrowed child proxies while their owning objects are still alive.
            if backend is not None:backend.deck=None;backend.app=None
            session=backend=batch=opened=deck=title=chart=body=table=None
            import gc
            gc.collect()
            for deck in list(app.Presentations):
                if local_identity(str(deck.FullName))==local_identity(source):
                    if not bool(deck.Saved):deck.Save()
                    deck.Close()
            fixture=deck=None
            gc.collect()
            if int(app.Presentations.Count)==0:app.Quit()
