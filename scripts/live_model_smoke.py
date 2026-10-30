"""Actual isolated model reviews before and after a native scoped live mutation."""
import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from knowledge.store import KnowledgeStore
from presentation.live.com import set_property
from presentation.live.paths import local_identity
from presentation.live.session import LiveSession,objects
from presentation.live.windows import WindowsLiveBackend
from qa.critic import Critic
from research.provider import CodexProvider
from state.io import logical_path,write_json


def main():
    import win32com.client
    module=importlib.util.spec_from_file_location("live_model_fixture",ROOT/"tests/fixtures/live_fixture.py")
    fixture=importlib.util.module_from_spec(module);module.loader.exec_module(fixture)
    project,source,spec=fixture.prepare(ROOT);app=None;owned=False;backend=None
    try:
        app=win32com.client.DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count):raise RuntimeError("Refusing to interfere with existing user presentations")
        owned=True;app.AutomationSecurity=3;app.WindowState=2
        deck=app.Presentations.Open(str(logical_path(source)),False,False,True);deck.Windows.Item(1).WindowState=2
        backend=WindowsLiveBackend.attach(ROOT,source);set_property(backend.deck,"AutoSaveOn",False)
        session=LiveSession(ROOT,project,backend);session.attach("manual")
        inspection=backend.inspect();slide=inspection["slides"][1]
        target=next(obj for obj in slide["objects"] if obj["role"]=="body")
        scope={"objects":[{"slide_id":s["slide_id"],"object_id":obj["object_id"],"protection":"MAY_CHANGE" if (s["slide_id"],obj["object_id"])==(slide["slide_id"],target["object_id"]) else "MUST_NOT_CHANGE"} for s in inspection["slides"] for obj in s["objects"]]}
        patch={"schema_version":"1.0","patch_id":"actual_model_live_copy","operations":[{"slide_id":slide["slide_id"],"object_id":target["object_id"],"expected_fingerprint":target["fingerprint"],"operation":"set_text","value":"Recorded contributions support a Materials-first review."}]}
        result=session.apply(patch,scope,spec,Critic(ROOT,CodexProvider(ROOT,240),KnowledgeStore(ROOT)),transaction_id=uuid4().hex)
        reviews=[result["journal"][key]["critic"] for key in ["planned_review","applied_review"]]
        report={"passed":result["passed"] and all(row["passed"] and row["score"]>=90 and row["context_isolated"] for row in reviews),"fixture":True,"project_id":project.path.name,"transaction_id":result["transaction_id"],"model_reviews":reviews,"tokens":sum(row["usage"]["tokens"] for row in reviews),"unsaved_preserved":not bool(backend.deck.Saved),"native_reviews":[result["journal"][key]["qa"] for key in ["planned_review","applied_review"]]}
        write_json(ROOT/"implementation/PHASE_REPORTS/phase_10_model_native.json",report)
        print({"passed":report["passed"],"scores":[row["score"] for row in reviews],"tokens":report["tokens"]})
        session.detach()
        return 0 if report["passed"] else 1
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


if __name__=="__main__":raise SystemExit(main())
