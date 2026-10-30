# Installation and setup

Use this source checkout as the workspace root; schemas, configuration, library and project state are external workspace assets. Python 3.12 or later is required. On Windows, native rendering/live collaboration also require installed PowerPoint and pywin32. The measured environment uses Python 3.12.10, PowerPoint 16.0 and pywin32 312.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[native,test]'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\studio.exe status
.\.venv\Scripts\studio.exe capabilities
```

Run commands from this workspace or supply `--root` with its absolute path. `requirements-lock.txt` records the verified dependency versions. `scripts/studio.ps1` and `scripts/test.ps1` support the existing workspace interpreter and bundled `runtime/python_packages` standards validator.

The installation smoke creates an isolated editable venv under `runtime/installation_smoke`, reuses verified system packages and the bundled validator through a local `.pth`, and checks installation, dependency consistency, CLI/help, compilation and inspection. It performs no downloads or global installations; it is not a fresh network dependency-resolution test. Its exact method and versions are persisted in the release report.

The configured Codex CLI must be available on PATH and authenticated before reasoning, research or independent visual review. Model/provider configuration is read from the existing Codex configuration; credentials are never copied into project state. Inference jobs are ephemeral and disable tools except the explicit research search capability. Subscription pricing is unavailable to this adapter: measured token/latency telemetry is retained, monetary cost is null, and requests requiring a dollar budget fail before inference.

Native Office automation must run in a local Windows terminal with permission to access COM. In the Codex sandbox it requires approved execution outside the sandbox. Live commands borrow an existing instance; they never create or quit the user's PowerPoint application. Each live CLI command runs in its own bounded worker; timeout stops that worker and retains snapshots/authority for recovery.

Start `python run.py` or `./scripts/studio.ps1` for the activity menu and
[project workflow](PROJECT_WORKSPACES.md). `run.py` checks the selected Python
for the required dependencies and automatically uses a complete `.venv` or
Python installation on PATH when the editor's interpreter is incomplete. The
workspace VS Code settings start new terminals and the Run Python File action
in this folder. If no complete interpreter is available, create `.venv` with
the setup commands above.

The project picker manages project folders and file imports, discovers the
desktop Codex binary when it is absent from PATH, and supplies that binary on
PATH to the project chat and its Studio workers. The launcher uses `--no-daemon`
and preserves the user's existing model settings and authentication.

Run `scripts/test.ps1 --tb=short` for the complete regression suite. Run `scripts/benchmark.py --suite phase_11 --output implementation/PHASE_REPORTS/phase_11_benchmark.json` with `src` and `runtime/python_packages` on PYTHONPATH for the complete benchmark. Real quality fixtures must first be produced by the measured smoke/system benchmark scripts; an empty or missing suite cannot pass.

Successful test runs now remove their temporary pytest directory unless a current native reference/release proof still points into it. Failed runs are retained for diagnosis; `scripts/test.ps1 -KeepArtifacts` explicitly keeps successful run artifacts too.

Run `scripts/clean_workspace.ps1` to preview maintenance cleanup and `scripts/clean_workspace.ps1 -Apply` to apply it. Cleanup retains original library material and provenance, runtime dependencies, current benchmark fixtures, live/locked/unclassified projects, implementation status/release reports, and the final V1 checkpoint. It removes superseded checkpoints, unreferenced synthetic test projects, temporary rendering/provider/test artifacts and bytecode caches. The plan and results are recorded in `implementation/CLEANUP_PLAN.json` and `implementation/CLEANUP_REPORT.json`. `implementation` remains necessary for `studio status` and release verification; historical probe report paths can describe artifacts removed by maintenance.
