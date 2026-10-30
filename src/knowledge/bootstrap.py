import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from state.io import native_path, read_json, read_yaml, sha256


PACKAGE_ID = "consulting_deck_knowledge_v1"


def verify_bootstrap(root: Path) -> dict:
    """Read-only rerun: never reclassify application code or mutate the package."""
    root = native_path(root)
    package = root / "library/knowledge/packages" / PACKAGE_ID
    inventory = read_json(package / "bootstrap_inventory.json")
    status = read_json(package / "bootstrap_verification.json")
    original = package / "original_package"
    issues, expected_paths = [], set()
    for record in inventory["files"]:
        parts = Path(record["path"]).parts
        destination = root / status["path_mapping"][parts[0]] / Path(*parts[1:])
        expected_paths.add(destination)
        if not destination.is_file():
            issues.append({"kind": "missing", "path": record["path"]})
        elif sha256(destination) != record["sha256"]:
            issues.append({"kind": "changed", "path": record["path"]})
    for record in status["recovered_files"]:
        path = original / record["path"]
        expected_paths.add(path)
        if not path.is_file() or sha256(path) != record["sha256"]:
            issues.append({"kind": "changed_recovered", "path": record["path"]})
    for record in status["archive_aliases"]:
        alias, archive = root / record["alias"], root / record["archive"]
        expected_paths.add(alias)
        if not alias.is_file() or not archive.is_file() or sha256(alias) != sha256(archive):
            issues.append({"kind": "changed_alias", "path": record["alias"]})
    for path in original.rglob("*"):
        if path.is_file() and path not in expected_paths:
            issues.append({"kind": "new_package_item", "path": path.relative_to(original).as_posix()})
    links = 0
    for path in original.rglob("*.md"):
        for raw in re.findall(r"\]\(([^\n]+?)\)", path.read_text(encoding="utf-8-sig")):
            parsed = urlsplit(raw.strip().strip("<>").split(' "')[0])
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            links += 1
            if not (path.parent / unquote(parsed.path)).resolve().exists():
                issues.append({"kind": "broken_link", "source": str(path.relative_to(original)), "target": raw})
    known_repository = set(read_yaml(root / "config/defaults/paths.yaml")["repository_directories"]) | {".studio-root", ".gitignore", ".git", ".pytest_cache", ".venv", "README.md", "REQUIREMENTS.yaml", "pyproject.toml", "requirements-lock.txt"}
    original_names = {entry["name"] for entry in inventory["top_level"]}
    new_material, ambiguous, duplicates = [], [], []
    source_hashes = {entry["sha256"] for entry in inventory["files"]}
    for path in root.iterdir():
        if path.name in known_repository:
            continue
        if path.name in original_names:
            new_material.append(path.name)
            if path.is_file() and sha256(path) in source_hashes:
                duplicates.append(path.name)
        else:
            ambiguous.append(path.name)
    return {"passed": not issues, "errors": issues, "original_files": len(inventory["files"]), "local_links": links, "status": "already_migrated" if not issues else "changed_or_missing", "archive_ingestion": False, "new_root_material": sorted(new_material), "ambiguous_keep_in_place": sorted(ambiguous), "duplicates": sorted(duplicates)}
