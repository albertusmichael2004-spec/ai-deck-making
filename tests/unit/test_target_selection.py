from pathlib import Path
from types import SimpleNamespace
from presentation.live.target_update import matching_presentations


def test_inaccessible_preview_does_not_block_exact_target_or_select_other_deck(tmp_path):
    class Preview:
        @property
        def Name(self):raise RuntimeError("Automation rights are not granted")
    target=tmp_path/"canonical.pptx"
    selected=SimpleNamespace(Name="canonical.pptx",FullName=str(target))
    other=SimpleNamespace(Name="canonical.pptx",FullName=str(tmp_path/"different"/"canonical.pptx"))
    app=SimpleNamespace(Presentations=[Preview(),other,selected])
    assert matching_presentations(app,target)==[selected]


def test_live_cli_defaults_to_same_canonical_with_save_existing(repo,project,monkeypatch):
    import cli.live_commands as commands
    from presentation.live.windows import WindowsLiveBackend
    from presentation.live.session import LiveSession
    calls=[]
    backend=SimpleNamespace(release=lambda:None)
    def attach(root,target,**kwargs):
        calls.append((Path(target),kwargs));return backend
    monkeypatch.setattr(WindowsLiveBackend,"attach",attach)
    monkeypatch.setattr(LiveSession,"attach",lambda self,policy:{"policy":policy})
    args=SimpleNamespace(target=None,project_id=project.path.name,action="attach",open_if_missing=True,save_policy=None,output=None)
    result=commands.execute_local(repo,args)
    assert result["policy"]=="save_existing"
    assert calls==[(project.canonical,{"open_if_missing":True})]
