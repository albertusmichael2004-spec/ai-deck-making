"""Start the installed Codex TUI in one selected presentation project."""
import os
import shutil
import subprocess
from pathlib import Path

from state.errors import ErrorCode, StudioError
from state.intake import ProjectIntake
from state.io import logical_path, native_path
from state.workspace import CONTEXT_MARKER, now
from state.paths import others_output_path


def resolve_codex():
    selected = shutil.which("codex")
    if selected:
        return Path(selected)
    # Desktop installs expose a versioned binary to the app, not always to PATH.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        versions = list((Path(local) / "OpenAI/Codex/bin").glob("*/codex.exe"))
        if versions:
            return max(versions, key=lambda path: path.stat().st_mtime_ns)
    raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Codex CLI was not found; install it or open this launcher from the Codex app terminal")


def command(root, project, executable, resume=False, prompt=None):
    result = [str(executable), "--no-daemon", "-s", "workspace-write", "-a", "on-request", "-C", str(logical_path(project.path))]
    for setting in ['tui.notifications=["approval-requested","agent-turn-complete"]', 'tui.notification_condition="always"', 'tui.notification_method="bel"']:
        result.extend(["-c", setting])
    # Source code remains read-only; durable shared indexes and native workers
    # need their existing writable areas outside the selected project directory.
    for folder in [root / "runtime", root / "library"]:
        result.extend(["--add-dir", str(folder)])
    if project.path.is_relative_to(native_path(root / "runtime/others")):
        result.extend(["--add-dir", str(logical_path(others_output_path(root)))])
    if resume:
        result.extend(["resume", "--last"])
    agents = project.path / "AGENTS.md"
    if agents.exists() and not agents.read_text(encoding="utf-8").startswith(CONTEXT_MARKER):
        context = "Project ini memakai AI Presentation Studio. Baca state/operator_context.md dan state/workspace.json sebelum mengerjakan permintaan pengguna. Pertahankan instruksi AGENTS.md yang sudah ada."
        prompt = context + ("\n\n" + prompt if prompt else "")
    if prompt:
        if os.name == "nt" and executable.suffix.lower() in {".cmd", ".bat"}:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Use a Codex executable for a startup prompt, or enter the prompt inside Codex after choosing Others")
        result.append(prompt)
    return result


def launch(workspaces, project, resume=False, runner=None, prompt=None):
    if any(not row["verified"] for row in ProjectIntake(workspaces, project).files()):
        raise StudioError(ErrorCode.SOURCE_CONFLICT, "A registered input is missing or changed; original lineage must be restored before prompting")
    executable = resolve_codex()
    workspaces.write_context(project)
    with project._lock():
        value = workspaces.metadata(project)
        value["last_chat_started_at"] = now()
        workspaces.save(project, value)
    env = dict(os.environ)
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = os.pathsep.join([str(workspaces.root / "src"), str(workspaces.root / "runtime/python_packages"), env.get("PYTHONPATH", "")])
    completed = (runner or subprocess.run)(command(workspaces.root, project, executable, resume, prompt), cwd=logical_path(project.path), env=env)
    with project._lock():
        value = workspaces.metadata(project)
        value["last_chat_exit_code"] = completed.returncode
        workspaces.save(project, value)
    from state.outputs import export_others
    export_others(workspaces.root, project.path.name)
    return completed.returncode
