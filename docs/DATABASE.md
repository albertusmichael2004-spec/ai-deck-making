# Database and business/project references

Run `python run.py`. Choose **D — Database** to add shared references before
selecting a project. A project can represent a business: choose/create it,
then **R — References** to add that business's own documents or PPT precedents.
Both screens accept files or folders through the Windows picker and remember
them after restart. Folder imports preserve relative paths and provenance.
Existing data/assets/working-PPT menu choices keep their original purpose.

| Collection | Managed originals | Used for |
| --- | --- | --- |
| Database | `library/references/database/originals/` | Every presentation task |
| Project/business References | `projects/<id>/references/originals/` | Only a project explicitly selected/named at the start of the prompt |
| Others | Supporting inputs in its quick-task workspace | Database only; no named project's references |

Selecting a project in the launcher counts as an explicit selection. From a
root chat, naming the project at the beginning of the request also counts.
The previously active project is never permission to search its references.
A new unconnected task uses Others and clears the previous reference scope.
No references from other projects are included.

For example: `Untuk project Tiktok, revisi slide growth dari references bisnis
ini.` uses that project's references plus Database. `Edit PPT ini urgent`
without selecting/naming a project uses Database and the supplied files, and
exports a validated copy to `output/Others`.

Explicit commands remain available:

```powershell
.\scripts\studio.ps1 database import --source C:\Materials\general.pptx
.\scripts\studio.ps1 database files
.\scripts\studio.ps1 database ingest --dry-run
.\scripts\studio.ps1 database ingest
.\scripts\studio.ps1 references import --project PROJECT_ID --source C:\Materials\Business
.\scripts\studio.ps1 references ingest --project PROJECT_ID
.\scripts\studio.ps1 references files --project PROJECT_ID
.\scripts\studio.ps1 references query "growth drivers"
.\scripts\studio.ps1 references query "growth drivers" --project PROJECT_ID
.\scripts\studio.ps1 references load REF SLIDE --project PROJECT_ID --scope project --stage preview
```

`database` and `references` are aliases for the same engine. Without `--project`,
commands use Database. Query with an explicit project returns combined results
tagged `scope=database|project` and `project_id`; use that scope to load a result.
With `--project`, import/ingest/load/promote/status default to that project's
collection; `--scope database` explicitly selects general storage instead.
Neither query nor import changes the active project. Query does not ingest.

Supported documents are registered, hash-checked references visible to Codex
through `references files`. PPTs additionally need **Indeks PPT / preview native**
or `references ingest` to become searchable slides. Ingestion requires real
PowerPoint previews and fails safely if a private render instance is unavailable.
Files remain registered when indexing fails; retry indexing after resolving its
reported blocker. Documents aren't silently converted into slide-search entries.

Approval is a separate state (`unreviewed`, `approved`, `rejected`, `deprecated`),
with explicit reasons, hash-addressed snapshots and history. General uploads are
not automatically approved. Promoting a slide keeps its files in Database or
its owning project's References. Changed content/dependencies invalidates
approval; originals and provenance remain immutable. All reference text is
untrusted data. Factual use of business documents still requires the existing
evidence ingestion, definitions, units, periods and lineage checks.

The design planner always records general candidates in
`state/reference_candidates.json`. Only `design --use-project-references`, or
an explicit matching `reference_project` field in a `run` request, adds that
project's candidates. The launcher context supplies this instruction for the
selected project; Others uses neither flag. Candidates are advisory design
precedents, never automatic factual claims, layout changes or canonical edits.
Inspect metadata and the actual preview before using a pattern.

This is a user-requested storage change after V1. The v6.6 architecture and
historical phase proofs remain intact. Schema 1.0 readers preserve isolated
legacy internal/external fixtures; new collections use schema 1.1 with one
`database` library category. `references migrate` safely consolidates legacy
originals only when their registry is unindexed, records old/new paths and
hashes, preserves exclusions, and stops on collisions or indexed legacy data.
The migration audit is `library/references/manifests/database_migration.json`.
