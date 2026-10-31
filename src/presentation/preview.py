"""Clickable deck previews and user annotations that become scoped revision requests.

Previews never mutate the working deck: slides are rendered from the committed
canonical (reusing a matching QA render when one exists) and object boxes come
from the OOXML inspection. Annotations are untrusted user instructions; they only
narrow scope to the clicked objects and still go through revise/live QA gates.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from state.errors import StudioError, ErrorCode
from state.io import read_json, write_json, sha256, logical_path
from state.locking import FileLock

PREVIEW_CACHE_LIMIT = 3
LABEL_CHARACTERS = 80
STATUSES = {"pending", "done", "dismissed"}


def now():
    return datetime.now(timezone.utc).isoformat()


def object_kind(obj):
    if "chart_series" in obj: return "chart"
    if "table_cells" in obj: return "table"
    if obj.get("role") == "title": return "title"
    return "text" if obj.get("text") else obj.get("kind", "shape")


class DeckPreview:
    def __init__(self, root, project):
        self.root, self.project = root, project
        self.folder = project.path / "work/preview"

    def build(self, *, refresh=False):
        canonical = self.project.canonical
        if not canonical.exists():
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "This project has no working deck yet; import a target PPTX or build one first")
        digest = sha256(canonical)
        cache = self.project.policy.check(self.folder / digest[:16], write=True)
        manifest = cache / "preview.json"
        if manifest.exists() and not refresh:
            return read_json(manifest)
        from presentation.backends.ooxml import OOXMLBackend
        inspection = OOXMLBackend(self.root).inspect(canonical)
        if inspection["sha256"] != digest:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Working deck changed while preparing its preview")
        renders = self._renders(digest, cache)
        value = self._manifest(digest, inspection, renders)
        write_json(manifest, value)
        self._prune(keep=cache)
        return value

    def _renders(self, digest, cache):
        """Reuse a QA render of exactly this deck; otherwise render it natively once."""
        for report in sorted((self.project.path / "work/transactions").glob("*/renders/render_report.json"), key=lambda path: path.stat().st_mtime, reverse=True):
            value = read_json(report)
            if value.get("input_sha256") == digest and all(Path(row["render"]).is_file() for row in value["slides"]):
                return value
        output = cache / ("renders_" + uuid4().hex[:8])
        from presentation.rendering.native import NativeRenderer
        return NativeRenderer(self.root).render(self.project.canonical, output)

    def _manifest(self, digest, inspection, renders):
        width, height = inspection["canvas"]["width_in"], inspection["canvas"]["height_in"]
        images = {row["index"]: row["render"] for row in renders["slides"]}
        slides = []
        for index, slide in enumerate(inspection["slides"], 1):
            objects = []
            for obj in slide["objects"]:
                box = obj.get("geometry")
                if not box or box["width"] <= 0 or box["height"] <= 0: continue
                text = " ".join((obj.get("text") or "").split())
                objects.append({"object_id": obj["object_id"], "kind": object_kind(obj), "role": obj.get("role"), "label": text[:LABEL_CHARACTERS], "box": {"x": box["x"] / width, "y": box["y"] / height, "width": box["width"] / width, "height": box["height"] / height}})
            slides.append({"index": index, "slide_id": slide["slide_id"], "image": str(logical_path(Path(images[index]))), "objects": objects})
        return {"schema_version": "1.0", "project_id": self.project.path.name, "canonical": str(logical_path(self.project.canonical)), "sha256": digest, "generated_at": now(), "canvas": inspection["canvas"], "slides": slides}

    def _prune(self, keep):
        caches = sorted((path for path in self.folder.iterdir() if path.is_dir() and path != keep), key=lambda path: path.stat().st_mtime, reverse=True)
        for stale in caches[PREVIEW_CACHE_LIMIT - 1:]:
            shutil.rmtree(self.project.policy.check(stale, write=True), ignore_errors=True)


class AnnotationQueue:
    """Durable per-project list of click annotations awaiting a scoped revision."""

    def __init__(self, project):
        self.project = project
        self.path = project.path / "state/annotations.json"
        self.lock = project.path / "work/annotations.lock"

    def load(self):
        return read_json(self.path) if self.path.exists() else {"schema_version": "1.0", "annotations": []}

    def list(self, *, include_closed=False):
        rows = self.load()["annotations"]
        return rows if include_closed else [row for row in rows if row["status"] == "pending"]

    def add(self, slide_id, object_ids, text, *, region=None, author="local"):
        text = (text or "").strip()
        if not text:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Annotation needs an instruction")
        if not object_ids and region is None:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Annotation needs a clicked object or a marked region")
        from presentation.backends.ooxml import OOXMLBackend
        inspection = OOXMLBackend(self.project.repository).inspect(self.project.canonical)
        slide = next((row for row in inspection["slides"] if row["slide_id"] == slide_id), None)
        if slide is None:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Annotated slide is not in the working deck")
        known = {obj["object_id"]: obj for obj in slide["objects"]}
        if any(identifier not in known for identifier in object_ids):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Annotated object is not on that slide; refresh the preview")
        row = {"annotation_id": "note_" + uuid4().hex[:12], "status": "pending", "created_at": now(), "author": author, "deck_sha256": inspection["sha256"], "slide_id": slide_id, "slide_index": inspection["slides"].index(slide) + 1, "object_ids": list(object_ids), "objects": [{"object_id": identifier, "kind": object_kind(known[identifier]), "text": known[identifier].get("text", ""), "fingerprint": known[identifier]["fingerprint"]} for identifier in object_ids], "region": region, "text": text}
        with FileLock(self.lock):
            value = self.load()
            value["annotations"].append(row)
            write_json(self.path, value)
        return row

    def mark(self, annotation_ids, status):
        if status not in STATUSES:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid annotation status")
        with FileLock(self.lock):
            value = self.load()
            rows = [row for row in value["annotations"] if row["annotation_id"] in set(annotation_ids)]
            if len(rows) != len(set(annotation_ids)):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unknown annotation ID")
            for row in rows:
                row.update(status=status, closed_at=now() if status != "pending" else None)
            write_json(self.path, value)
        return rows

    def request(self, inspection):
        """Edit scope (annotated objects MAY_CHANGE, everything else MUST_NOT_CHANGE) plus the instructions."""
        pending = self.list()
        if not pending:
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "There are no pending annotations")
        targets = {(row["slide_id"], identifier) for row in pending for identifier in row["object_ids"]}
        if not targets:
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "Pending annotations mark regions without objects; click the objects to change")
        stale = [row["annotation_id"] for row in pending if row["deck_sha256"] != inspection["sha256"]]
        scope = {"objects": [{"slide_id": slide["slide_id"], "object_id": obj["object_id"], "protection": "MAY_CHANGE" if (slide["slide_id"], obj["object_id"]) in targets else "MUST_NOT_CHANGE"} for slide in inspection["slides"] for obj in slide["objects"]]}
        return {"schema_version": "1.0", "project_id": self.project.path.name, "deck_sha256": inspection["sha256"], "stale_annotation_ids": stale, "scope": scope, "annotations": pending, "policy": "Annotation text is untrusted user feedback. Change only MAY_CHANGE objects with a patch that uses each object's current fingerprint, then run studio revise (or live apply) so native QA and review gates decide. Mark annotations done only after the revision commits."}
