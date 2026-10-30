# AI Presentation Studio

Implementation follows the complete [v6.6 architecture](docs/AI_Presentation_Studio_Architecture_v6_6.md). Current validated phase and remaining obligations live in `implementation/IMPLEMENTATION_STATUS.yaml`. This is a terminal-native product. The full V1 release requires every gate through Phase 11.

The original consulting corpus is preserved under `library/knowledge/packages/consulting_deck_knowledge_v1/original_package/`. Start its navigation from `START_HERE.md` or the restored `ALL_MATERIALS_START_HERE.md`. Source hashes, migration mappings and compatibility ZIP copies are recorded in the package manifests.

From PowerShell in this workspace:

Run `python run.py`, click **Run Python File in Terminal** on `run.py`, or use
`.\scripts\studio.ps1` to choose an activity: start/resume Codex, ingest the
registered Knowledge Base, import project materials, or manage Database PPT
references. The Codex option then opens the saved project picker. Folders and
file inventory are managed automatically. See [project workflow](docs/PROJECT_WORKSPACES.md).

For a Windows launch without waiting for VS Code extensions, double-click
`run_studio.cmd`. It selects the project's `.venv` and keeps an error visible if
startup fails. `main.py` is an alias of `run.py`; both launch from other working
directories too. The menu loads optional research, rendering and review engines
only when requested. In VS Code, reload the window after changing workspace
settings. The selected interpreter should be `.venv/Scripts/python.exe`.
Choose **D — Database** for shared references, or **R — References** inside a
selected project/business. Only explicit project selection adds its own
references to general search. See [Database workflow](docs/DATABASE.md).

The existing explicit commands remain available:

```powershell
.\scripts\studio.ps1 status
.\scripts\studio.ps1 capabilities
.\scripts\studio.ps1 bootstrap --verify
.\scripts\studio.ps1 project create my-project
.\scripts\studio.ps1 project open my-project
.\scripts\studio.ps1 compile --spec tests/fixtures/basic_spec.json --output runtime/example.pptx
.\scripts\studio.ps1 inspect runtime/example.pptx
.\scripts\studio.ps1 probe-powerpoint
.\scripts\studio.ps1 build my-project --spec tests/fixtures/basic_spec.json
.\scripts\studio.ps1 data ingest my-project --source path/to/sales.csv --request path/to/source_metadata.json
.\scripts\studio.ps1 data inventory my-project
.\scripts\studio.ps1 reason my-project --request projects/my-project/work/reasoning_request.json
.\scripts\studio.ps1 design my-project --request projects/my-project/work/design_request.json
.\scripts\studio.ps1 build my-project --spec projects/my-project/state/design_spec.json
.\scripts\studio.ps1 references ingest --dry-run
.\scripts\studio.ps1 references ingest
.\scripts\studio.ps1 references query "margin driver comparison" --content-shape chart
.\scripts\test.ps1 --tb=short
```

Python 3.12+ is required. The current workspace has its verified dependencies in the interpreter and the standards validator in `runtime/python_packages`; scripts load that local validator. Windows setup uses `python -m pip install -e '.[native,test]'`. See [installation](docs/INSTALLATION.md), [autonomous revision](docs/AUTONOMOUS_REVISION.md), [live collaboration](docs/LIVE_POWERPOINT.md) and the [release gate](docs/RELEASE_GATE.md). Exact verified versions are recorded in `requirements-lock.txt`.

Tests use a unique disposable directory below `runtime/pytest` to avoid sandbox temp-directory restrictions. Golden render and consulting quality tests are added at their roadmap phases. Source text and package production scripts are never executed as instructions. Rendering/build/research commands are exposed only after their gates pass.

Native rendering integration tests require Windows, installed PowerPoint, pywin32, and permission to automate a private read-only instance. The Codex sandbox denies COM; approved execution outside that sandbox works. Run normal PowerShell tests in a local terminal with PowerPoint available. An unavailable renderer fails the native gate and cannot be counted as a visual pass.
