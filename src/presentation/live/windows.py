"""Working-target adapter; borrow Office and save through reviewed workflows."""
import os
from pathlib import Path
from uuid import uuid4

from presentation.live.inspection import inspect_deck,selection_context,comments,native_shapes,slide_identity,object_identity
from presentation.rendering.metrics import export_slides
from presentation.live.paths import local_identity
from security.files import FileRegistry
from security.paths import PathPolicy
from state.errors import StudioError,ErrorCode
from state.io import logical_path,native_path,read_yaml,write_json,sha256,fingerprint
from presentation.live.com import set_property
from presentation.live.disk import disk_fingerprint


def live_policy(repository):
    """Never open or save immutable project originals through a writable COM handle."""
    originals=[repository/"library/knowledge/packages",*(repository/"projects").glob("*/input"),*(repository/"runtime/test_projects").glob("*/input"),*(repository/"runtime/others").glob("*/input")]
    return PathPolicy([repository],[repository/"runtime",repository/"projects"],originals)


class WindowsLiveBackend:
    def __init__(self,repository,app,deck):
        self.root,self.app,self.deck=repository,app,deck
        self.policy=live_policy(repository)
        self.registry=FileRegistry(self.policy,read_yaml(repository/"config/security/files.yaml"))
        self.target=str(deck.FullName)
        self.local_target=local_identity(self.target)
        try:self.disk_fingerprint=disk_fingerprint(Path(self.local_target))
        except StudioError as exc:
            if exc.code!=ErrorCode.CAPABILITY_UNAVAILABLE:raise
            self.disk_fingerprint=None

    @classmethod
    def attach(cls,repository,target,*,open_if_missing=False):
        if os.name!="nt":raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Live PowerPoint requires Windows; use safe file mode")
        import pythoncom
        import win32com.client
        try:
            app=win32com.client.GetActiveObject("PowerPoint.Application")
        except Exception as exc:
            if open_if_missing and getattr(exc,"hresult",None) in {-2147221021,-2147221005}:
                app=win32com.client.DispatchEx("PowerPoint.Application")
            else:
                raise StudioError(ErrorCode.LIVE_ATTACH_FAILED,"PowerPoint attachment failed for the selected working target; no replacement deck was created") from exc
        policy=live_policy(repository)
        path=policy.check(Path(target),write=True)
        if path.suffix.lower()!=".pptx":raise StudioError(ErrorCode.SECURITY_BLOCK,"Live collaboration accepts validated PPTX working targets only")
        from presentation.live.target_update import matching_presentations
        candidates=matching_presentations(app,path)
        if len(candidates)>1:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Target presentation identity is ambiguous")
        if not candidates and open_if_missing:
            FileRegistry(policy,read_yaml(repository/"config/security/files.yaml")).inspect(path,"canonical_target")
            candidates=[app.Presentations.Open(str(logical_path(path)),False,False,True)]
        if not candidates:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Requested target is not open; explicit open_if_missing is required")
        backend=cls(repository,app,candidates[0]);backend._com_initialized=True
        return backend

    def release(self):
        # The terminal owns its STA lifetime. Detaching borrowed Office proxies
        # must not tear down an apartment while other presentation proxies exist.
        self._com_initialized=False

    def inspect(self):
        if str(self.deck.FullName)!=self.target:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Live presentation identity changed")
        first=inspect_deck(self.deck);second=inspect_deck(self.deck)
        if first["fingerprint"]!=second["fingerprint"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Presentation changed during live inspection")
        return second

    def selection(self,generation):return selection_context(self.app,self.deck,self.inspect(),generation)
    def comments(self):
        from presentation.live.file_comments import read_comments
        from presentation.backends.ooxml import OOXMLBackend
        # Current snapshot includes modern threads that the legacy COM collection
        # may omit and preserves unsaved comments without trusting a stale disk file.
        snapshot=self.snapshot()
        return read_comments(OOXMLBackend(self.root),Path(snapshot["path"]))

    def pause_autosave(self):
        try:enabled=bool(self.deck.AutoSaveOn)
        except Exception:
            if self.target.lower().startswith("https://"):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Cloud AutoSave capability is unknown; use a local working copy before mutation")
            return {"available":False,"initial":None,"paused":False}
        if enabled:set_property(self.deck,"AutoSaveOn",False)
        if bool(self.deck.AutoSaveOn):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Cannot prevent AutoSave before post-apply QA; use a local working copy")
        return {"available":True,"initial":enabled,"paused":enabled}

    def restore_autosave(self,policy):
        if policy.get("initial") and bool(self.deck.Saved):set_property(self.deck,"AutoSaveOn",True);return True
        return False

    def snapshot(self):
        before=self.inspect();folder=native_path(self.root/"runtime/live_snapshots"/uuid4().hex);folder.mkdir(parents=True)
        path=folder/("snapshot_"+uuid4().hex[:8]+".pptx")
        self.deck.SaveCopyAs(str(logical_path(path)),24)
        after=self.inspect()
        if before["fingerprint"]!=after["fingerprint"] or before["name"]!=after["name"] or before["saved"]!=after["saved"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Snapshot did not preserve stable live authority/name/unsaved state")
        self.registry.inspect(path,"temporary_input")
        return {"path":str(path),"sha256":sha256(path),"live_fingerprint":after["fingerprint"],"saved":after["saved"]}

    def render(self,source,output):
        source=self.policy.check(source);self.registry.inspect(source,"temporary_input")
        output=self.policy.check(output,write=True)
        if output.exists():raise StudioError(ErrorCode.FILE_CONFLICT,"Live render requires a fresh directory")
        before=self.inspect();auxiliary=None;input_hash=sha256(source)
        try:
            auxiliary=self.app.Presentations.Open(str(logical_path(source)),True,False,False)
            if str(auxiliary.FullName).casefold()==self.target.casefold():
                auxiliary=None
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Renderer refuses to take ownership of the live target")
            slides=export_slides(auxiliary,output)
            result={"schema_version":"1.0","passed":True,"errors":[],"renderer":"WindowsPowerPointLiveSnapshot","version":str(self.app.Version),"input_sha256":input_hash,"canvas_pt":{"width":float(auxiliary.PageSetup.SlideWidth),"height":float(auxiliary.PageSetup.SlideHeight)},"slides":slides}
        finally:
            if auxiliary is not None:auxiliary.Close()
        if self.inspect()["fingerprint"]!=before["fingerprint"] or sha256(source)!=input_hash:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Live target or review snapshot changed while rendering")
        write_json(output/"render_report.json",result);return result

    def _shape(self,sid,oid):
        for slide in self.deck.Slides:
            if slide_identity(slide)==sid:
                for shape in native_shapes(slide.Shapes):
                    if object_identity(shape)==oid:return shape
        raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Requested live shape no longer exists")

    def apply(self,operation,*,text_scope=None):
        current=self.inspect();target=next((o for s in current["slides"] if s["slide_id"]==operation["slide_id"] for o in s["objects"] if o["object_id"]==operation["object_id"]),None)
        if target is None or target["fingerprint"]!=operation["expected_fingerprint"]:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"User changed the affected object immediately before mutation")
        shape=self._shape(operation["slide_id"],operation["object_id"]);kind=operation["operation"];value=operation["value"]
        if kind=="set_text":
            if not isinstance(value,str):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Live text replacement must be a string")
            if text_scope is None:shape.TextFrame.TextRange.Text=value
            else:
                if bool(shape.HasTable):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Selected table text requires a cell-specific operation; whole-table text replacement is unsafe")
                selected=shape.TextFrame.TextRange.Characters(text_scope["start"],text_scope["length"])
                if str(selected.Text)!=text_scope["text"]:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Selected text range changed before mutation")
                selected.Text=value
        elif kind=="set_geometry":
            import math
            if not isinstance(value,dict) or set(value)!={"x","y","width","height"} or any(type(n) not in {float,int} or not math.isfinite(n) for n in value.values()) or min(value["width"],value["height"])<=0:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid live geometry")
            shape.Left=value["x"]*72;shape.Top=value["y"]*72;shape.Width=value["width"]*72;shape.Height=value["height"]*72
        elif kind=="set_fill":
            import re
            if not isinstance(value,str) or not re.fullmatch("[A-Fa-f0-9]{6}",value):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid RGB fill")
            shape.Fill.Solid();shape.Fill.ForeColor.RGB=int(value[0:2],16)+256*int(value[2:4],16)+65536*int(value[4:6],16)
        elif kind=="repair_chart_axis":
            if value!="zero_origin" or not bool(shape.HasChart):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Live axis repair requires a native bar chart")
            if int(shape.Chart.ChartType) not in {57,58,59}:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Live axis repair is limited to horizontal bar charts")
            shape.Chart.Axes(2,1).Crosses=-4105;shape.Chart.Axes(1,1).Crosses=2
        else:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Unsupported live operation")
        return self.inspect()

    def restore(self,sid,oid,prior,expected_fingerprint):
        current=self.inspect();actual=next((obj for slide in current["slides"] if slide["slide_id"]==sid for obj in slide["objects"] if obj["object_id"]==oid),None)
        if actual is None or actual["fingerprint"]!=expected_fingerprint:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Recovery target changed after the agent's mutation")
        shape=self._shape(sid,oid)
        if prior.get("text") is not None and bool(shape.HasTextFrame):
            shape.TextFrame.TextRange.Text=prior["text"];position=1
            for run in prior.get("font_runs",[]):
                length=len(run["text"].encode("utf-16-le"))//2
                if length:
                    font=shape.TextFrame.TextRange.Characters(position,length).Font
                    font.Name=run["name"];font.Size=run["size"];font.Bold=run["bold"];font.Italic=run["italic"];font.Color.RGB=run["color"]
                position+=length
        shape.Left=prior["x_pt"];shape.Top=prior["y_pt"];shape.Width=prior["width_pt"];shape.Height=prior["height_pt"]
        if prior.get("fill") and prior["fill"]["type"]==1:
            shape.Fill.Solid();shape.Fill.ForeColor.RGB=prior["fill"]["color"];shape.Fill.Transparency=prior["fill"]["transparency"];shape.Fill.Visible=prior["fill"]["visible"]
        if bool(shape.HasChart):
            for axis in prior.get("chart_axes",[]):shape.Chart.Axes(axis["kind"],1).Crosses=axis["crosses"]
        return self.inspect()

    def save(self,policy,*,copy_path=None):
        if policy=="manual":return {"saved":False,"policy":"manual","unsaved_preserved":True}
        if policy=="save_copy":
            if copy_path is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"save_copy requires an explicit output path")
            path=self.policy.check(copy_path,write=True)
            if path.exists():raise StudioError(ErrorCode.FILE_CONFLICT,"Save copy refuses to overwrite an existing artifact")
            before=self.inspect();self.deck.SaveCopyAs(str(logical_path(path)),24)
            if self.inspect()["saved"]!=before["saved"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Copy save changed the user's unsaved state")
            return {"saved":False,"copy":str(path),"policy":policy,"unsaved_preserved":True}
        if policy=="save_existing":
            target=self.policy.check(Path(self.local_target),write=True)
            if self.disk_fingerprint is None:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"save_existing requires a verified readable disk fingerprint; manual/save_copy remain available")
            if disk_fingerprint(target)!=self.disk_fingerprint:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Target disk changed during the live session; preserve it instead of saving over it")
            self.deck.Save();self.disk_fingerprint=disk_fingerprint(target)
            return {"saved":True,"policy":policy}
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"An explicit supported save policy is required")
