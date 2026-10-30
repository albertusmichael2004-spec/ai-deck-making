"""Same-target exchange protocol with Office stubs, including failure recovery."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from conftest import commit_bytes,byte_validator
from presentation.live.target_update import TargetUpdate
from state.io import sha256,read_json,native_path
from state.errors import StudioError


class Presentations(list):
    def Open(self,path,read_only,untitled,visible):
        assert not read_only and not untitled
        self.events.append(("open",path))
        deck=Deck(path,self);self.append(deck);return deck


class Deck:
    def __init__(self,path,collection):
        self.FullName=str(path);self.Saved=True;self.ReadOnly=False;self.AutoSaveOn=True
        self.collection=collection;self.user_edit=0
        view=SimpleNamespace(Slide=SimpleNamespace(SlideIndex=1),GotoSlide=lambda index:None)
        self.Windows=SimpleNamespace(Count=1,Item=lambda index:SimpleNamespace(View=view))
        self.Slides=SimpleNamespace(Count=1)
    def Close(self):
        assert self.Saved,"Must never discard user edits"
        self.collection.events.append(("close",self.FullName));self.collection.remove(self)


class Backend:
    def __init__(self,root,app,deck):self.root,self.app,self.deck=root,app,deck
    def inspect(self):return {"saved":self.deck.Saved,"fingerprint":sha256(Path(self.deck.FullName))+str(self.deck.user_edit)}
    def pause_autosave(self):
        initial=self.deck.AutoSaveOn;self.deck.AutoSaveOn=False
        return {"initial":initial,"available":True,"paused":initial}
    def restore_autosave(self,policy):
        if policy.get("initial"):self.deck.AutoSaveOn=True
        return True


def setup(project,monkeypatch):
    commit_bytes(project,b"valid:old")
    documents=Presentations();documents.events=[]
    target=Deck(project.canonical,documents);other=Deck(project.path/"work/unrelated.pptx",documents)
    documents.extend([other,target]);app=SimpleNamespace(Presentations=documents)
    bindings=[]
    def discover(cls,selected):
        matches=[d for d in documents if native_path(Path(d.FullName))==project.canonical]
        binding=TargetUpdate(selected,Backend(selected.repository,app,matches[0]) if matches else None)
        bindings.append(binding);return binding
    monkeypatch.setattr(TargetUpdate,"discover",classmethod(discover))
    monkeypatch.setattr("presentation.live.windows.WindowsLiveBackend",Backend)
    def attach(root,path,**kwargs):
        matches=[d for d in documents if native_path(Path(d.FullName))==native_path(path)]
        return Backend(root,app,matches[0] if matches else documents.Open(str(path),False,False,True))
    monkeypatch.setattr(Backend,"attach",staticmethod(attach),raising=False)
    monkeypatch.setattr("presentation.live.target_update.ensure_sta",lambda:None)
    return target,other,documents,bindings


def test_open_target_updates_same_file_and_reopens_without_touching_other_deck(project,monkeypatch):
    target,other,documents,bindings=setup(project,monkeypatch)
    tx=project.begin();project.candidate(tx).write_bytes(b"valid:revised")
    result=project.commit(tx,byte_validator)
    assert result["generation"]==2 and project.canonical.read_bytes()==b"valid:revised"
    assert other in documents and target not in documents and len(documents)==2
    reopened=next(d for d in documents if d is not other)
    assert native_path(Path(reopened.FullName))==project.canonical and reopened.AutoSaveOn
    assert [event[0] for event in documents.events]==["close","open"]
    assert read_json(bindings[-1].path)["status"]=="reopened_same_target"


def test_bad_qa_never_closes_open_target_or_creates_replacement(project,monkeypatch):
    target,other,documents,_=setup(project,monkeypatch)
    tx=project.begin();project.candidate(tx).write_bytes(b"invalid")
    with pytest.raises(StudioError):project.commit(tx,byte_validator)
    assert not documents.events and documents==[other,target]
    assert project.canonical.read_bytes()==b"valid:old" and target.AutoSaveOn


def test_intervening_unsaved_user_edit_is_preserved(project,monkeypatch):
    target,other,documents,_=setup(project,monkeypatch)
    tx=project.begin();project.candidate(tx).write_bytes(b"valid:revised")
    def review(path):
        target.Saved=False;target.user_edit+=1
        return byte_validator(path)
    with pytest.raises(StudioError,match="User changed"):project.commit(tx,review)
    assert target in documents and not target.Saved and target.user_edit==1
    assert not documents.events and project.canonical.read_bytes()==b"valid:old"


def test_replace_failure_reopens_original_same_path_and_preserves_old_bytes(project,monkeypatch):
    target,other,documents,_=setup(project,monkeypatch)
    tx=project.begin();project.candidate(tx).write_bytes(b"valid:revised")
    import state.io as io
    original=io.replace_file
    def fail(source,destination):
        if Path(destination)==project.canonical:raise PermissionError("controlled sharing lock")
        return original(source,destination)
    monkeypatch.setattr(io,"replace_file",fail)
    with pytest.raises(PermissionError):project.commit(tx,byte_validator)
    assert project.canonical.read_bytes()==b"valid:old" and len(documents)==2
    assert other in documents and [e[0] for e in documents.events]==["close","open"]
    assert native_path(Path(documents[-1].FullName))==project.canonical


def test_target_opened_during_qa_is_refreshed_at_the_same_path(project,monkeypatch):
    target,other,documents,_=setup(project,monkeypatch);documents.remove(target)
    tx=project.begin();project.candidate(tx).write_bytes(b"valid:revised")
    def review(path):documents.append(target);return byte_validator(path)
    project.commit(tx,review)
    assert project.canonical.read_bytes()==b"valid:revised" and len(documents)==2
    assert native_path(Path(documents[-1].FullName))==project.canonical


def test_saved_user_source_is_registered_before_revision_and_preserved_on_bad_qa(project,monkeypatch):
    target,other,documents,bindings=setup(project,monkeypatch)
    project.canonical.write_bytes(b"valid:user-saved")
    tx=project.begin()
    assert project.state()["generation"]==2
    assert read_json(bindings[-1].path)["source_snapshot_id"]
    project.candidate(tx).write_bytes(b"invalid")
    with pytest.raises(StudioError):project.commit(tx,byte_validator)
    assert project.canonical.read_bytes()==b"valid:user-saved" and not documents.events


def test_reopen_interruption_recovers_same_committed_target(project,monkeypatch):
    target,other,documents,bindings=setup(project,monkeypatch)
    tx=project.begin();project.candidate(tx).write_bytes(b"valid:revised")
    original=documents.Open
    def interrupted(*args):raise RuntimeError("controlled Office interruption")
    monkeypatch.setattr(documents,"Open",interrupted)
    with pytest.raises(StudioError,match="refresh needs recovery"):project.commit(tx,byte_validator)
    assert project.canonical.read_bytes()==b"valid:revised"
    assert read_json(bindings[-1].path)["status"]=="reopen_or_restore_pending"
    monkeypatch.setattr(documents,"Open",original)
    result=project.recover()
    assert any(row["status"]=="reopened_same_target" for row in result)
    assert len(documents)==2 and other in documents
    assert native_path(Path(documents[-1].FullName))==project.canonical
