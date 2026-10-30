"""Real Office proof on an isolated synthetic project; preserve user documents."""
from pathlib import Path
from uuid import uuid4
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"src"))
from state.project import Project
from state.io import read_json,write_json,logical_path,native_path,sha256
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from layout.baseline import BaselineLayout
from presentation.rendering.native import NativeRenderer
from qa.transaction import PresentationValidator
from presentation.live.paths import local_identity
from presentation.live.target_update import matching_presentations
import pythoncom
import win32com.client

pythoncom.CoInitialize()
app=None;created_app=False;original_window=None;project=None
try:
    try:app=win32com.client.GetActiveObject("PowerPoint.Application")
    except pythoncom.com_error as exc:
        if exc.hresult not in {-2147221021,-2147221005}:raise
        app=win32com.client.DispatchEx("PowerPoint.Application");created_app=int(app.Presentations.Count)==0
    def user_documents():
        rows=[]
        for deck in app.Presentations:
            try:rows.append((str(deck.Name),bool(deck.Saved)))
            except pythoncom.com_error:rows.append(("metadata_unavailable",None))
        return rows
    before=user_documents()
    try:original_window=app.ActiveWindow
    except Exception:pass
    project=Project.create(root,"qa-smoke-"+uuid4().hex[:12])
    write_json(project.path/"work/native_target_proof_owner.json",{"script":"scripts/verify_target_updates.py","project_id":project.path.name})
    backend=OOXMLBackend(root);renderer=NativeRenderer(root,timeout_seconds=180)
    spec=read_json(root/"tests/fixtures/basic_spec.json")
    tx=project.begin()
    PresentationCompiler(root,BaselineLayout(root),backend).compile(**spec,destination=project.candidate(tx))
    qa=project.candidate(tx).parent/"initial_qa"
    project.commit(tx,PresentationValidator(root,backend,renderer,qa))
    working=str(logical_path(project.canonical))
    deck=app.Presentations.Open(working,False,False,True)
    deck.Windows.Item(1).View.GotoSlide(2)
    proof=[]
    def target():
        matches=matching_presentations(app,project.canonical)
        assert len(matches)==1
        return matches[0]
    def revise(label,text):
        tx=project.begin()
        inspection=backend.inspect(project.canonical);slide=inspection["slides"][0]
        obj=next(o for o in slide["objects"] if o["role"]=="title")
        scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MUST_CHANGE" if (s["slide_id"],o["object_id"])==(slide["slide_id"],obj["object_id"]) else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
        patch={"schema_version":"1.0","patch_id":label,"operations":[{"slide_id":slide["slide_id"],"object_id":obj["object_id"],"expected_fingerprint":obj["fingerprint"],"operation":"set_text","value":text}]}
        backend.patch(project.canonical,project.candidate(tx),patch,scope)
        output=project.candidate(tx).parent/"native_qa"
        state=project.commit(tx,PresentationValidator(root,backend,renderer,output,inspection,scope))
        report=read_json(output/"render_report.json")
        assert report["passed"] and report["session_mode"]=="borrowed"
        assert len([p for p in (project.path/"presentation").glob("*.pptx") if not p.name.startswith("~$")])==1
        proof.append({"case":label,"passed":True,"generation":state["generation"],"target":working,"render_report":str(logical_path(output/"render_report.json")),"sha256":sha256(project.canonical)})
    revise("target_open_saved","The open working target updates in place")
    reopened=target()
    assert any(str(s.TextFrame.TextRange.Text)=="The open working target updates in place" for s in reopened.Slides.Item(1).Shapes if bool(s.HasTextFrame))
    assert int(reopened.Windows.Item(1).View.Slide.SlideIndex)==2
    body=next(s for s in reopened.Slides.Item(1).Shapes if str(s.AlternativeText)=="studio-role:body")
    body.TextFrame.TextRange.Text="A user's unsaved draft is retained"
    assert not bool(reopened.Saved)
    revise("target_open_unsaved","The existing draft and revision stay together")
    reopened=target()
    assert bool(reopened.Saved)
    assert any(str(s.TextFrame.TextRange.Text)=="A user's unsaved draft is retained" for s in reopened.Slides.Item(1).Shapes if bool(s.HasTextFrame))
    reopened.Close()
    revise("target_closed_app_running","The same file updates while PowerPoint is running")
    assert not matching_presentations(app,project.canonical)
    after=user_documents()
    assert before==after,"Unrelated user presentations must remain unchanged"
    result={"passed":True,"project_id":project.path.name,"cases":proof,"unrelated_presentations_preserved":True,"preexisting_count":len(before),"public_working_files":1}
    write_json(root/"implementation/PHASE_REPORTS/target_update_native_20261022.json",result)
    print({"passed":True,"cases":[p["case"] for p in proof],"unrelated_presentations_preserved":True,"project":project.path.name})
finally:
    if app is not None and project is not None:
        for deck in matching_presentations(app,project.canonical):
            # Only this synthetic fixture is owned by this test.
            deck.Saved=True;deck.Close()
    if original_window is not None:
        try:original_window.Activate()
        except Exception:pass
    if app is not None and created_app and int(app.Presentations.Count)==0:app.Quit()
    pythoncom.CoUninitialize()
