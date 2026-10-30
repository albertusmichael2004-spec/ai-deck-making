"""Read-only cleanup planner; PowerShell performs the checked removals."""
import argparse
import ctypes
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = re.compile(r"(?:bench|chart-boundaries|consulting-e2e|critic-native|critic-smoke|exhibits|incremental-native|live-comments|live-native|live-probe|live-table|qa-smoke|reason-smoke|research-design)-[0-9a-f]{8,12}")
DISPOSABLE = {"cli_tests", "installation_smoke", "live_commands", "live_snapshots", "native_render", "native_tests", "phase_2_golden_candidate", "preference_benchmark", "provider_probe", "pytest", "reference_ingestion", "render_metrics_probe", "render_metrics_probe_classic", "render_metrics_probe_fixed", "render_probe_elevated", "research_provider"}


def locked(path):
    if not path.exists():
        return False
    if os.name != "nt":
        return True
    # Existing lock files persist after unlock. Probe sharing without writing.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        return True
    kernel.CloseHandle(handle)
    return False


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def inventory(path):
    counts = {"files": 0, "folders": 0, "bytes": 0}
    native = Path("\\\\?\\" + str(path)) if os.name == "nt" else path
    if native.is_symlink() or native.is_junction():
        raise ValueError(f"Linked cleanup target: {path}")
    if not native.is_dir():
        return {"files": 1, "folders": 0, "bytes": native.stat().st_size}
    pending = [native]
    while pending:
        directory = pending.pop()
        counts["folders"] += 1
        for entry in os.scandir(directory):
            metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or getattr(metadata, "st_reparse_tag", 0) in {0xA0000003, 0xA000000C}:
                raise ValueError(f"Linked child: {entry.path}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(entry.path)
            else:
                counts["files"] += 1
                counts["bytes"] += metadata.st_size
    return counts


def plan(test_run=None):
    protected = defaultdict(set)
    projects = [p for p in (ROOT / "projects").iterdir() if p.is_dir()]
    names = {p.name for p in projects}
    root_text = str(ROOT).lower() + "\\"

    def observe(value, source):
        for text in strings(value):
            if text in names:
                protected[f"projects/{text}"].add(source)
            normalized = text.replace("/", "\\").removeprefix("\\\\?\\")
            if normalized.lower().startswith(root_text):
                parts = normalized[len(root_text):].split("\\")
            elif normalized.startswith(("projects\\", "runtime\\")):
                parts = normalized.split("\\")
            else:
                continue
            if len(parts) >= 2 and parts[0] == "projects":
                protected["/".join(parts[:2])].add(source)
            elif len(parts) >= 3 and parts[0] == "runtime":
                depth = 4 if parts[1] == "pytest" and len(parts) >= 4 else 3
                protected["/".join(parts[:depth])].add(source)

    # Current proofs and provenance, not historical inventory/benchmark listings.
    for file in (ROOT / "implementation/PHASE_REPORTS").glob("*.json"):
        if "audit" in file.name or "benchmark" in file.name or "probe" in file.name:
            continue
        observe(json.loads(file.read_text(encoding="utf-8")), file.name)
    for folder in [ROOT / "library/references/manifests", ROOT / "library/references/index"]:
        for file in folder.glob("*.json"):
            observe(json.loads(file.read_text(encoding="utf-8")), "library provenance")

    def latest(prefix, predicate):
        matches = [p for p in projects if p.name.startswith(prefix) and predicate(p)]
        if not matches:
            raise ValueError(f"Required benchmark fixture missing: {prefix}")
        path = max(matches, key=lambda p: p.stat().st_mtime_ns)
        protected[f"projects/{path.name}"].add("current consulting benchmark")

    for template in [False, True]:
        latest("consulting-e2e-", lambda p: (p / "presentation/canonical.pptx").is_file() and (p / "work/company_template.pptx").is_file() == template)
    latest("research-design-", lambda p: (p / "output/qa/research_design/qa_report.json").is_file())
    latest("chart-boundaries-", lambda p: (p / "output/qa/native_boundary/qa_report.json").is_file())
    for path in projects:
        state = yaml.safe_load((path / "project.yaml").read_text(encoding="utf-8")) if (path / "project.yaml").exists() else {}
        if (path / "state/workspace.json").exists() or state.get("authority") == "live" or locked(path / "work/project.lock") or not FIXTURE.fullmatch(path.name) or state.get("project_id") != path.name:
            protected[f"projects/{path.name}"].add("live, locked, user, or unclassified project")
    # Preserve runtime snapshots/inference artifacts referenced by retained projects.
    for path in projects:
        if f"projects/{path.name}" not in protected:
            continue
        for folder in [path / "state", path / "work", path / "history", path / "logs", path / "output/qa"]:
            if os.name == "nt":
                folder = Path("\\\\?\\" + str(folder))
            for file in folder.rglob("*"):
                if file.suffix in {".json", ".jsonl", ".yaml"} and file.is_file():
                    text = file.read_text(encoding="utf-8")
                    if "runtime" not in text:
                        continue
                    if file.suffix == ".json":
                        observe(json.loads(text), f"retained project {path.name}")
                    elif file.suffix == ".yaml":
                        observe(yaml.safe_load(text), f"retained project {path.name}")
                    else:
                        for line in text.splitlines():
                            if line.strip():
                                observe(json.loads(line), f"retained project {path.name}")

    candidates = []
    if test_run:
        if not re.fullmatch(r"[0-9a-f]{32}", test_run):
            raise ValueError("Invalid test run ID")
        candidates = [(ROOT / "runtime/pytest" / test_run, "successful test temporary directory")]
    else:
        for bucket in sorted(DISPOSABLE):
            folder = ROOT / "runtime" / bucket
            if folder.exists():
                children = list(folder.iterdir())
                candidates.extend((p, "unreferenced runtime artifact") for p in children)
                if not children:
                    candidates.append((folder, "empty disposable runtime directory"))
        candidates.extend((p, "obsolete synthetic test project") for p in projects if FIXTURE.fullmatch(p.name))
        for bucket in ["knowledge_staging", "knowledge_views"]:
            folder = ROOT / "runtime/cache" / bucket
            if folder.exists():
                candidates.extend((p, "rebuildable knowledge staging") for p in folder.iterdir())
        state = yaml.safe_load((ROOT / "implementation/IMPLEMENTATION_STATUS.yaml").read_text(encoding="utf-8"))
        latest_checkpoint = ROOT / state["last_checkpoint"]["path"]
        retained_checkpoints = {latest_checkpoint, latest_checkpoint.with_suffix(".json")}
        for item in state.get("maintenance", {}).values():
            checkpoint_path = item.get("last_checkpoint", {}).get("path")
            if checkpoint_path:
                checkpoint = (ROOT / checkpoint_path).resolve()
                if not checkpoint.is_relative_to(ROOT / "implementation/CHECKPOINTS"):
                    raise ValueError("Maintenance checkpoint outside checkpoint folder")
                retained_checkpoints.update({checkpoint, checkpoint.with_suffix(".json")})
        candidates.extend((p, "superseded checkpoint; current release and maintenance checkpoints retained") for p in (ROOT / "implementation/CHECKPOINTS").iterdir() if p not in retained_checkpoints)
        if (ROOT / ".pytest_cache").exists():
            candidates.append((ROOT / ".pytest_cache", "pytest cache"))
        for folder in ["src", "scripts", "tests", "runtime/python_packages"]:
            candidates.extend((p, "rebuildable Python bytecode") for p in (ROOT / folder).rglob("__pycache__"))

    def disposable_parts(path, reason):
        relative = path.relative_to(ROOT).as_posix()
        if not path.exists() or any(relative == key or relative.startswith(key + "/") for key in protected):
            return
        if any(key.startswith(relative + "/") for key in protected):
            for child in path.iterdir():
                yield from disposable_parts(child, reason)
        else:
            yield path, reason

    removals = []
    for path, reason in (item for candidate, why in candidates for item in disposable_parts(candidate, why)):
        relative = path.relative_to(ROOT).as_posix()
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT) or resolved == ROOT:
            raise ValueError(f"Cleanup outside workspace: {path}")
        removals.append({"path": relative, "absolute_path": str(resolved), "reason": reason, **inventory(path)})
    return {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(), "root": str(ROOT), "removals": removals, "protected": {key: sorted(value) for key, value in sorted(protected.items())}, "totals": {key: sum(row[key] for row in removals) for key in ["files", "folders", "bytes"]}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = plan(args.test_run)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"targets": len(result["removals"]), **result["totals"], "protected": len(result["protected"])}))
