import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli import claude_launcher, codex_launcher
from cli.agent_permissions import claude_settings, hook_command, program_folders, write_codex_hooks
from research.provider import ClaudeProvider, CodexProvider, inference_provider
from state.errors import ErrorCode, StudioError
from state.workspace import Workspaces


def folders(args):
    return {args[index + 1] for index, value in enumerate(args) if value == "--add-dir"}


def test_codex_gets_the_program_folder_but_not_other_projects(repo, project):
    args = codex_launcher.command(repo, project, Path("codex.exe"))
    assert args[args.index("-a") + 1] == "on-request" and args[args.index("-s") + 1] == "workspace-write"
    assert str(repo / "projects") not in folders(args)
    assert {str(repo / name) for name in ["config", "schemas", "runtime"]} <= folders(args)


def test_codex_hook_file_points_at_this_installations_policy(repo):
    hooks = json.loads(write_codex_hooks(repo).read_text(encoding="utf-8"))
    handler = hooks["hooks"]["PermissionRequest"][0]["hooks"][0]
    assert handler["command"] == hook_command(repo) and str(repo / ".codex/hooks/approval_policy.py") in handler["command"]


def test_claude_command_uses_accept_edits_policy_hook_and_studio_instructions(repo, project):
    (repo / "AGENTS.md").write_text("Studio rules", encoding="utf-8")
    args = claude_launcher.command(repo, project, Path("claude.exe"), resume=True, prompt="edit slide 2")
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    settings = json.loads(args[args.index("--settings") + 1])
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == hook_command(repo)
    assert args[args.index("--append-system-prompt-file") + 1] == str(repo / "AGENTS.md")
    assert "--continue" in args and args[-1] == "edit slide 2"
    assert "--dangerously-skip-permissions" not in args and str(repo / "projects") not in folders(args)
    # The variadic --add-dir list must end before the prompt.
    assert args.index("--add-dir") < args.index("--permission-mode") < len(args) - 1


def test_claude_launch_writes_claude_md_and_selects_claude_provider(repo, project, monkeypatch):
    workspaces = Workspaces(repo)
    workspaces.register(project)
    monkeypatch.setattr(claude_launcher, "resolve_claude", lambda: Path("C:/apps/Claude/claude.exe"))
    monkeypatch.delenv("STUDIO_MODEL_PROVIDER", raising=False)
    calls = []
    assert codex_launcher.launch(workspaces, project, agent="claude", runner=lambda args, **options: calls.append((args, options)) or SimpleNamespace(returncode=0)) == 0
    args, options = calls[0]
    assert args[0].endswith("claude.exe") and options["env"]["STUDIO_MODEL_PROVIDER"] == "claude_cli"
    assert options["env"]["STUDIO_PROJECT_DIR"].endswith(project.path.name)
    assert "@AGENTS.md" in (project.path / "CLAUDE.md").read_text(encoding="utf-8")


def test_user_written_claude_md_is_preserved(repo, project):
    (project.path / "CLAUDE.md").write_text("My own notes", encoding="utf-8")
    Workspaces(repo).register(project)
    assert (project.path / "CLAUDE.md").read_text(encoding="utf-8") == "My own notes"


def test_provider_follows_environment_then_config(repo, monkeypatch):
    monkeypatch.delenv("STUDIO_MODEL_PROVIDER", raising=False)
    assert isinstance(inference_provider(repo), CodexProvider)
    monkeypatch.setenv("STUDIO_MODEL_PROVIDER", "claude_cli")
    assert isinstance(inference_provider(repo), ClaudeProvider)
    monkeypatch.setenv("STUDIO_MODEL_PROVIDER", "other")
    with pytest.raises(StudioError):
        inference_provider(repo)


def claude_output(events):
    return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(event) for event in events), stderr="")


def result(structured, searches=0, error=False):
    return {"type": "result", "is_error": error, "result": "Not logged in" if error else "", "structured_output": structured, "usage": {"input_tokens": 20, "output_tokens": 10, "server_tool_use": {"web_search_requests": searches}}, "total_cost_usd": 0.01}


def test_claude_provider_is_tool_less_metered_and_structured(repo, monkeypatch):
    provider = ClaudeProvider(repo)
    provider.executable = "claude"
    commands = []
    def run(command, **kwargs):
        commands.append((command, kwargs))
        return claude_output([result({"findings": []})])
    monkeypatch.setattr("subprocess.run", run)
    assert provider.extract({"url": "https://example.org/", "regions": []}, {"question": "q"}) == []
    command, options = commands[0]
    assert command[command.index("--tools") + 1] == "" and "--allowedTools" not in command
    assert command[command.index("--setting-sources") + 1] == "" and "--no-session-persistence" in command
    assert "CLAUDECODE" not in options["env"] and provider.last_usage["tokens"] == 30


def test_claude_provider_blocks_tools_and_surfaces_cli_errors(repo, monkeypatch):
    provider = ClaudeProvider(repo)
    provider.executable = "claude"
    tool = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}
    monkeypatch.setattr("subprocess.run", lambda *a, **k: claude_output([tool, result({"sources": []}, searches=1)]))
    with pytest.raises(StudioError) as blocked:
        provider.search("test", 1)
    assert blocked.value.code == ErrorCode.SECURITY_BLOCK
    monkeypatch.setattr("subprocess.run", lambda *a, **k: claude_output([result(None, error=True)]))
    with pytest.raises(StudioError) as failed:
        provider.complete("x", {"type": "object"})
    assert "Not logged in" in json.dumps(failed.value.details["provider_errors"])
    monkeypatch.setattr("subprocess.run", lambda *a, **k: claude_output([result({"sources": []}, searches=0)]))
    with pytest.raises(StudioError):
        provider.search("test", 1)


def test_program_folders_skip_projects_and_hidden_folders(repo):
    (repo / ".git").mkdir(exist_ok=True)
    (repo / ".venv").mkdir(exist_ok=True)
    names = {path.name for path in program_folders(repo)}
    assert "projects" not in names and ".git" not in names and ".venv" in names
    assert json.loads(claude_settings(repo))["hooks"]["PreToolUse"]
