import importlib.util
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from presentation.live.com import set_property
from presentation.live.paths import local_identity
from presentation.live.session import LiveSession,objects
from presentation.live.windows import WindowsLiveBackend
from qa.critic import Critic
from state.errors import StudioError
from state.io import write_json,logical_path,sha256


def test_actual_running_powerpoint_selection_unsaved_guard_and_live_revision():
    import pythoncom
    import win32com.client
    root=Path(__file__).resolve().parents[2]
    module=importlib.util.spec_from_file_location("owned_live_case",Path(__file__).parents[1]/"fixtures/live_fixture.py");case=importlib.util.module_from_spec(module);module.loader.exec_module(case)
    module=importlib.util.spec_from_file_location("live_native_review_control",Path(__file__).with_name("test_live_transactions.py"));review_control=importlib.util.module_from_spec(module);module.loader.exec_module(review_control)
    project,source,spec=case.prepare(root);app=None;owned=False;backend=None;session=None
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Native integration refuses to interfere with open user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        opened=app.Presentations.Open(str(logical_path(source)),False,False,True);opened.Windows.Item(1).WindowState=2
        backend=WindowsLiveBackend.attach(root,source);deck=backend.deck
        set_property(deck,"AutoSaveOn",False)
        # A user's unsaved edit outside the requested scope must survive both reviews.
        title=next(shape for shape in deck.Slides.Item(3).Shapes if str(shape.AlternativeText)=="studio-role:title")
        title.TextFrame.TextRange.Text=spec["slides"][2]["action_title"]+"."
        spec["slides"][2]["action_title"]+="."
        session=LiveSession(root,project,backend);session.attach("manual")
        deck.Windows.Item(1).View.GotoSlide(2)
        chart=next(shape for shape in deck.Slides.Item(2).Shapes if bool(shape.HasChart));chart.Select()
        captured=session.selection()
        assert captured["objects"][0]["content_type"]=="chart"
        body=next(shape for shape in deck.Slides.Item(2).Shapes if str(shape.AlternativeText)=="studio-role:body")
        body.TextFrame.TextRange.Characters(1,len(str(body.TextFrame.TextRange.Text))).Select()
        selected=session.selection();assert selected["selection_type"]=="text" and selected["text_scope"]["length"]>0
        import json,os,subprocess,sys
        env=os.environ.copy();env["PYTHONPATH"]=os.pathsep.join([str(root/"src"),str(root/"runtime/python_packages")])
        for action in ["inspect","selection"]:
            command=subprocess.run([sys.executable,"-m","cli.main","live",action,project.path.name],cwd=root,env=env,capture_output=True,text=True,encoding="utf-8",timeout=950)
            assert command.returncode==0,command.stdout+command.stderr
            captured_cli=json.loads(command.stdout)
            assert captured_cli["fingerprint"]==backend.inspect()["fingerprint"] if action=="inspect" else captured_cli["objects"]==selected["objects"]
        inspection=backend.inspect();target=objects(inspection)[(selected["objects"][0]["slide_id"],selected["objects"][0]["object_id"])]
        scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MAY_CHANGE" if o["object_id"]==target["object_id"] and s["slide_id"]==selected["slide_ids"][0] else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
        patch={"schema_version":"1.0","patch_id":"native_selected_copy","operations":[{"slide_id":selected["slide_ids"][0],"object_id":target["object_id"],"expected_fingerprint":target["fingerprint"],"operation":"set_text","value":"Recorded contributions support a Materials-first review."}]}
        with pytest.raises(StudioError):project.begin()
        identifier=uuid4().hex;reviewer=review_control.Reviewer()
        result=session.apply(patch,scope,spec,Critic(root,reviewer),selection=selected,transaction_id=identifier)
        assert result["passed"] and not bool(deck.Saved) and reviewer.calls==2
        after=backend.inspect();assert objects(after)[(spec["slides"][2]["slide_id"],next(o["object_id"] for o in after["slides"][2]["objects"] if o["role"]=="title"))]["text"].rstrip().endswith(".")
        assert session.apply(patch,scope,spec,Critic(root,reviewer),selection=selected,transaction_id=identifier)["no_op"]
        # Reusing a selection from before a successful mutation must be stale.
        with pytest.raises(StudioError):session.apply(patch,scope,spec,Critic(root,reviewer),selection=selected)
        report={"passed":True,"fixture":True,"project_id":project.path.name,"version":str(app.Version),"selected_chart":True,"selected_text":True,"bounded_cli_worker_verified":True,"unsaved_edit_preserved":not bool(deck.Saved),"file_mode_excluded":True,"stale_selection_rejected":True,"replay_no_op":True,"native_planned_qa":result["journal"]["planned_review"]["qa"],"native_applied_qa":result["journal"]["applied_review"]["qa"],"comment_count":len(backend.comments()[0]),"transaction_id":identifier,"model":"controlled reviewer; actual model review is a separate release smoke"}
        write_json(root/"implementation/PHASE_REPORTS/phase_10_native_case.json",report)
        assert session.detach()["unsaved_preserved"]
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
