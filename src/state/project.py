import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from ir.validation import validate
from state.errors import ErrorCode, StudioError
from state.io import fingerprint, native_path, read_json, read_yaml, sha256, write_json, write_yaml,copy_file
from state.locking import FileLock
from state.paths import contracts, project_path
from state.telemetry import Telemetry
from security.paths import PathPolicy


def artifact_id(value: str):
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Invalid internal artifact identifier")
    return value


class Project:
    def __init__(self, root: Path, project_id: str, *, others=False):
        self.repository = root.resolve()
        self.path = native_path(project_path(root, project_id, others=others))
        if not self.path.is_relative_to(native_path(self.repository)):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Project path resolves outside the workspace")
        self.policy = PathPolicy([self.path], [self.path], [self.path / "input", self.path / "references/originals"])
        self.canonical = self.path / "presentation/canonical.pptx"
        self.state_path = self.path / "project.yaml"
        self.lock_path = self.path / "work/project.lock"
        self.telemetry = Telemetry(self.path / "logs/events.jsonl")

    @classmethod
    def create(cls, root: Path, project_id: str, *, validation_policy="presentation", others=False):
        if validation_policy == "kernel" and (root / ".studio-root").read_text(encoding="utf-8").strip() != "test":
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Kernel-only validation is reserved for isolated primitive test fixtures")
        project = cls(root, project_id, others=others)
        try:
            project.path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Project already exists") from exc
        for directory in contracts(root)["project_directories"]:
            (project.path / directory).mkdir(parents=True, exist_ok=True)
        state = {"schema_version": "1.1", "project_id": project_id, "generation": 0, "canonical": "presentation/canonical.pptx", "canonical_fingerprint": fingerprint(project.canonical), "authority": "file", "validation_policy": validation_policy}
        validate(root, "project_state", state)
        write_yaml(project.state_path, state)
        project.telemetry.record("project_created", project_id=project_id)
        return project

    @classmethod
    def open(cls, root: Path, project_id: str):
        project = cls(root, project_id)
        if not project.state_path.is_file():
            raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR, "Project state missing")
        project.state()
        return project

    def state(self):
        state = read_yaml(self.policy.check(self.state_path))
        validate(self.repository, "project_state", state)
        if state["schema_version"] == "1.0":
            # Explicit additive migration. Existing production projects acquire the stronger gate.
            state = {**state, "schema_version": "1.1", "validation_policy": "presentation"}
            validate(self.repository, "project_state", state)
        if state["project_id"] != self.path.name:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Project identity mismatch")
        return state

    def token(self):
        return {"generation": self.state()["generation"], "fingerprint": fingerprint(self.policy.check(self.canonical))}

    def _lock(self):
        return FileLock(self.policy.check(self.lock_path, write=True))

    def detect_conflict(self, expected: dict):
        return self.token() != expected

    def _file_authority(self):
        state = self.state()
        if state["authority"] != "file":
            raise StudioError(ErrorCode.FILE_CONFLICT, "A live session owns this project")
        return state

    def _snapshot(self):
        self.policy.check(self.canonical)
        if not self.canonical.exists():
            return None
        identifier = uuid4().hex
        before = fingerprint(self.canonical)
        destination = self.policy.check(self.path / "history/snapshots" / (identifier + ".pptx"), write=True)
        copy_file(self.canonical, destination)
        if fingerprint(self.canonical) != before or sha256(destination) != before["sha256"]:
            destination.unlink(missing_ok=True)
            raise StudioError(ErrorCode.FILE_CONFLICT, "Deck changed during snapshot")
        write_json(destination.with_suffix(".json"), {"id": identifier, "sha256": before["sha256"], "generation": self.state()["generation"]})
        return identifier

    def snapshot(self):
        with self._lock():
            self._file_authority()
            return self._snapshot()

    def _transaction_path(self, identifier):
        path = native_path(self.path / "work/transactions" / artifact_id(identifier))
        if not path.is_relative_to(self.path):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Transaction path resolves outside the project")
        return path

    def candidate(self, identifier):
        return self._transaction_path(identifier) / "candidate.pptx"

    def begin(self):
        self._file_authority()
        from presentation.live.target_update import TargetUpdate
        binding=TargetUpdate.discover(self)
        try:
            binding.prepare_source()
            with self._lock():
                identifier=self._prepare_transaction()
            if not hasattr(self,"_target_updates"):self._target_updates={}
            self._target_updates[identifier]=binding
            binding._record("ready",transaction_id=identifier)
            return identifier
        except Exception:
            binding.finish()
            raise

    def _prepare_transaction(self, expected=None):
        state = self._file_authority()
        before = self.token()
        if expected is not None and before != expected:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Canonical changed before rollback preparation")
        if expected is None and before["fingerprint"] != state["canonical_fingerprint"]:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Canonical file changed outside the project")
        snapshot = self._snapshot()
        identifier = uuid4().hex
        transaction = self._transaction_path(identifier)
        transaction.mkdir()
        if self.canonical.exists():
            copy_file(self.canonical, self.candidate(identifier))
        if self.detect_conflict(before):
            raise StudioError(ErrorCode.FILE_CONFLICT, "Canonical file changed during transaction preparation")
        journal = {"schema_version": "1.0", "id": identifier, "status": "planned", "base": before, "snapshot_id": snapshot, "candidate_hash": None}
        self._write_journal(journal)
        self.telemetry.record("transaction_started", transaction_id=identifier, base_generation=before["generation"])
        return identifier
    def _write_journal(self, journal):
        validate(self.repository, "transaction", journal)
        write_json(self._transaction_path(journal["id"]) / "transaction.json", journal)

    def commit(self, transaction_id: str, validator):
        from presentation.live.target_update import TargetUpdate
        bindings=getattr(self,"_target_updates",{})
        binding=bindings.pop(transaction_id,None) or TargetUpdate.discover(self)
        try:return self._commit(transaction_id,validator,binding)
        finally:
            binding.finish()

    def _commit(self, transaction_id: str, validator, binding):
        """Only a validated, unchanged working copy can replace the canonical deck."""
        with self._lock():
            self._file_authority()
            journal = read_json(self._transaction_path(transaction_id) / "transaction.json")
            validate(self.repository, "transaction", journal)
            if journal["status"] != "planned":
                raise StudioError(ErrorCode.FILE_CONFLICT, "Transaction is no longer pending")
            candidate = self.candidate(transaction_id)
            if not candidate.is_file():
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Candidate is missing")
            before = fingerprint(candidate)
            try:
                result = validator(candidate)
                if not isinstance(result, dict) or result.get("passed") is not True or result.get("errors"):
                    raise StudioError(ErrorCode.QA_FAILURE, "Candidate validation failed")
                if self.state()["validation_policy"] == "presentation":
                    if result.get("rendered") is not True or result.get("structural_passed") is not True or not result.get("render_report"):
                        raise StudioError(ErrorCode.QA_FAILURE, "Production commit requires real rendering and deterministic QA")
                    render_report = read_json(self.policy.check(Path(result["render_report"])))
                    if render_report.get("passed") is not True or render_report.get("input_sha256") != before["sha256"]:
                        raise StudioError(ErrorCode.QA_FAILURE, "Render proof does not match the candidate")
                if fingerprint(candidate) != before:
                    raise StudioError(ErrorCode.FILE_CONFLICT, "Candidate changed during validation")
            except Exception:
                journal["status"] = "aborted"
                self._write_journal(journal)
                raise
            if self.detect_conflict(journal["base"]):
                journal["status"] = "conflict"
                self._write_journal(journal)
                raise StudioError(ErrorCode.FILE_CONFLICT, "User edits detected before commit")
            journal["status"], journal["candidate_hash"] = "validated", before["sha256"]
            self._write_journal(journal)
            with candidate.open("r+b") as stream:
                os.fsync(stream.fileno())
            journal["status"] = "committing"
            self._write_journal(journal)
            # Recheck after the durable intent write and immediately before replacement.
            if self.detect_conflict(journal["base"]):
                journal["status"] = "conflict"
                self._write_journal(journal)
                raise StudioError(ErrorCode.FILE_CONFLICT, "Canonical changed before replacement")
            binding.before_replace()
            if self.detect_conflict(journal["base"]):
                journal["status"]="conflict";self._write_journal(journal)
                raise StudioError(ErrorCode.FILE_CONFLICT,"Working target changed while PowerPoint released its file handle")
            from state.io import replace_file
            replace_file(candidate, self.policy.check(self.canonical, write=True))
            state = self.state()
            state["generation"] = journal["base"]["generation"] + 1
            state["canonical_fingerprint"] = fingerprint(self.canonical)
            write_yaml(self.policy.check(self.state_path, write=True), state)
            journal["status"] = "committed"
            self._write_journal(journal)
            self.telemetry.record("transaction_committed", transaction_id=transaction_id, generation=state["generation"])
            return state

    def abort(self, transaction_id):
        with self._lock():
            journal = read_json(self._transaction_path(transaction_id) / "transaction.json")
            if journal["status"] != "planned":
                raise StudioError(ErrorCode.FILE_CONFLICT, "Only pending transactions can be aborted")
            journal["status"] = "aborted"
            self._write_journal(journal)
        binding=getattr(self,"_target_updates",{}).pop(transaction_id,None)
        if binding is not None:binding.finish()

    def rollback(self, snapshot_id: str, expected: dict, validator=None):
        if self.state()["validation_policy"] == "presentation" and validator is None:
            raise StudioError(ErrorCode.QA_FAILURE, "Production rollback requires an injected presentation validator")
        snapshot_id = artifact_id(snapshot_id)
        source = self.policy.check(self.path / "history/snapshots" / (snapshot_id + ".pptx"))
        manifest = read_json(source.with_suffix(".json"))
        if sha256(source) != manifest["sha256"]:
            raise StudioError(ErrorCode.SOURCE_CONFLICT, "Snapshot hash mismatch")
        with self._lock():
            self._file_authority()
            identifier = self._prepare_transaction(expected)
        shutil.copy2(source, self.candidate(identifier))
        def integrity(candidate):
            if sha256(candidate) != manifest["sha256"]:
                raise StudioError(ErrorCode.SOURCE_CONFLICT, "Rollback candidate differs from snapshot")
            if validator is not None:
                return validator(candidate)
            return {"passed": sha256(candidate) == manifest["sha256"], "errors": []}
        state = self.commit(identifier, integrity)
        self.telemetry.record("rollback", snapshot_id=snapshot_id, generation=state["generation"])
        return state

    def recover(self):
        """Resolve a durable commit intent without overwriting an external edit."""
        recovered = []
        with self._lock():
            self._file_authority()
            for path in sorted((self.path / "work/transactions").glob("*/transaction.json")):
                journal = read_json(path)
                validate(self.repository, "transaction", journal)
                if journal["status"] != "committing":
                    continue
                actual = fingerprint(self.canonical)
                if actual["sha256"] == journal["candidate_hash"]:
                    state = self.state()
                    if state["generation"] not in {journal["base"]["generation"], journal["base"]["generation"] + 1}:
                        raise StudioError(ErrorCode.FILE_CONFLICT, "Recovery generation conflict")
                    state["generation"] = journal["base"]["generation"] + 1
                    state["canonical_fingerprint"] = actual
                    write_yaml(self.policy.check(self.state_path, write=True), state)
                    journal["status"] = "committed"
                elif self.token() == journal["base"]:
                    journal["status"] = "aborted"
                else:
                    journal["status"] = "conflict"
                self._write_journal(journal)
                recovered.append({"id": journal["id"], "status": journal["status"]})
        from presentation.live.target_update import TargetUpdate
        return recovered+TargetUpdate.recover(self)
