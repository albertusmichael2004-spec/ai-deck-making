# Agents, approvals and model providers

## Choosing Codex or Claude Code

On a project page of the Studio menu:

- **[1] / [2]** start or resume Codex CLI.
- **[C] / [L]** start or resume Claude Code.

Both launchers find the CLI on PATH first, then the copy bundled with the
desktop app (`%LOCALAPPDATA%\OpenAI\Codex\bin\…\codex.exe`,
`%LOCALAPPDATA%\Claude-Data\claude_…\claude-code\…\claude.exe`). The bundled
Claude Code CLI needs its own login once: start it, type `/login`, then return.

Codex reads the project's generated `AGENTS.md`; Claude Code reads the generated
`CLAUDE.md`, which imports that same file, and also receives the Studio root
`AGENTS.md` as appended system instructions. A user-written `AGENTS.md` or
`CLAUDE.md` is never overwritten.

## Automatic approvals

Both agents use one deterministic policy, `.codex/hooks/approval_policy.py`
(a Codex `PermissionRequest` hook and a Claude Code `PreToolUse` hook):

| Request | Result |
| --- | --- |
| Every path it names is inside the Studio program folder or the selected project | Approved automatically |
| Names another project's folder, `projects/` or `runtime/others/` itself | You are asked |
| Names `.codex`, `.claude` or `.git` (the approval rules themselves) | You are asked |
| Names a path outside the Studio folder, a home/system/environment location, a registry or network share | You are asked |
| Cannot be inspected (PowerShell `-EncodedCommand`, `Invoke-Expression`) | You are asked |
| Web fetch/search (Claude Code) | Approved automatically |

The policy never denies anything; it either approves or leaves the normal
prompt in place. Decisions are logged to `runtime/agent_approvals.jsonl`.

Codex runs with `-s workspace-write -a on-request`. Writable folders are the
selected project plus every top-level Studio folder except `projects`; its
sandbox keeps `.codex` and `.git` read-only. Commands that must leave the
sandbox, such as PowerPoint automation for native render/QA, become approval
requests that the hook approves when they stay inside those folders. The hook
file `.codex/hooks.json` is regenerated at each launch for this installation.
**The first time, open `/hooks` in Codex and trust "Studio approval policy";**
Codex runs a hook only after you have reviewed it, and asks again if it changes.

Claude Code runs with `--permission-mode acceptEdits` and the same folders via
`--add-dir`. Claude Code on Windows has no OS sandbox, so the policy only checks
the paths a command names: a script inside the folder can still touch other
locations when it runs. Use Codex when that difference matters.

## Model provider for Studio's own calls

Research, reasoning, the image-capable Critic and live-comment planning call a
model CLI. `config/defaults/model.yaml` selects it (`provider: codex_cli` or
`claude_cli`, optional `claude_model`); the `STUDIO_MODEL_PROVIDER` environment
variable overrides it. Starting Claude Code from the menu sets `claude_cli` for
that session unless the variable is already set. Claude calls run in print
mode with no tools (web search only for discovery), no user/project settings,
no MCP servers and schema-validated JSON output; images are sent inline. Its
reported dollar cost is recorded in the provider job's `usage.json` but not used
for budgets, because subscription usage is not billed per call.
