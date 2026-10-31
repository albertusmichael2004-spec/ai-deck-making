# AI Presentation Studio

**A local workspace for building and revising evidence-based, editable PowerPoint presentations.**

AI Presentation Studio connects source documents, structured data, consulting knowledge, visual references, and AI-assisted analysis in one managed workflow. It produces native PowerPoint objects and checks a candidate presentation before replacing the project's working deck.

The application is written in Python. Its primary interface is a terminal menu, with an optional VS Code extension for launching Studio, previewing slides, and annotating individual objects. Microsoft PowerPoint provides native rendering and live editing on Windows.

## What you can do

| Capability | Purpose |
| --- | --- |
| Managed projects | Keep a brief, imported materials, one working deck, and recovery history together. |
| Source and data ingestion | Register documents and datasets with hashes, provenance, units, periods, and evidence bindings. |
| Knowledge retrieval | Retrieve consulting methods and presentation guidance from a registered local knowledge package. |
| Reference search | Index PowerPoint precedents with native previews, then retrieve relevant slides and layouts. |
| Research and reasoning | Use a configured model provider to research factual questions, analyze evidence, and plan an answer-first storyline. |
| Presentation compilation | Turn validated slide specifications into editable PowerPoint shapes, text, tables, and charts. |
| Scoped revision | Change specified slides or objects while checking fingerprints and protecting everything outside the edit scope. |
| Visual review and repair | Render candidates, run deterministic QA and an independent AI Critic, and attempt bounded repairs. |
| Live PowerPoint collaboration | Work with the selected managed presentation while retaining authority, save, conflict, and recovery checks. |
| VS Code Deck Preview | Select slide objects, save annotations, and generate a scoped revision request. |

Studio supports Codex CLI and Claude Code as agent interfaces. These are integrations; project authorship and commit attribution are managed separately.

## How it works

```text
Brief + source documents + data + permitted references
                         |
              Register and verify inputs
                         |
             Evidence, research, reasoning
                         |
              Storyline and slide design
                         |
              Compile or revise candidate
                         |
             Native PowerPoint rendering
                         |
          Deterministic QA and visual review
                         |
              Bounded repair, if needed
                         |
         Validated commit to the working deck
```

1. **Select a workspace.** Create or reopen a named project. Use **Others** for a quick task without a named project.
2. **Register the materials.** Studio copies supplied sources, assets, or an initial PPTX into managed storage and records their hashes and original locations. Imported originals stay unchanged.
3. **Prepare the content.** The evidence layer tracks facts and their sources. Reasoning and design modules use that evidence to create claims, exhibit choices, and slide specifications. Reference slides guide design; they do not establish business facts.
4. **Build a candidate.** The compiler creates a deck, or a scoped patch revises an existing one. Candidate files live in transaction storage, separate from the working presentation.
5. **Validate the result.** Native PowerPoint renders support layout and visual checks. Deterministic validation checks structure, numbers, evidence, edit scope, and protected objects. The autonomous workflow also requests an independent Critic review and can repair within its budgets.
6. **Commit or retain the previous version.** A successful transaction updates the same managed working path. A failed or conflicting transaction retains diagnostic and recovery state instead of treating the candidate as a completed revision.

The low-level `compile` command only creates an artifact; it is not a native visual QA pass. Use the project build, revision, or autonomous workflow to update a managed working deck. See [autonomous revision](docs/AUTONOMOUS_REVISION.md), [QA specification](docs/QA_SPEC.md), and [same-target updates](docs/TARGET_UPDATES.md).

## Requirements

| Requirement | When it is needed |
| --- | --- |
| Python 3.12 or later | Running Studio and its command-line tools. |
| Windows with desktop Microsoft PowerPoint | Native slide rendering, full presentation validation, and live collaboration. |
| `pywin32` | Access to PowerPoint automation on Windows. |
| An installed, authenticated model CLI | AI research, reasoning, independent Critic review, and agent chats. Configure Codex CLI or Claude Code for the selected workflow. |
| VS Code | Optional Studio launch buttons, Deck Preview, and annotations. |
| Local knowledge packages and references | Workflows that use those collections. These materials are provisioned separately from the source checkout. |

Pure Python and OOXML operations can run without PowerPoint, but they cannot substitute for the native rendering gate. Native rendering also needs the fonts used by the presentation and permission to automate Office.

## Installation

