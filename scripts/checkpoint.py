"""Persist a recoverable repository snapshot only after a reviewed phase gate."""
import argparse
import hashlib
import json
import zipfile
import yaml
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from ir.validation import validate
from state.errors import ErrorCode, StudioError
from state.io import read_json, read_yaml, sha256, write_json, write_yaml


def checkpoint(root: Path, phase: int, report: Path):
    state = read_yaml(root / "implementation/IMPLEMENTATION_STATUS.yaml")
    gate = read_json(report)
    if state["completed_phases"] != list(range(phase)) or state["current_phase"] != phase:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Previous phase gate is incomplete")
    if gate.get("phase") != phase or not gate.get("engineering_review_passed") or not gate.get("acceptance") or not all(item["passed"] is True for item in gate["acceptance"]):
        raise StudioError(ErrorCode.QA_FAILURE, "Phase acceptance or engineering review failed")
    registry = read_yaml(root / "REQUIREMENTS.yaml")
    requirements = registry["phases"][phase]["requirements"]
    if len(gate["acceptance"]) != len(requirements) or {item["requirement"] for item in gate["acceptance"]} != set(requirements):
        raise StudioError(ErrorCode.QA_FAILURE, "Gate does not cover every roadmap obligation")
    totals = {"total": 0, "passing": 0, "failing": 0, "skipped": 0}
    for name in gate["test_reports"]:
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Test report outside repository")
        tree = ElementTree.parse(path)
        suites = [tree.getroot()] if tree.getroot().tag == "testsuite" else list(tree.getroot())
        for suite in suites:
            counts = {key: int(suite.attrib.get(key, 0)) for key in ["tests", "errors", "failures", "skipped"]}
            if not counts["tests"] or counts["errors"] or counts["failures"] or counts["skipped"]:
                raise StudioError(ErrorCode.QA_FAILURE, "Test gate has failures, skips or no cases", report=name)
            totals["total"] = max(totals["total"], counts["tests"])
            totals["passing"] = totals["total"]
    if totals["total"] == 0:
        raise StudioError(ErrorCode.QA_FAILURE, "No executable test evidence")
    if phase >= 5 and not gate.get("benchmark_passed"):
        raise StudioError(ErrorCode.QA_FAILURE, "Quality benchmark evidence required")
    identifier = uuid4().hex
    directory = root / "implementation/CHECKPOINTS"
    directory.mkdir(exist_ok=True)
    target = directory / f"phase_{phase}_{identifier}.zip"
    now = datetime.now(timezone.utc).isoformat()
    state["completed_phases"].append(phase)
    state["phases"][phase] = {"status": "complete", "gate_report": report.relative_to(root).as_posix()}
    state["status"] = "complete" if phase == 11 else "in_progress"
    state["tests"] = {**totals, "last_run": now, "reports": gate["test_reports"]}
    state["current_phase_progress"] = {"completed": ["gate_passed", "checkpoint"], "remaining": []}
    state["last_checkpoint"] = {"type": "repository_snapshot", "id": identifier, "path": target.relative_to(root).as_posix(), "phase": phase}
    validate(root, "implementation_state", state)
    registry["phases"][phase]["status"] = "complete"
    registry["phases"][phase]["test_evidence"] = gate["test_reports"]
    files = []
    for top in root.iterdir():
        if top.name in {"runtime", "projects", "library", ".git", ".pytest_cache", ".venv"}:
            continue
        candidates = top.rglob("*") if top.is_dir() else [top]
        for path in candidates:
            if path.is_file() and "CHECKPOINTS" not in path.parts and "__pycache__" not in path.parts:
                files.append(path)
    package = root / "library/knowledge/packages/consulting_deck_knowledge_v1"
    files.extend(p for p in package.glob("*") if p.is_file())
    payloads = {p.relative_to(root).as_posix(): p.read_bytes() for p in files}
    payloads["implementation/IMPLEMENTATION_STATUS.yaml"] = yaml.safe_dump(state, sort_keys=False).encode("utf-8")
    payloads["REQUIREMENTS.yaml"] = yaml.safe_dump(registry, sort_keys=False, allow_unicode=True).encode("utf-8")
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
        archive.writestr("CHECKPOINT_MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(target) as archive:
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise StudioError(ErrorCode.SOURCE_CONFLICT, "Checkpoint verification failed", member=name)
    record = {"schema_version": "1.0", "phase": phase, "id": identifier, "path": target.relative_to(root).as_posix(), "sha256": sha256(target), "files": len(manifest), "time": now, "corpus": "immutable library retained separately with inventory and ZIP backups"}
    write_json(target.with_suffix(".json"), record)
    write_yaml(root / "REQUIREMENTS.yaml", registry)
    write_yaml(root / "implementation/IMPLEMENTATION_STATUS.yaml", state)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(checkpoint(root, args.phase, root / args.gate), indent=2))
