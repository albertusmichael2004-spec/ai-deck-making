# Database folders and validation fixtures

General PPT originals now use one `library/references/database/originals/`
collection. Named projects/businesses have `references/originals/` private to
their explicit prompt scope. The [Database guide](DATABASE.md) explains the
picker, imports, searches and approval states. Legacy original paths and hashes
are preserved in `library/references/manifests/database_migration.json`.

Reference folders named `ref_<hash>` are managed snapshots, not the original
user-facing PPT filenames. Their hashes identify reference sources. Each holds
immutable versions and links to previews, metadata, approvals and provenance.
Remove them through a consistent archive/manifest update, not by deleting just
one folder while leaving its registry entries behind.

The two inactive fixtures from `native-reference-90a0bf063c.pptx` and
`native-reference-ef0d0ae731.pptx` were archived and removed from the production
reference library. The audit, archive path and SHA-256 are recorded in
`implementation/PHASE_REPORTS/reference_fixture_cleanup.json`. The archive
contains original snapshots, previews, metadata, promoted copies, provenance
and the former registry/index. Its member manifest verifies every saved byte.
The current reference benchmark uses a separate isolated fixture, so these
production test snapshots are not needed for current retrieval or benchmarks.
The consulting knowledge corpus was not changed.

The historical hash-suffixed project folders below are V1 validation fixtures:

| Prefix | Purpose |
| --- | --- |
| `consulting-e2e`, `chart-boundaries`, `research-design` | Design, chart and end-to-end quality proofs |
| `critic-smoke`, `reason-smoke` | Reasoning and independent review proofs |
| `incremental-native` | Scoped native render and revision proof |
| `live-native`, `live-comments`, `live-table` | PowerPoint sessions, comment and table regression proofs |
| `qa-smoke` | Deterministic QA and same-target PowerPoint lifecycle proofs |
| `release-manufacturing`, `release-retail`, `release-financial_services` | Final V1 release scenario proofs |

Their suffixes keep runs distinct. On 2026-10-24, all 52 unregistered fixture
folders were removed from `projects` after archiving and verifying all 1,026
files. The recoverable archive is
`implementation/ARCHIVES/project_fixtures_20261024.zip`; its ARCHIVE_MANIFEST.json
preserves original paths, hashes, timestamps and provenance bytes. The external
audit is `implementation/PHASE_REPORTS/workspace_cleanup_20261024.json`.
Historical reports still record their original absolute paths: restore their
archived bytes into an isolated validation workspace before rerunning historical
proofs. Archive verification preserves those proofs; their old directories are
no longer active project storage.

New synthetic fixture IDs are stored under `runtime/test_projects`, while named
user projects stay under `projects`. Legacy paths remain readable if explicitly
restored. The ordinary picker excludes unregistered fixtures, and
`--include-fixtures` also inspects the internal test-project location. Explicitly
adopted fixtures remain visible to their operator. No knowledge packages or
general reference originals were removed.

The archived same-target proof uses `qa-smoke-82d95e8a3527`; its three genuine native
render/QA cases are recorded in `implementation/PHASE_REPORTS/target_update_native_20261022.json`.
The earlier synthetic attempts `qa-smoke-70fa69f926cf`, `qa-smoke-19a8155b3d37`
and `qa-smoke-68b5004d1ad9` retain their diagnostic/snapshot data. They are not
user decks or additional working outputs. Owned test windows were reconciled
as recorded in `implementation/PHASE_REPORTS/target_test_cleanup_20261022.json`.

Quick edits without a named project are grouped as Others. Public PPT results
go to `output/Others`; internal QA/recovery state lives in `runtime/others`.
See [Others](OTHERS.md) and [project picker](PROJECT_WORKSPACES.md).
