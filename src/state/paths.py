from pathlib import Path
import re

from state.errors import ErrorCode, StudioError
from state.io import logical_path, native_path, read_yaml

FIXTURE_ID = re.compile(r"(?:bench|chart-boundaries|consulting-e2e|critic-native|critic-smoke|exhibits|incremental-native|live-comments|live-native|live-probe|live-table|qa-smoke|reason-smoke|research-design|release-manufacturing|release-retail|release-financial_services)-[0-9a-f]{8,12}")

def repository_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for path in [start, *start.parents]:
        if (path / ".studio-root").is_file():
            return path
    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Workspace bootstrap marker missing")


def contracts(root: Path) -> dict:
    return read_yaml(root / "config/defaults/paths.yaml")


def initialize_folders(root: Path):
    for name in contracts(root)["repository_directories"] + contracts(root)["library_directories"]:
        native_path(root / name).mkdir(parents=True, exist_ok=True)


def others_output_path(root: Path) -> Path:
    expected = root.resolve() / "output/Others"
    resolved = native_path(expected)
    if logical_path(resolved) != expected:
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Others output folder cannot be redirected through a link or junction")
    return resolved


def project_path(root: Path, project_id: str, *, others=False) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", project_id) or project_id.lower() in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(?:com|lpt)[1-9]", project_id):
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Invalid project identifier")
    normal = root / "projects" / project_id
    quick = root / "runtime/others" / project_id
    quick_id = bool(re.fullmatch(r"others-[a-f0-9]{32}", project_id))
    if others:
        if not quick_id or normal.exists():
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Invalid or conflicting Others workspace identity")
        return quick
    if quick_id and not normal.exists() and quick.exists():
        return quick
    if FIXTURE_ID.fullmatch(project_id) and not normal.exists():
        return root / "runtime/test_projects" / project_id
    return normal
