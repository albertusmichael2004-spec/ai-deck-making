"""Start the installed Codex (or Claude Code) TUI in one selected presentation project."""
import os
import shutil
import subprocess
from pathlib import Path

from cli.agent_permissions import agent_environment, program_folders, write_codex_hooks
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
    # The whole Studio program folder is writable; other projects are not, and
    # the sandbox keeps .codex/.git read-only. Escalations go to the approval hook.
    for folder in program_folders(root):
        result.extend(["--add-dir", str(folder)])
    if project.path.is_relative_to(native_path(root / "runtime/others")):
        result.extend(["--add-dir", str(logical_path(others_output_path(root)))])
    if resume:
        result.extend(["resume", "--last"])
    prompt = startup_prompt(project, prompt)
    if prompt:
        if os.name == "nt" and executable.suffix.lower() in {".cmd", ".bat"}:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Use a Codex executable for a startup prompt, or enter the prompt inside Codex after choosing Others")
        result.append(prompt)
    return result


def startup_prompt(project, prompt):
    """Point a user-owned AGENTS.md project at the generated Studio context."""
    agents = project.path / "AGENTS.md"
    if agents.exists() and not agents.read_text(encoding="utf-8").startswith(CONTEXT_MARKER):
        context = "Project ini memakai AI Presentation Studio. Baca state/operator_context.md dan state/workspace.json sebelum mengerjakan permintaan pengguna. Pertahankan instruksi AGENTS.md yang sudah ada."
        prompt = context + ("\n\n" + prompt if prompt else "")
    return prompt


def launch(workspaces, project, resume=False, runner=None, prompt=None, agent="codex"):
    """Start the chosen agent CLI (codex or claude) in the selected project."""
    if any(not row["verified"] for row in ProjectIntake(workspaces, project).files()):
        raise StudioError(ErrorCode.SOURCE_CONFLICT, "A registered input is missing or changed; original lineage must be restored before prompting")
    if agent == "claude":
        from cli import claude_launcher
        executable, build = claude_launcher.resolve_claude(), claude_launcher.command
    else:
        executable, build = resolve_codex(), command
        write_codex_hooks(workspaces.root)
    workspaces.write_context(project)
    with project._lock():
        value = workspaces.metadata(project)
        value["last_chat_started_at"] = now()
        workspaces.save(project, value)
    env = agent_environment(workspaces.root, project, executable)
    if agent == "claude":
        # Studio's own model calls follow the agent the user chose unless pinned.
        env.setdefault("STUDIO_MODEL_PROVIDER", "claude_cli")
    completed = (runner or subprocess.run)(build(workspaces.root, project, executable, resume, prompt), cwd=logical_path(project.path), env=env)
    with project._lock():
        value = workspaces.metadata(project)
        value["last_chat_exit_code"] = completed.returncode
        workspaces.save(project, value)
    from state.outputs import export_others
    export_others(workspaces.root, project.path.name)
    return completed.returncode
