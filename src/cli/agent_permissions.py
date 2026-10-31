"""Approval wiring shared by the Codex and Claude Code launchers.

Both agents get the same deterministic policy (.codex/hooks/approval_policy.py):
requests that stay inside the Studio program folder or the selected project are
approved automatically; anything else is left to the user. Other projects'
folders are never writable or auto-approved, preserving project isolation.
"""
import json
import os
from pathlib import Path

from state.io import atomic_bytes, logical_path

POLICY = ".codex/hooks/approval_policy.py"
EXCLUDED = {"projects"}


def program_folders(root):
    """Top-level Studio folders an agent may write besides its own project."""
    root = Path(logical_path(Path(root)))
    return [path for path in sorted(root.iterdir()) if path.is_dir() and path.name not in EXCLUDED and (path.name == ".venv" or not path.name.startswith("."))]


def hook_command(root):
    # A bare `python` (the launcher puts .venv first on PATH) plus one quoted
    # absolute path parses the same way in cmd, PowerShell and bash.
    return f'python "{logical_path(Path(root) / POLICY)}"'


def write_codex_hooks(root):
    """Keep the Codex PermissionRequest hook pointing at this installation's policy."""
    value = {"description": "AI Presentation Studio: auto-approve requests inside the Studio folder or selected project.", "hooks": {"PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": hook_command(root), "timeout": 30, "statusMessage": "Studio approval policy"}]}]}}
    path = Path(root) / ".codex/hooks.json"
    payload = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != payload:
        atomic_bytes(path, payload)
    return path


def claude_settings(root):
    """Inline --settings for Claude Code: the same policy as a PreToolUse hook."""
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": hook_command(root), "timeout": 30}]}]}})


def agent_environment(root, project, executable):
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # Launching from inside another Claude Code session must not look nested.
    env["PATH"] = os.pathsep.join([str(executable.parent), str(Path(root) / ".venv/Scripts"), env.get("PATH", "")])
    env["PYTHONPATH"] = os.pathsep.join([str(Path(root) / "src"), str(Path(root) / "runtime/python_packages"), env.get("PYTHONPATH", "")])
    env["STUDIO_PROJECT_DIR"] = str(logical_path(project.path))
    return env