Clone the repository and open its root folder in PowerShell:

```powershell
git clone https://github.com/albertusmichael2004-spec/ai-deck-making.git
Set-Location -LiteralPath '.\ai-deck-making'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[native,test]'
.\.venv\Scripts\python.exe -m pip check
```

Run the installation checks:

```powershell
.\scripts\studio.ps1 status
.\scripts\studio.ps1 capabilities
.\scripts\studio.ps1 probe-powerpoint
```

`status` reports recorded implementation state. `capabilities` shows the configured capability profile. `probe-powerpoint` checks the current Office automation environment; successful installation alone does not prove that rendering is available.

The repository is used as a workspace, with external schemas, configuration, library assets, and project state. Keep those folders alongside the source. Private project files, knowledge packages, references, generated outputs, and local credentials are excluded from Git. A fresh clone therefore does not contain an existing user's materials. The default knowledge ingestion action requires the registered consulting package to be provisioned first; see [knowledge storage](docs/KNOWLEDGE_SYSTEM.md).

Install and authenticate the model CLI you intend to use through its own setup flow. Studio reads the existing provider configuration and does not copy login credentials into project state. See [installation details](docs/INSTALLATION.md) and [agent and model-provider configuration](docs/AGENTS_AND_APPROVALS.md).

## Start Studio

Use any of these entry points from the workspace root:

```powershell
.\.venv\Scripts\python.exe run.py
# Equivalent Python entry point:
.\.venv\Scripts\python.exe main.py
# PowerShell menu:
.\scripts\studio.ps1
```

On Windows, you can also double-click **`run_studio.cmd`**. The launcher prefers the workspace virtual environment, checks required imports, and opens an interactive terminal when needed. Virtual-environment activation is optional when calling its Python executable directly.

For VS Code, install the workspace extension using **Terminal → Run Task → Studio: Install VS Code extension**, then reload the window. Use **▶ Studio** or **Run Studio** to launch directly through the workspace interpreter. The regular **Run Python File** action first waits for the Python extension to initialize. See [VS Code setup and Deck Preview](docs/VSCODE.md).

### Startup menu

| Choice | Action |
| --- | --- |
| 1 | Open the project picker, then start or resume an agent chat. |
| 2 | Re-ingest the registered consulting Knowledge Base. Verified unchanged content is skipped. |
| 3 | Import PDF, data, or other documents as project source materials. |
| 4 | Add, list, and index shared Database references, including PowerPoint previews. |
| Q | Exit while keeping project state. |

**Knowledge ingestion and PPT reference indexing serve different purposes.** To use newly added reference decks in slide search, choose **4 → Indeks PPT / preview native**. Choice **2** processes the registered knowledge package.

## Everyday project workflow

### Create a presentation

1. Open Studio, choose **1**, then **N** in the project picker.
2. Enter a project name. Studio creates its managed folders and remembers the project.
3. Add supporting documents/data and any images or logos through the project menu.
4. Start a chat with **1** for Codex or **C** for Claude Code.
5. Describe the audience, decision, desired slide count, language, and source materials.

For example:

> Create an eight-slide progress report for the board using this project's registered manufacturing data. Explain the main cost drivers, preserve the reported units and periods, and identify any missing evidence before drafting conclusions.

The agent receives the selected project's inventory and Studio workflow. Missing evidence or unsupported operations can stop a task before commit. Review the recorded result and working path rather than assuming that a generated candidate is final.

### Edit an existing presentation

1. Select the intended project.
2. Choose **6 — Impor PPT untuk dikerjakan** to register the initial target. Initialization runs the existing validation gate.
3. Use **7 — Lihat file** to find the managed working presentation.
4. Request a scoped revision in chat, or select objects and add notes in **Deck Preview**.

The working deck is in the project's `presentation/` folder; the standard managed filename is `canonical.pptx`. The imported original remains under `input/target/`. Later revisions update the working deck through transactions, rather than reimporting another target over it.

When that managed deck is open in PowerPoint, the same-target workflow checks for user edits, validates a separate candidate, and refreshes the same working file after a successful commit. An unrelated open presentation does not by itself block QA. Concurrent edits, denied Office automation, or unsupported operations still need to be resolved. See [live collaboration](docs/LIVE_POWERPOINT.md) and [target updates](docs/TARGET_UPDATES.md).

### Quick tasks with Others

