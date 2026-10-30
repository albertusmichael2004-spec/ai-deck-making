"""Read-only workspace inventory and checkpoint comparison before resuming work."""
import ast
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    inventory = []
    source = {}
    errors = []
    native_root = "\\\\?\\" + str(ROOT) if os.name == "nt" else str(ROOT)
    for directory, _, filenames in os.walk(native_root):
        for filename in filenames:
            path = Path(directory) / filename
            relative = str(path)[len(native_root) + 1:].replace("\\", "/")
            inventory.append({"path": relative, "bytes": path.stat().st_size})
            if relative.split("/")[0] not in {"src", "tests", "scripts", "schemas", "config", "docs"} or "__pycache__" in relative:
                continue
            source[relative] = {"sha256": digest(path)}
            if path.suffix == ".py":
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
                    source[relative]["definitions"] = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                except (SyntaxError, UnicodeError) as exc:
                    errors.append({"path": relative, "error": str(exc)})
    checkpoints = []
    latest = {}
    for sidecar in sorted((ROOT / "implementation/CHECKPOINTS").glob("*.json")):
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        archive = ROOT / metadata["path"]
        valid = digest(archive) == metadata["sha256"]
        checkpoints.append({"phase": metadata["phase"], "sha256_verified": valid, "path": metadata["path"]})
        if metadata["phase"] == 5:
            with zipfile.ZipFile(archive) as bundle:
                latest = {name: hashlib.sha256(bundle.read(name)).hexdigest() for name in bundle.namelist() if name in source}
    changed = [name for name, record in source.items() if name in latest and record["sha256"] != latest[name]]
    added = [name for name in source if name not in latest]
    report = {"time": datetime.now(timezone.utc).isoformat(), "files": len(inventory), "bytes": sum(item["bytes"] for item in inventory), "inventory": sorted(inventory, key=lambda item: item["path"]), "source": source, "syntax_errors": errors, "checkpoints": checkpoints, "changed_since_phase_5": sorted(changed), "added_since_phase_5": sorted(added)}
    destination = ROOT / "implementation/PHASE_REPORTS/resume_audit.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"inventory", "source"}}, indent=2))


if __name__ == "__main__":
    main()
