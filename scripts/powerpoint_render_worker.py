"""Isolated native rendering of a trusted working copy; no live editing."""
import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone


def render(source: Path, destination: Path, slide_indices=None,progress=None):
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "src"), str(root / "runtime/python_packages")]
    from presentation.backends.ooxml import OOXMLBackend
    from state.io import logical_path
    backend = OOXMLBackend(root)
    validation = backend.validate(source)
    if not validation["passed"]:
        return validation
    destination = backend.policy.check(destination, write=True)
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    application, deck = None, None
    owned = False
    result={"passed":False,"errors":[]}
    try:
        if progress:progress(stage="connect_powerpoint")
        try:
            application = win32com.client.GetActiveObject("PowerPoint.Application")
        except pythoncom.com_error as exc:
            if getattr(exc,"hresult",None) not in {-2147221021,-2147221005}:
                raise
            application = win32com.client.DispatchEx("PowerPoint.Application")
            owned = int(application.Presentations.Count) == 0
        # Borrow a running app, including the empty start screen. Only our unique
        # read-only staging deck is owned; never change global Office settings.
        existing = int(application.Presentations.Count)
        if owned:
            application.AutomationSecurity = 3
            application.DisplayAlerts = 1
        destination.mkdir(parents=True, exist_ok=True)
        if progress:progress(stage="open_deck")
        deck = application.Presentations.Open(str(logical_path(source.resolve())), True, False, False)
        from presentation.live.paths import local_identity
        if local_identity(str(deck.FullName)) != local_identity(source) or not bool(deck.ReadOnly):
            deck = None
            raise RuntimeError("Renderer did not receive its exact read-only staging deck")
        from presentation.rendering.metrics import export_slides
        slides=export_slides(deck,destination,slide_indices,progress=progress)
        result.update({"schema_version": "1.0", "passed": True, "renderer": "WindowsPowerPoint", "session_mode":"owned" if owned else "borrowed", "preexisting_presentations":existing, "version": str(application.Version), "time": datetime.now(timezone.utc).isoformat(), "canvas_pt": {"width": float(deck.PageSetup.SlideWidth), "height": float(deck.PageSetup.SlideHeight)}, "slides": slides})
        return result
    except Exception as exc:
        from presentation.rendering.diagnostics import office_failure
        result["errors"].append(office_failure(exc))
        return result
    finally:
        try:
            if progress:progress(stage="cleanup")
            if deck is not None:
                deck.Close()
            if application is not None and owned and int(application.Presentations.Count) == 0:
                application.Quit()
        except Exception as exc:
            from presentation.rendering.diagnostics import office_failure
            result["passed"]=False
            result["errors"].append({**office_failure(exc),"stage":"cleanup"})
        finally:
            pythoncom.CoUninitialize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--slides")
    parser.add_argument("--progress",type=Path)
    args = parser.parse_args()
    progress_state={"marker":None,"time":0.0}
    def progress(**values):
        marker=(values.get('stage'),values.get('slide'))
        current=time.monotonic()
        if marker==progress_state['marker'] and current-progress_state['time']<2:
            return
        from state.io import write_json
        write_json(args.progress,{**values,"time":datetime.now(timezone.utc).isoformat()})
        progress_state.update(marker=marker,time=current)
    result = render(args.source,args.output,[int(value) for value in args.slides.split(",")] if args.slides else None,progress=progress if args.progress else None)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"]}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