Choose **O — Others**, press Enter, or enter a prompt at the initial project picker. Studio manages a quick-task workspace under `runtime/others/` and exports validated results to `output/Others/`. Use the export path recorded in the task state to locate the result. See [Others workflow](docs/OTHERS.md).

### Shared and project references

| Collection | Contents | Access scope |
| --- | --- | --- |
| Knowledge Base | Registered consulting methods, guidance, and source provenance. | Knowledge retrieval workflows. |
| Database | Shared reference documents and indexed PPT design precedents. | General presentation tasks, including Others. |
| Project References | Business documents or design precedents belonging to a named project. | Only when that project was explicitly selected or named for the task. |

Add shared references through **D — Database** in the picker or startup choice **4**. Add project references through **R — References** inside a selected project. Adding a PPT registers the file; indexing creates its searchable slide metadata and previews. If indexing fails, the registered original remains available for a retry. See [Database workflow](docs/DATABASE.md) and [reference intelligence](docs/REFERENCE_INTELLIGENCE.md).

## Command-line examples

Run these from the workspace root. Replace `PROJECT_ID` with an existing ID from `project list`; request, patch, and scope JSON files must follow the relevant schemas.

```powershell
# Discover projects and registered inputs
.\scripts\studio.ps1 project list
.\scripts\studio.ps1 project files PROJECT_ID

# Import source materials or an initial working deck
.\scripts\studio.ps1 project import PROJECT_ID --source 'C:\Materials\sales.csv' --role source
.\scripts\studio.ps1 project import PROJECT_ID --source 'C:\Materials\brief.pptx' --role target

# Shared visual references
.\scripts\studio.ps1 references import --source 'C:\Materials\reference.pptx'
.\scripts\studio.ps1 references ingest --dry-run
.\scripts\studio.ps1 references ingest
.\scripts\studio.ps1 references query 'growth drivers'

# Registered knowledge package
.\scripts\studio.ps1 knowledge ingest --package consulting_deck_knowledge_v1

# Build a first deck or revise an existing one through a transaction
.\scripts\studio.ps1 build PROJECT_ID --spec projects/PROJECT_ID/state/design_spec.json
.\scripts\studio.ps1 revise PROJECT_ID --patch projects/PROJECT_ID/work/patch.json --scope projects/PROJECT_ID/work/scope.json

# Autonomous workflow with evidence, design, review, and bounded repair
.\scripts\studio.ps1 run PROJECT_ID --request projects/PROJECT_ID/work/request.json

# Prepare object-level annotations for revision
.\scripts\studio.ps1 annotate list PROJECT_ID
.\scripts\studio.ps1 annotate request PROJECT_ID

# Inspect available commands without starting a chat
.\scripts\studio.ps1 --help
```

Use `COMMAND --help` for the installed parser's exact options. See [tool contracts](docs/TOOL_CONTRACTS.md) for request and result formats.

## Architecture and repository layout

| Path | Responsibility |
| --- | --- |
| `run.py`, `main.py`, `run_studio.cmd` | Launcher entry points and interpreter selection. |
| `src/cli/` | Terminal menus, agent launchers, command parsing, and dispatch. |
| `src/state/` | Project inventory, file policy, transactions, snapshots, and recovery. |
| `src/evidence/`, `src/research/`, `src/reasoning/` | Source lineage, factual retrieval, analysis, and claims. |
| `src/knowledge/`, `src/references/` | Knowledge ingestion/retrieval and visual reference indexing. |
| `src/ir/`, `src/layout/`, `src/presentation/` | Validated slide models, layouts, OOXML compilation, native rendering, previews, and live editing. |
| `src/qa/`, `src/orchestration/`, `src/preferences/` | Validation, independent review, bounded repair, and learned preferences. |
| `src/security/`, `schemas/`, `config/` | Input controls, JSON contracts, and configurable policies. |
| `tools/vscode-studio/` | VS Code launch and slide-annotation extension. |
| `projects/` | Named user projects and their working presentations; local data excluded from Git. |
| `library/` | Local knowledge packages, references, provenance, preferences, and caches. |
| `runtime/`, `output/` | Temporary work, quick-task state, test fixtures, and exported results. |
| `tests/`, `scripts/` | Automated checks, benchmarks, setup, and maintenance tools. |
| `docs/`, `implementation/` | Architecture, operating guides, implementation state, and verification records. |

