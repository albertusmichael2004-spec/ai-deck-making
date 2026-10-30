import os
import subprocess
import sys
import shutil
from uuid import uuid4
from pathlib import Path

from state.errors import StudioError, ErrorCode
from state.io import fingerprint, read_json, write_json, sha256, logical_path,copy_file


class NativeRenderer:
    def __init__(self, repository: Path, timeout_seconds: int = None):
        self.repository = repository
        self.timeout_seconds = timeout_seconds

    def worker_timeout(self, slide_count):
        # Keep explicit caller limits; otherwise budget startup plus per-slide COM work.
        return self.timeout_seconds if self.timeout_seconds is not None else min(1800,90+30*slide_count)

    def render(self, source: Path, output: Path, slide_indices=None):
        before = fingerprint(source)
        from presentation.backends.ooxml import OOXMLBackend
        backend = OOXMLBackend(self.repository)
        validation = backend.validate(source)
        if not validation["passed"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Renderer input is structurally invalid", errors=validation["errors"])
        source = backend.policy.check(source)
        count=len(backend.inspect(source)["slides"])
        if slide_indices is not None:
            if not slide_indices or any(type(index)!=int or not 1<=index<=count for index in slide_indices) or len(set(slide_indices))!=len(slide_indices):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Selective render indices must be unique existing slide numbers")
        output = backend.policy.check(output, write=True)
        if output.exists():
            raise StudioError(ErrorCode.FILE_CONFLICT, "Use a fresh render directory")
        # A short immutable render copy avoids native Office path-length limits.
        staging = backend.policy.check(self.repository / "runtime/native_render" / uuid4().hex, write=True)
        staging.mkdir(parents=True)
        render_input = staging / "input.pptx"
        copy_file(source, render_input)
        if sha256(render_input) != before["sha256"]:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Source changed during render materialization")
        worker_output = staging / "slides"
        report = staging / "render_report.json"
        progress = staging / "progress.json"
        timeout = self.worker_timeout(len(slide_indices) if slide_indices is not None else count)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(self.repository / "src"), str(self.repository / "runtime/python_packages")])
        try:
            command=[sys.executable,str(self.repository/"scripts/powerpoint_render_worker.py"),"--source",str(logical_path(render_input)),"--output",str(logical_path(worker_output)),"--report",str(logical_path(report)),"--progress",str(logical_path(progress))]
            if slide_indices is not None:command.extend(["--slides",",".join(map(str,sorted(slide_indices)))])
            result = subprocess.run(command, cwd=self.repository, env=env, capture_output=True, text=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired as exc:
            last=read_json(progress) if progress.is_file() else {"stage":"worker_startup"}
            # subprocess.run has killed/waited for our worker. Recover only its
            # exact immutable, saved, read-only render copy in an isolated helper.
            recovery={"status":"unavailable"}
            try:
                subprocess.run([sys.executable,str(self.repository/'scripts/powerpoint_render_recovery.py'),'--source',str(logical_path(render_input)),'--sha256',before['sha256']],cwd=self.repository,env=env,capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                recovery_path=staging/'recovery.json'
                if recovery_path.is_file():recovery=read_json(recovery_path)
            except (OSError,subprocess.SubprocessError):pass
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Native render worker timed out; canonical was not mutated",timeout_seconds=timeout,progress=last,progress_path=str(logical_path(progress)),recovery=recovery) from exc
        if not report.is_file():
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Native renderer did not return a durable report", returncode=result.returncode)
        artifact = read_json(report)
        if not artifact.get("passed") or result.returncode != 0:
            errors=artifact.get("errors", [])
            action=next((row["recovery_action"] for row in errors if row.get("recovery_action")), "Inspect the native render report and retry preflight.")
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Real slide rendering failed. " + action, errors=errors)
        if fingerprint(source) != before:
            raise StudioError(ErrorCode.FILE_CONFLICT, "Renderer source changed while it was rendering")
        from PIL import Image
        output.mkdir(parents=True)
        for slide in artifact["slides"]:
            image = Path(slide["render"])
            with Image.open(image) as canvas:
                canvas.verify()
            if image.stat().st_size == 0:
                raise StudioError(ErrorCode.QA_FAILURE, "Renderer produced an empty slide")
            target = output / image.name
            shutil.copy2(image, target)
            slide["render"] = str(logical_path(target))
        artifact["input_sha256"] = before["sha256"]
        write_json(output / "render_report.json", artifact)
        return artifact
