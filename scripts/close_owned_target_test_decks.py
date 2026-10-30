"""Close only synthetic decks created by this target-update verification turn."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"src"))
import pythoncom
import win32com.client
from presentation.live.target_update import matching_presentations
from state.io import read_yaml,write_json,logical_path

owned=["qa-smoke-70fa69f926cf","qa-smoke-19a8155b3d37","qa-smoke-68b5004d1ad9","qa-smoke-82d95e8a3527"]
pythoncom.CoInitialize()
closed=[]
try:
    app=win32com.client.GetActiveObject("PowerPoint.Application")
    for identifier in owned:
        folder=root/"projects"/identifier
        state=read_yaml(folder/"project.yaml")
        assert state["project_id"]==identifier
        target=folder/"presentation/canonical.pptx"
        for deck in matching_presentations(app,target):
            if not bool(deck.Saved):
                recovery=folder/"work/native_test_cleanup_recovery.pptx"
                assert not recovery.exists()
                deck.SaveCopyAs(str(logical_path(recovery)),24)
                assert recovery.is_file()
            # Only these explicitly owned synthetic fixtures may be discarded.
            deck.Saved=True;deck.Close();closed.append(identifier)
    write_json(root/"implementation/PHASE_REPORTS/target_test_cleanup_20261022.json",{"closed_owned_fixture_ids":closed,"user_presentations_closed":False,"application_quit":False})
    print({"closed_owned_fixture_ids":closed,"user_presentations_closed":False})
finally:pythoncom.CoUninitialize()
