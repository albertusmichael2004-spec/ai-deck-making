# Project picker and managed files

From PowerShell in this workspace, run:

```powershell
python run.py
# Or use the existing PowerShell launcher:
.\scripts\studio.ps1
# The same project picker:
.\scripts\studio.ps1 project
```

You can also open the root `run.py` in your editor and click **Run Python File
in Terminal**. It locates this workspace automatically, including when invoked
from another directory. On Windows, an editor output panel or `pythonw` launch
opens a real console so the startup menu and Codex can accept keyboard input.
Choose Codex to open the project picker, then **1** to start a chat or **2** to
resume its last chat.

The menu lists saved user projects. Choose **N** to create a project and enter a
normal display name, such as `Board Meeting October 2026`. Studio creates its
canonical folders and remembers the project under `projects/<generated-id>/`.
Synthetic test projects are hidden; existing user projects remain available.

For a task without a named project, press Enter, choose **O** (Others), or type
the actual prompt at the initial picker. Its results go to `output/Others`.
See [quick edits](OTHERS.md) and [database/fixture folders](WORKSPACE_STORAGE.md).

The startup menu also offers Knowledge ingestion, project-material import, and
Database PPT-reference management. Knowledge ingestion rechecks the registered
consulting package and its PDF/Markdown/JSON/CSV materials; unchanged content is
verified and skipped. It does not add arbitrary PDFs to the shared Knowledge
Base. Use project-material import to register a new PDF or data file as an
immutable project source. Database ingestion indexes visual PPT references.

After selecting a project:

| Choice | Action |
| --- | --- |
| 1 | Start a new Codex chat in this project |
| 2 | Resume the last Codex chat from this project directory |
| 3 | Choose supporting documents/data using the Windows file picker |
| 4 | Choose a folder of supporting materials |
| 5 | Choose images/logos |
| 6 | Import one existing PPTX as the initial working presentation |
| 7 | List registered files and the working presentation path |
| D | Add/list general Database references |
| R | Add/list this selected project's/business's References |
| B | Select another project or create a new one |
| Q | Exit; saved projects and inputs remain available |

Choose supporting files, then start chat. Prompt normally, for example:
`Buat deck 8 slide dari data project ini untuk board meeting. Gunakan Bahasa
Indonesia dan jelaskan driver pertumbuhan revenue.` Codex receives the selected
project ID, file inventory, canonical PPTX location and the existing Studio
workflow. It asks for missing factual metadata rather than inventing units or
periods. The launcher uses the user's Codex model configuration and authentication.
The selected project's References are combined with general Database references;
other projects are excluded. Others uses Database only. See [reference scope](DATABASE.md).
It discovers the installed CLI, including the Codex desktop binary when absent
from terminal PATH, and uses `--no-daemon` for the desktop CLI package.

Exit the Codex chat to return to the project menu. After closing the terminal,
run the same Studio command: projects and registered files reappear. **2** resumes
the latest chat scoped to the selected project; it needs an existing Codex
session. **1** starts a new chat with the same saved project and files.

This picker is the Studio launcher before the native Codex chat. The native
Codex composer and slash-command list retain their installed behavior. Inside
chat, project instructions tell Codex to register supplied local attachments
through `project import`, then work from the managed inventory. Menu imports
are deterministic; chat attachments become registered when that instruction is
performed by Codex. Pasting text alone does not create a supporting file.

## Storage and the working PPTX

Each project uses the existing canonical layout:

```text
projects/<generated-id>/
  project.yaml
  AGENTS.md
  input/
    sources/uploads/<version>/...     supporting files and original relative paths
    assets/uploads/<version>/...      images/logos
    target/uploads/<version>/...      immutable imported initial PPTX
  state/
    workspace.json                   display name, provenance and import inventory
    operator_context.md              generated context for Codex
  presentation/canonical.pptx         single working presentation
  history/snapshots/                  recovery versions from the existing engine
  work/                              requests and validated transaction candidates
  output/qa/                         existing QA/render proof
```

A new project reserves the working PPTX path; its first successful build creates
the file. An imported initial PPTX must pass the existing native render and QA
gate before becoming canonical. Importing another target cannot overwrite an
existing working deck: subsequent changes use the existing scoped revision
workflow and continue in `presentation/canonical.pptx`. History snapshots and
temporary validation candidates are recovery artifacts, not extra working decks.

Imports copy bytes, record original paths and SHA-256 hashes, and leave external
originals unchanged. Reimporting the same content is idempotent; changed content
gets a separate immutable version. Files chosen together share a version folder
with their common relative paths, preserving links between the selected files.
Folder imports preserve internal relative
paths and relative document links. External links remain external. Unsupported
files, links/junctions, unsafe archives and provenance-sidecar filename conflicts
are rejected without weakening security rules. A folder with filenames colliding
with `*.source.json` can be supplied as a ZIP to preserve its interior exactly.
Studio never extracts arbitrary uploads or executes their contents.

Missing or altered managed inputs block chat launch until their lineage is
restored. Existing custom project `AGENTS.md` instructions are preserved; the
launcher supplies a separate context pointer. Cleanup protects all projects
registered with `state/workspace.json`, including adopted legacy projects.

## Optional terminal commands

The menu avoids routine path entry. These commands support automation and
existing integrations:

```powershell
.\scripts\studio.ps1 project list
.\scripts\studio.ps1 project use PROJECT_ID
.\scripts\studio.ps1 project files
.\scripts\studio.ps1 project import --source 'C:\Downloads\sales.xlsx'
.\scripts\studio.ps1 project import PROJECT_ID --source 'C:\Downloads\materials' --role source
.\scripts\studio.ps1 project import PROJECT_ID --source 'C:\Downloads\logo.png' --role asset
.\scripts\studio.ps1 project import PROJECT_ID --source 'C:\Downloads\starting.pptx' --role target
.\scripts\studio.ps1 project start PROJECT_ID
```

Explicit imports into another project do not silently switch the saved active
selection. Existing `project create/open/snapshot/rollback/recover`, data, build,
revision and live commands keep their existing contracts.
