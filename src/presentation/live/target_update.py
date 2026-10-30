"""Refresh the exact managed working target after a validated file commit.

The working path is stable. Office is borrowed, never quit. A saved target is
released only after QA; on failure the same original path is reopened.
"""
import os
import threading
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from state.errors import ErrorCode, StudioError
from state.io import fingerprint, logical_path, write_json

_sta=threading.local()


def ensure_sta():
    # The terminal owns the apartment lifetime. Per-target CoUninitialize can
    # disconnect other still-live Office proxies in the same terminal thread.
    if not getattr(_sta,"initialized",False):
        import pythoncom
        pythoncom.CoInitialize();_sta.initialized=True


def matching_presentations(app,target):
    from presentation.live.paths import local_identity
    result=[]
    for deck in app.Presentations:
        try:
            name=getattr(deck,"Name",None)
            if name is not None and str(name).casefold()!=Path(target).name.casefold():continue
            identity=local_identity(str(deck.FullName))
        except StudioError:
            # An unrelated cloud URL without a registered local mapping cannot
            # become the selected local target merely because it is active.
            continue
        except Exception as exc:
            from presentation.rendering.diagnostics import office_failure
            if office_failure(exc)["reason"]=="office_automation_denied":continue
            raise
        if identity==local_identity(target):result.append(deck)
    return result


