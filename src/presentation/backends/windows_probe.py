import os
from pathlib import Path
from datetime import datetime, timezone

from state.errors import ErrorCode
from state.io import native_path, logical_path


class WindowsPowerPointProbe:
    """Early read-only feasibility probe; full live transactions arrive in Phase 10."""
    def probe(self, snapshot_directory: Path | None = None):
        result = {"schema_version": "1.0", "backend": "WindowsPowerPointAutomationBackend", "time": datetime.now(timezone.utc).isoformat(), "available": False, "capabilities": {}, "presentations": [], "errors": []}
        if os.name != "nt":
            result["errors"].append({"code": ErrorCode.CAPABILITY_UNAVAILABLE.value, "reason": "not_windows"})
            return result
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            result["errors"].append({"code": ErrorCode.CAPABILITY_UNAVAILABLE.value, "reason": "pywin32_missing"})
            return result
        pythoncom.CoInitialize()
        try:
            try:
                app = win32com.client.GetActiveObject("PowerPoint.Application")
            except pythoncom.com_error as exc:
                result["errors"].append({"code": ErrorCode.CAPABILITY_UNAVAILABLE.value, "reason": "no_attachable_running_powerpoint", "hresult": exc.hresult})
                return result
            result["available"] = True
            result["version"] = str(app.Version)
            result["capabilities"]["live_attach"] = True
            for index in range(1, app.Presentations.Count + 1):
                deck = app.Presentations.Item(index)
                try:item = {"name": str(deck.Name), "full_name": str(deck.FullName), "saved": bool(deck.Saved), "slides": int(deck.Slides.Count)}
                except pythoncom.com_error as exc:
                    from presentation.rendering.diagnostics import office_failure
                    result["presentations"].append({"native_index":index,"metadata_available":False,"diagnostic":office_failure(exc)})
                    continue
                try:
                    comments = [{"slide_id": int(slide.SlideID), "count": int(slide.Comments.Count)} for slide in deck.Slides]
                    item["comments"] = comments
                    result["capabilities"]["comments_read"] = True
                except pythoncom.com_error:
                    result["capabilities"]["comments_read"] = False
                if snapshot_directory is not None:
                    # SaveCopyAs preserves the open presentation's name and unsaved state.
                    output = native_path(snapshot_directory)
                    output.mkdir(parents=True, exist_ok=True)
                    copy = output / f"probe_{index}.pptx"
                    if copy.exists():
                        raise FileExistsError("Probe refuses to overwrite a snapshot")
                    deck.SaveCopyAs(str(logical_path(copy)), 24)
                    item["snapshot"] = str(copy)
                    result["capabilities"]["save_copy_snapshot"] = copy.is_file()
                result["presentations"].append(item)
            try:
                window = app.ActiveWindow
                result["active_slide"] = int(window.View.Slide.SlideID)
                selection = window.Selection
                result["selection"] = {"type": int(selection.Type)}
                if int(selection.Type) == 2:
                    result["selection"]["shape_ids"] = [int(s.Id) for s in selection.ShapeRange]
                if int(selection.Type) == 3:
                    result["selection"]["text"] = str(selection.TextRange.Text)
                result["capabilities"]["active_selection_read"] = True
            except Exception:
                result["capabilities"]["active_selection_read"] = False
            return result
        except pythoncom.com_error as exc:
            from presentation.rendering.diagnostics import office_failure
            result["available"]=False
            result["capabilities"]["live_attach"]=False
            result["errors"].append(office_failure(exc))
            return result
        finally:
            pythoncom.CoUninitialize()
