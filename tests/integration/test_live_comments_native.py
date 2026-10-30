import importlib.util
import json
from pathlib import Path

from presentation.live.batch import CommentBatch
from presentation.live.com import set_property
from presentation.live.paths import local_identity
from presentation.live.session import LiveSession
from presentation.live.windows import WindowsLiveBackend
from qa.critic import Critic
from state.io import write_json,logical_path


def test_native_comment_batch_resolves_applies_and_preserves_original_comment():
    import pythoncom
    import win32com.client
    root=Path(__file__).resolve().parents[2]
    module=importlib.util.spec_from_file_location("comment_live_fixture",Path(__file__).parents[1]/"fixtures/live_fixture.py");case=importlib.util.module_from_spec(module);module.loader.exec_module(case)
    module=importlib.util.spec_from_file_location("comment_live_reviewer",Path(__file__).with_name("test_live_transactions.py"));control=importlib.util.module_from_spec(module);module.loader.exec_module(control)
    project,source,spec=case.prepare(root,"live-comments");app=None;owned=False;backend=None
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Comment E2E refuses to interfere with user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        opened=app.Presentations.Open(str(logical_path(source)),False,False,True);opened.Windows.Item(1).WindowState=2
        backend=WindowsLiveBackend.attach(root,source);deck=backend.deck;set_property(deck,"AutoSaveOn",False)
        deck.Windows.Item(1).View.GotoSlide(2)
        body=next(shape for shape in deck.Slides.Item(2).Shapes if str(shape.AlternativeText)=="studio-role:body")
        deck.Slides.Item(2).Comments.Add(float(body.Left)+5,float(body.Top)+5,"Fixture Reviewer","FR","Make this text wording concise")
        session=LiveSession(root,project,backend);session.attach()
        inspection=backend.inspect();target=next(o for o in inspection["slides"][1]["objects"] if o["native_id"]==int(body.Id))
        scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MAY_CHANGE" if o["object_id"]==target["object_id"] and s["slide_id"]==spec["slides"][1]["slide_id"] else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
        class Provider(control.Reviewer):
            def complete(self,prompt,schema):
                context=json.loads(prompt.split("DATA=",1)[1]);row=context["instructions"][0]
                obj=next(o for s in context["observed_live_state"]["slides"] if s["slide_id"]==row["slide_id"] for o in s["objects"] if o["object_id"]==row["resolved_target_ids"][0])
                return {"schema_version":"1.1","patch_id":"native_comment_copy","operations":[{"slide_id":row["slide_id"],"object_id":obj["object_id"],"expected_fingerprint":obj["fingerprint"],"operation":"set_text","value":"Recorded contributions support a Materials-first review."}]}
        provider=Provider();batch=CommentBatch(root,session,provider,Critic(root,provider))
        assert not batch.plan(scope,authors=["Another reviewer"])["instructions"]
        observed_comments,_=backend.comments()
        assert len(observed_comments)==1 and observed_comments[0]["text"]=="Make this text wording concise"
        plan=batch.plan(scope,authors=[observed_comments[0]["author"]])
        assert len(plan["instructions"])==1 and plan["instructions"][0]["status"]=="planned"
        result=batch.apply(plan,spec)
        assert result["passed"] and result["original_comments_preserved"] and not bool(deck.Saved)
        retained_comments,_=backend.comments()
        assert len(retained_comments)==1 and retained_comments[0]["text"]=="Make this text wording concise"
        assert not batch.plan(scope)["instructions"]
        write_json(root/"implementation/PHASE_REPORTS/phase_10_comments_native.json",{"passed":True,"fixture":True,"project_id":project.path.name,"native_comment_capture":True,"author_filter":True,"high_confidence_resolution":True,"batch_applied_after_both_reviews":True,"original_comments_preserved":True,"processed_scan_no_op":True,"capabilities":plan["capabilities"],"transaction_id":result["transaction_id"]})
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
