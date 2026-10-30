"""Explicit file-picker imports preserve originals, versioned copies and provenance."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from security.files import FileRegistry
from security.paths import PathPolicy
from state.errors import ErrorCode, StudioError
from state.io import logical_path, native_path, read_yaml, sha256
from state.workspace import now


def selected_files(source, owner):
    original = Path(source).expanduser().absolute()
    if original.is_symlink() or original.is_junction():
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Select an original file/folder, not a link")
    source = native_path(original)
    if source.is_file():
        return source, [(source, Path(source.name))]
    if not source.is_dir():
        raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR, "Selected input does not exist")
    if owner.is_relative_to(source):
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Cannot import a folder containing the destination project")
    if source.is_relative_to(owner / "input") or source.is_relative_to(owner / "references"):
        raise StudioError(ErrorCode.FILE_CONFLICT, "This folder is already managed input; use the project inventory instead of recursively importing it")
    result = []
    pending = [source]
    while pending:
        folder = pending.pop()
        for entry in sorted(os.scandir(folder), key=lambda e: e.name):
            metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or getattr(metadata, "st_reparse_tag", 0) in {0xA0000003, 0xA000000C}:
                raise StudioError(ErrorCode.SECURITY_BLOCK, "Folder imports cannot follow links or junctions")
            if entry.is_dir(follow_symlinks=False):
                pending.append(native_path(Path(entry.path)))
            else:
                path = native_path(Path(entry.path))
                result.append((path, Path(source.name) / path.relative_to(source)))
    if not result:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Selected folder has no files")
    return source, sorted(result, key=lambda row: row[1].as_posix())



def prepare_imports(repository, owner, destination_root, sources, role):
    selections = [selected_files(source, owner) for source in sources]
    if any(source.is_dir() and source.is_relative_to(native_path(destination_root)) for source, _ in selections):
        raise StudioError(ErrorCode.FILE_CONFLICT, "Use the inventory instead of recursively importing managed originals")
    if not selections:
        return [], None, None
    if len(selections) == 1:
        files = selections[0][1]
    else:
        try:
            common = Path(os.path.commonpath([str(path.parent) for path, _files in selections]))
        except ValueError as exc:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Choose files from one drive per import") from exc
        files = [(path, path.relative_to(common)) for _selected, entries in selections for path, _relative in entries]
    unique = {}
    for path, relative in files:
        key = relative.as_posix().casefold()
        if key in unique and unique[key][0] != path:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Selected inputs have conflicting relative paths")
        unique[key] = (path, relative)
    files = sorted(unique.values(), key=lambda row: row[1].as_posix())
    if role == "target" and (len(files) != 1 or files[0][0].suffix.lower() != ".pptx"):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "The working target must be one PPTX")
    registry_role = "reference" if role == "reference" else ROLES[role][1]
    # Read access is limited to the explicitly chosen files, not their parent folders.
    registry = FileRegistry(PathPolicy([path for path, _ in files], [destination_root]), read_yaml(repository / "config/security/files.yaml"))
    prepared = [(path, relative, registry.inspect(path, registry_role)) for path, relative in files]
    names = {str(relative).casefold() for _, relative in files}
    if any(str(relative.with_name(relative.name + ".source.json")).casefold() in names for _, relative in files):
        raise StudioError(ErrorCode.FILE_CONFLICT, "Folder filenames collide with provenance sidecars; import the folder as a ZIP to preserve its internal paths")
    batch = hashlib.sha256(json.dumps([(relative.as_posix(), record["sha256"]) for _, relative, record in prepared], ensure_ascii=False).encode()).hexdigest()[:32]
    return prepared, registry, batch


ROLES = {"source": ("sources", "supporting_source"), "asset": ("assets", "approved_asset"), "target": ("target", "canonical_target"), "reference": ("references", "reference")}


class ProjectIntake:
    def __init__(self, workspaces, project):
        self.workspaces, self.project = workspaces, project

    def _files(self, source):
        return selected_files(source, self.project.path)

    def destination(self, role):
        if role == "reference":
            from references.store import ReferenceStore
            store = ReferenceStore(self.workspaces.root, project_id=self.project.path.name)
            destination = store.policy.check(store.base / "originals", write=True)
            if logical_path(destination) != logical_path(store.base / "originals"):
                raise StudioError(ErrorCode.SECURITY_BLOCK, "Project reference originals cannot be redirected")
            return destination
        return self.project.path / "input" / ROLES[role][0]

    def import_path(self, source, role="source"):
        return self.import_paths([source], role)

    def import_paths(self, sources, role="source"):
        if role not in ROLES:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unknown import role")
        prepared, registry, batch = prepare_imports(self.workspaces.root, self.project.path, self.destination(role), sources, role)
        destination_root = self.destination(role)
        registry_role = ROLES[role][1]
        result = []
        with self.project._lock():
            metadata = self.workspaces.metadata(self.project)
            known = {(item["path"], item["original_path"]) for item in metadata["imports"]}
            for path, relative, expected in prepared:
                destination = destination_root / "uploads" / batch / relative
                if destination.exists():
                    if sha256(destination) != expected["sha256"]:
                        raise StudioError(ErrorCode.SOURCE_CONFLICT, "An immutable imported copy has changed")
                else:
                    copied = registry.materialize(path, destination, registry_role)
                    if copied["sha256"] != expected["sha256"]:
                        raise StudioError(ErrorCode.SOURCE_CONFLICT, "Selected input changed during import")
                item = {"role": role, "original_path": str(logical_path(path)), "path": str(logical_path(destination)), "relative_path": destination.relative_to(self.project.path).as_posix(), "sha256": expected["sha256"], "bytes": expected["bytes"], "imported_at": now()}
                if (item["path"], item["original_path"]) not in known:
                    metadata["imports"].append(item)
                    known.add((item["path"], item["original_path"]))
                result.append(item)
            self.workspaces.save(self.project, metadata)
        self.workspaces.write_context(self.project)
        return result

    def files(self):
        rows = self.workspaces.metadata(self.project)["imports"]
        result = []
        for row in rows:
            path = self.project.policy.check(Path(row["path"]))
            expected_root = self.destination(row["role"]) / "uploads"
            if not path.is_relative_to(expected_root) or path.relative_to(self.project.path).as_posix() != row["relative_path"]:
                raise StudioError(ErrorCode.SECURITY_BLOCK, "Import inventory points outside its managed input location")
            result.append({**row, "verified": path.is_file() and sha256(path) == row["sha256"]})
        return result

    def initialize_target(self, item, validator=None):
        if not any(row["role"] == "target" and row["verified"] and row["path"] == item["path"] and row["sha256"] == item["sha256"] for row in self.files()):
            raise StudioError(ErrorCode.SOURCE_CONFLICT, "Working target is not a verified registered input")
        source = self.project.policy.check(Path(item["path"]))
        if item["role"] != "target" or sha256(source) != item["sha256"]:
            raise StudioError(ErrorCode.SOURCE_CONFLICT, "Registered target differs from the imported original")
        if self.project.canonical.exists():
            if sha256(self.project.canonical) == item["sha256"]:
                return self.project.state()
            raise StudioError(ErrorCode.FILE_CONFLICT, "A working PPTX already exists; revise it with explicit scope")
        identifier = self.project.begin()
        try:
            from state.io import read_json
            journal = read_json(self.project.candidate(identifier).with_name("transaction.json"))
            if journal["base"]["fingerprint"]["sha256"] is not None:
                raise StudioError(ErrorCode.FILE_CONFLICT, "A working deck appeared during import; use scoped revision")
            candidate = self.project.candidate(identifier)
            shutil.copy2(source, candidate)
            if sha256(candidate) != item["sha256"]:
                raise StudioError(ErrorCode.SOURCE_CONFLICT, "Imported target changed during preparation")
            if validator is None:
                from presentation.backends.ooxml import OOXMLBackend
                from presentation.rendering.native import NativeRenderer
                from qa.transaction import PresentationValidator
                validator = PresentationValidator(self.workspaces.root, OOXMLBackend(self.workspaces.root), NativeRenderer(self.workspaces.root), candidate.parent / "target_import_qa")
            return self.project.commit(identifier, validator)
        except Exception:
            from state.io import read_json
            if read_json(self.project.candidate(identifier).with_name("transaction.json"))["status"] == "planned":
                self.project.abort(identifier)
            raise