A standard named project contains:

```text
projects/<project-id>/
  project.yaml
  input/                      # Immutable registered sources, assets, target
  references/originals/       # This project's references
  state/                      # Inventory, evidence, design, annotations
  presentation/canonical.pptx # Managed working deck
  work/                       # Requests and transaction candidates
  output/qa/                  # Render and validation evidence
  history/                    # Recovery snapshots and revision history
```

Reserved synthetic fixture projects live under `runtime/test_projects/` and are hidden from the normal project picker. See [workspace storage](docs/WORKSPACE_STORAGE.md) and the [v6.6 architecture](docs/AI_Presentation_Studio_Architecture_v6_6.md).

## Configuration and safeguards

- **Models:** `config/defaults/model.yaml` selects Studio's model provider. `STUDIO_MODEL_PROVIDER` can override it for a session. Interactive agents keep their own login and model configuration.
- **Design:** Brand, layout, and preference defaults live under `config/brands/`, `config/layout_rules/`, and `config/preferences/`.
- **Capabilities and QA:** `config/capability_profiles/` and `config/qa_rules/` describe supported operations and validation rules.
- **Sources:** Supplied documents, annotations, and reference content are treated as data. They are never executable instructions or permission to search unrelated projects.
- **Edits:** Scoped fingerprints, immutable inputs, recovery snapshots, and commit-time conflict checks protect working files. A QA failure does not authorize skipping a gate.
- **Permissions:** Agent approval rules and native Office access depend on the installation. Review [agent approvals](docs/AGENTS_AND_APPROVALS.md) and [security](docs/SECURITY.md) before changing them. Local hook configuration is not included in the source repository.

## Verification and development

Activate the workspace environment before using the test wrapper:

```powershell
.\.venv\Scripts\Activate.ps1
.\scripts\test.ps1 --tb=short
```

The wrapper uses a unique temporary directory under `runtime/pytest/`. Successful runs clean up disposable artifacts unless they are referenced by current proof; failed runs retain diagnostics. Use `-KeepArtifacts` when investigating a run. Tests can recreate this temporary directory even after a workspace cleanup.

Native integration tests need Windows, installed PowerPoint, and Office automation access. Model-backed benchmarks also need the configured authenticated provider and their provisioned fixtures. A unit-test pass or mocked renderer does not establish native rendering or model quality.

The V1 roadmap through Phase 11 is recorded as complete. Detailed release evidence, maintenance results, and any environment-specific pending checks live in [implementation status](implementation/IMPLEMENTATION_STATUS.yaml) and the [release gate](docs/RELEASE_GATE.md). See [contribution guidance](CONTRIBUTING.md) for change and commit conventions.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| VS Code stays on “Activating extensions” | Launch with `run_studio.cmd` or **▶ Studio**; confirm the Python interpreter is `.venv/Scripts/python.exe`. |
| A terminal opens outside the project | Run a launcher using its full path, or open the repository root first. The root launchers resolve their own workspace. |
| No complete Python environment is found | Recreate `.venv` and install `.[native,test]` using that environment's Python. |
| A reference PPT is registered but absent from slide search | Run Database/reference indexing and inspect the per-file result. |
| Native rendering times out or automation is denied | Check `probe-powerpoint`, Office access, fonts, and recorded render diagnostics. |
| A revision conflicts with a user edit | Preserve the user changes, refresh inspection and scope, and retry against current fingerprints. |
| A fresh clone has no Knowledge Base | Provision the registered package separately; ingestion cannot create missing original materials. |

## Documentation

- [Installation](docs/INSTALLATION.md), [project workflow](docs/PROJECT_WORKSPACES.md), and [VS Code tools](docs/VSCODE.md)
- [Evidence engine](docs/EVIDENCE_ENGINE.md), [research](docs/DEEP_RESEARCH.md), [reasoning](docs/CONSULTING_REASONING.md), and [design](docs/CONSULTING_DESIGN.md)
- [Autonomous revision](docs/AUTONOMOUS_REVISION.md), [style revision](docs/STYLE_REVISION.md), and [live PowerPoint](docs/LIVE_POWERPOINT.md)
- [QA specification](docs/QA_SPEC.md), [security](docs/SECURITY.md), and [architecture decisions](docs/ARCHITECTURE_DECISIONS)

Maintained by [Albertus Michael](https://github.com/albertusmichael2004-spec).
