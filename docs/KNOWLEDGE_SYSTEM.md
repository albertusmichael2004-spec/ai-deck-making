# Knowledge package storage

Immutable originals: `library/knowledge/packages/consulting_deck_knowledge_v1/original_package/`. ZIP backups: the sibling `archives/`. Inventory, migration plan, journal, restored-metadata provenance and verification are retained beside the source tree. No source file was rewritten. Package-relative source identities remain canonical for later derived artifacts.

All 11 initial root entries and 1,124 files were inventoried before application coding. Existing 427-entry and 112-entry file manifests were checked with their correct package-root bases. Two complete-archive-only metadata files were recovered. The restored complete manifest verifies 668 source files.

Root ZIP links use byte-identical compatibility copies. These and nested ZIP backups must be excluded from ingestion by role/fingerprint. `_Reference Library/Original PDFs` is knowledge provenance, separate from `library/references/` visual PowerPoint intelligence. Evaluations/exercises belong to isolated evaluation storage. Python tooling and cached QA content are inert provenance.

`studio bootstrap --verify` is a read-only idempotency audit. It checks inventory hashes, recovered metadata, archive aliases, new/changed/missing package files and relative Markdown links. It never treats newly created application source code as training data. Multi-format normalized knowledge ingestion begins in Phase 5.
