"""Start Claude Code in one selected presentation project, mirroring the Codex launcher."""
import os
import shutil
from pathlib import Path

from cli.agent_permissions import claude_settings, program_folders
from cli.codex_launcher import startup_prompt
from state.errors import ErrorCode, StudioError
from state.io import logical_path


def resolve_claude():
    selected = shutil.which("claude")
    if selected:
        return Path(selected)
    # The Claude desktop app ships a versioned Claude Code CLI that is not on PATH.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        versions = list(Path(local).glob("Claude-Data/claude_*/claude-code/*/*/claude.exe"))
        if versions:
            return max(versions, key=lambda path: path.stat().st_mtime_ns)
    raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Claude Code CLI was not found; install it (https://claude.com/claude-code) or open Studio from a terminal where `claude` works")


def command(root, project, executable, resume=False, prompt=None):
    # File edits inside the working folders are accepted; the shared policy hook
    # approves shell/tool calls that stay inside the Studio folder or this project.
    result = [str(executable), "--add-dir", *[str(folder) for folder in program_folders(root)]]
    result.extend(["--permission-mode", "acceptEdits", "--settings", claude_settings(root)])
    instructions = Path(root) / "AGENTS.md"
    if instructions.is_file():
        result.extend(["--append-system-prompt-file", str(logical_path(instructions))])
    if resume:
        result.append("--continue")
    prompt = startup_prompt(project, prompt)
    if prompt:
        if os.name == "nt" and executable.suffix.lower() in {".cmd", ".bat"}:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Use a Claude executable for a startup prompt, or enter the prompt inside Claude after choosing Others")
        result.append(prompt)
    return result
