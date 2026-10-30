# Quick edits in Others

Run `python run.py`. At the initial picker, press **Enter** to start a quick
edit, choose **O** to find saved Others work, or type the actual request directly.
Typing a request starts Codex with that request in a fresh Others task.
No named project or manually arranged folder is needed.

You can also launch a quick edit directly:

```powershell
python run.py --others
# Or:
.\scripts\studio.ps1 project others
```

In its menu, **6** chooses the original PPTX, **3/4** adds supporting files,
and **1** starts Codex. The original is copied into immutable task inputs.
Successful Studio imports, builds and scoped revisions export the validated
working deck to `output/Others/<original-name>_<task-suffix>.pptx`. Revisions
update that task's same output file. A different quick edit gets a different
output, even when its original filename is identical.

The public output folder is `output/Others`. Internal state is kept in
`runtime/others/<task-id>/` for evidence, one canonical working PPTX, native QA,
snapshots and recovery. These folders are necessary engine state; they are
managed automatically and are retained by maintenance cleanup. Others tasks
appear under the **O** group rather than as named projects in the main picker.

**O** lets you reopen a saved quick edit; **2** resumes its Codex chat. **8**
exports its validated deck on demand. If a live session still owns the deck,
finish that session and restore file authority before exporting. Failed QA
never publishes an unvalidated candidate. If an exported file was changed
externally, the exporter refuses to overwrite it: preserve those edits by
starting a fresh quick edit with that file, or resolve them explicitly.
An export failure does not undo a successful canonical commit; retry
`project export ID` after resolving the output conflict.

For Codex sessions started directly in the repository, the root `AGENTS.md`
instructs the agent to set up Others for a presentation task without a selected
project. This is agent-mediated routing, not a new built-in Codex slash command.
Coding/setup requests keep their existing application workflow.

Agent/automation setup without an interactive menu:

```powershell
.\scripts\studio.ps1 project quick
# Use the returned ID explicitly:
.\scripts\studio.ps1 project import ID --role target --source 'C:\Downloads\urgent.pptx'
.\scripts\studio.ps1 project export ID
```
