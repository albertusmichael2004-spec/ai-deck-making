"""Export validated quick-edit canonicals as owned copies in output/Others."""
import re
from pathlib import Path

from security.paths import PathPolicy
from state.errors import ErrorCode, StudioError
from state.io import atomic_bytes, fingerprint, logical_path, sha256
from state.locking import FileLock
from state.project import Project
from state.paths import others_output_path
from state.workspace import Workspaces


def export_others(root, project_id, *, required=False):
    root = Path(root).resolve()
    if not re.fullmatch(r"others-[a-f0-9]{32}", project_id):
        if required:
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "This export command is for Others quick edits")
        return None
    workspaces = Workspaces(root)
    project = Project.open(root, project_id)
    if not project.path.is_relative_to(workspaces.others_base):
        if required:
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "This export command is for Others quick edits")
        return None
    output_root = others_output_path(root)
    policy = PathPolicy([output_root], [output_root])
    output_root.mkdir(parents=True, exist_ok=True)
    with project._lock(), FileLock(output_root / ".export.lock"):
        state = project.state()
        if state["authority"] != "file":
            if required:
                raise StudioError(ErrorCode.FILE_CONFLICT, "Return file authority before exporting a live deck")
            return None
        if not project.canonical.exists():
            if required:
                raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "No validated working PPTX exists yet")
            return None
        source = fingerprint(project.policy.check(project.canonical))
        if state["generation"] < 1 or source != state["canonical_fingerprint"]:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Canonical changed outside the validated workflow")
        metadata = workspaces.metadata(project)
        if metadata.get("category") != "others":
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Quick-edit category is missing")
        record = metadata.get("export")
        if record is None:
            target = next((Path(row["original_path"]).stem for row in metadata["imports"] if row["role"] == "target"), "Presentation")
            label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", target).strip(" .")[:80] or "Presentation"
            path = policy.check(output_root / f"{label}_{project.path.name[7:15]}.pptx", write=True)
            record = {"path": str(logical_path(path)), "sha256": None, "generation": None}
        path = policy.check(Path(record["path"]), write=True)
        if path.parent != policy.check(output_root) or not path.name.endswith("_" + project.path.name[7:15] + ".pptx"):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Output is not owned by this quick edit")
        before = fingerprint(path)
        if before["exists"] and before["sha256"] not in {record["sha256"], source["sha256"]}:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Exported PPTX was edited externally; preserve or import those edits first")
        if "export" not in metadata:
            metadata["export"] = record
            workspaces.save(project, metadata)
        if before["sha256"] != source["sha256"]:
            payload = project.canonical.read_bytes()
            if fingerprint(project.canonical) != source or fingerprint(path) != before:
                raise StudioError(ErrorCode.FILE_CONFLICT, "Working or output deck changed during export")
            atomic_bytes(path, payload)
        if sha256(path) != source["sha256"]:
            raise StudioError(ErrorCode.SOURCE_CONFLICT, "Export copy hash differs from validated canonical")
        finished = {**record, "sha256": source["sha256"], "generation": state["generation"]}
        if metadata["export"] != finished:
            metadata["export"] = finished
            workspaces.save(project, metadata)
        return metadata["export"]