class TargetUpdate:
    def __init__(self, project, backend=None):
        self.project,self.backend=project,backend
        self.closed=False; self.finished=False; self.before=None; self.autosave={}
        self.path=None; self.view=None; self.window=None

    @classmethod
    def discover(cls,project):
        binding=cls(project)
        if os.name!="nt" or project.state()["validation_policy"]!="presentation" or not project.canonical.exists():
            return binding
        import pythoncom
        import win32com.client
        ensure_sta()
        try:
            try:app=win32com.client.GetActiveObject("PowerPoint.Application")
            except pythoncom.com_error as exc:
                if getattr(exc,"hresult",None) in {-2147221021,-2147221005}:return binding
                raise
            from presentation.live.windows import WindowsLiveBackend
            matches=matching_presentations(app,project.canonical)
            if len(matches)>1:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"More than one open window claims the managed working target")
            if matches:binding.backend=WindowsLiveBackend(project.repository,app,matches[0])
            return binding
        except Exception:
            binding.finish()
            raise

    def _record(self,status,**extra):
        if self.path is not None:
            self.record.update(status=status,**extra)
            write_json(self.path,self.record)

    def prepare_source(self,*,allow_source_changes=True):
        if self.backend is None:return
        deck=self.backend.deck
        if bool(deck.ReadOnly):raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"The managed working target is open read-only; unlock that same file before revision")
        folder=self.project.path/"work/target_updates"/uuid4().hex
        folder.mkdir(parents=True)
        self.path=folder/"target.json"
        self.record={"schema_version":"1.0","target":str(logical_path(self.project.canonical)),"status":"preparing","recovery_snapshot":None}
        self._record("preparing")
        self.autosave=self.backend.pause_autosave()
        # A saved user edit in this exact open target is a new source version,
        # not an agent commit. Retain it and its provenance before our revision.
        from state.io import write_yaml
        with (self.project._lock() if allow_source_changes else nullcontext()):
            state=self.project._file_authority();observed=fingerprint(self.project.canonical)
            if observed!=state["canonical_fingerprint"]:
                if not allow_source_changes:raise StudioError(ErrorCode.FILE_CONFLICT,"Working source changed during QA")
                retained=self.project._snapshot()
                if fingerprint(self.project.canonical)!=observed:raise StudioError(ErrorCode.FILE_CONFLICT,"User source changed during capture")
                prior=state["canonical_fingerprint"]
                state["canonical_fingerprint"]=observed;state["generation"]+=1
                write_yaml(self.project.state_path,state)
                self._record("user_source_registered",source_snapshot_id=retained,prior_disk=prior,current_disk=observed)
                self.project.telemetry.record("open_user_source_registered",generation=state["generation"],snapshot_id=retained)
        try:
            self.window=deck.Windows.Item(1) if int(deck.Windows.Count) else None
            if self.window is not None:self.view=int(self.window.View.Slide.SlideIndex)
        except Exception:self.window=None
        if not bool(deck.Saved):
            # Preserve the user's draft and register its save through existing live
            # authority, before beginning our file transaction or planning any edit.
            snapshot=self.backend.snapshot()
            self._record("saving_user_draft",recovery_snapshot=snapshot["path"])
            from presentation.live.session import LiveSession
            self.project.snapshot()
            session=LiveSession(self.project.repository,self.project,self.backend)
            session.attach("save_existing")
            session.save("save_existing")
            session.detach()
        self.before=self.backend.inspect()
        self.disk=fingerprint(self.project.canonical)
        self._record("ready",before_disk=self.disk,before_live=self.before["fingerprint"],view=self.view,with_window=self.window is not None,autosave=self.autosave)

    def before_replace(self):
        if self.backend is None:
            # The user may have opened the target while QA was running. Bind it
            # now but never save intervening unsaved edits as part of this commit.
            discovered=self.discover(self.project)
            if discovered.backend is None:
                discovered.finish();return
            self.backend=discovered.backend
            if not bool(self.backend.deck.Saved):raise StudioError(ErrorCode.FILE_CONFLICT,"User opened and changed the working target during QA; those edits were preserved")
            self.prepare_source(allow_source_changes=False)
        elif self.before is None:
            if not bool(self.backend.deck.Saved):raise StudioError(ErrorCode.FILE_CONFLICT,"User changed the open working target before commit; those edits were preserved")
            self.prepare_source(allow_source_changes=False)
        current=self.backend.inspect()
        if not current["saved"] or current["fingerprint"]!=self.before["fingerprint"] or fingerprint(self.project.canonical)!=self.disk:
            raise StudioError(ErrorCode.FILE_CONFLICT,"User changed the open working target during QA; no revision replaced it")
        self._record("closing_for_validated_replace")
        self.return_window=None
        try:
            from presentation.live.paths import local_identity
            active=self.backend.app.ActiveWindow
            if local_identity(str(active.Presentation.FullName))!=local_identity(self.project.canonical):self.return_window=active
        except Exception:pass
        # Saved is already true: Close cannot discard a user's unsaved draft.
        self.backend.deck.Close()
        self.closed=True
        self._record("closed_for_validated_replace")

    def finish(self):
        if self.finished:return
        self.finished=True
        try:
            if self.backend is not None:
                if self.closed:
                    app=self.backend.app
                    from presentation.live.paths import local_identity
                    matches=matching_presentations(app,self.project.canonical)
                    if len(matches)>1:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Working target was reopened ambiguously during commit")
                    deck=matches[0] if matches else app.Presentations.Open(str(logical_path(self.project.canonical)),False,False,self.window is not None)
                    if local_identity(str(deck.FullName))!=local_identity(self.project.canonical):raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"PowerPoint reopened a different target")
                    from presentation.live.windows import WindowsLiveBackend
                    self.backend=WindowsLiveBackend(self.project.repository,app,deck)
                    if self.view is not None and int(deck.Windows.Count):
                        deck.Windows.Item(1).View.GotoSlide(min(self.view,int(deck.Slides.Count)))
                    if getattr(self,"return_window",None) is not None:
                        try:self.return_window.Activate()
                        except Exception:pass
                    self._record("reopened_same_target",after_disk=fingerprint(self.project.canonical))
                restored=self.backend.restore_autosave(self.autosave)
                if self.autosave.get("initial") and not restored:
                    # Only user draft edits exist in the borrowed target when a
                    # candidate fails; restore the user's original AutoSave choice.
                    from presentation.live.com import set_property
                    set_property(self.backend.deck,"AutoSaveOn",True)
                if not self.closed:self._record("target_unchanged")
        except Exception as exc:
            self._record("reopen_or_restore_pending",error_type=type(exc).__name__)
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED,"The working file remains at the same path; PowerPoint refresh needs recovery",target=str(logical_path(self.project.canonical)),recovery=str(self.path)) from exc

    @classmethod
    def recover(cls,project):
        recovered=[]
        from state.io import read_json,native_path
        for path in (project.path/"work/target_updates").glob("*/target.json"):
            record=read_json(path)
            if record["status"] not in {"ready","preparing","closing_for_validated_replace","closed_for_validated_replace","reopen_or_restore_pending"}:continue
            if native_path(Path(record["target"]))!=native_path(project.canonical):
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Target recovery points to another working file")
            if not project.canonical.is_file():raise StudioError(ErrorCode.SOURCE_CONFLICT,"Target recovery requires the existing managed working file")
            ensure_sta()
            from presentation.live.windows import WindowsLiveBackend
            backend=WindowsLiveBackend.attach(project.repository,project.canonical,open_if_missing=True)
            binding=cls(project,backend);binding.path=path;binding.record=record
            binding.closed=record["status"] not in {"ready","preparing"};binding.view=record.get("view")
            binding.window=True if record.get("with_window") else None
            binding.autosave=record.get("autosave",{})
            binding.finish()
            recovered.append({"id":path.parent.name,"status":"reopened_same_target","target":record["target"]})
        return recovered
