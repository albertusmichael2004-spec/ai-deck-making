# VS Code: instant Run button and Deck Preview

Install once with **Terminal → Run Task → Studio: Install VS Code extension**
(or `.venv\Scripts\python.exe scripts\install_vscode_extension.py`), then run
**Developer: Reload Window**. The extension lives in `tools/vscode-studio`; the
installer packages it as a `.vsix` under `runtime/vscode` without Node or npm.

## ▶ Studio (status bar)

Starts `run.py` with `.venv\Scripts\python.exe` directly in a terminal. The
editor's ▷ button on `run.py` and `main.py` also offers **Run Studio**; pick it
once from the ▷ dropdown and VS Code keeps it as that button's default. Avoid
**Run Python File** (and F5): both go through the Python extension, which first
finishes its interpreter discovery. VS Code logs on this machine show that
first discovery taking 72–238 seconds after a window opens, while Studio itself
reaches its menu in about 0.3 seconds. The extension activates at startup, so
its buttons appear immediately. The command palette also has
**Studio: Run Studio (quick edit / Others)**.

Opening this workspace also triggers workspace-wide `workspaceContains`
searches from the Java extension pack, which time out every time and compete
with Python discovery. Disabling those Java extensions for this workspace
(Extensions view → each Java extension → **Disable (Workspace)**) removes that
startup load.

The workspace lives in OneDrive, so every file Studio or its tests create under
`runtime/` is synced. Run tests through `scripts/test.ps1`, which deletes each
run's temporary folder; successful native renders delete their staging copy.
Keeping the workspace outside OneDrive (or on a Dev Drive) removes this
overhead entirely.

## Deck Preview (status bar)

Shows the selected project's committed working deck as rendered slides. The
first preview of a deck reuses its native QA render when one matches the file
hash; otherwise PowerPoint renders it once and the result is cached under
`PROJECT/work/preview`. The panel re-renders automatically when the working
deck changes, for example after a revision commits.

- Hover shows each object's type and text; click selects it, Shift/Ctrl+click
  adds objects, and dragging marks an area (objects in that area are selected).
- Type what should change and press **Save annotation** (Ctrl+Enter). Numbered
  pins show pending annotations on the slides.
- **Copy revision request for AI** copies a prompt for Claude Code, Codex or the
  Studio chat.

Annotations are stored in `PROJECT/state/annotations.json` and are managed with
the CLI:

```powershell
.\scripts\studio.ps1 annotate list PROJECT
.\scripts\studio.ps1 annotate request PROJECT   # writes work/annotations/scope.json
.\scripts\studio.ps1 revise PROJECT --patch PATCH.json --scope projects/PROJECT/work/annotations/scope.json
.\scripts\studio.ps1 annotate done PROJECT --id note_...
```

`annotate request` marks only the annotated objects MAY_CHANGE and every other
object MUST_NOT_CHANGE, so the revision still runs through the normal native QA,
review, protected-object and recovery gates. Annotation text is untrusted user
feedback, like PowerPoint comments in the [live workflow](LIVE_POWERPOINT.md).
