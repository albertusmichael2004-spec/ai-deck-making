# ADR 013 — Immutable references and progressive derivatives

Keep original snapshots authoritative and all previews/metadata/element graphs/indexes rebuildable. Publish accepted decks atomically to one canonical manifest; keep each failed deck's prior record. Derive the index with a manifest-hash guard, allowing safe recovery between manifest and index writes.

Use dependency-aware slide hashes and selective PowerPoint export. An unchanged source avoids rendering entirely. Conservative dependency invalidation may rerender additional slides when vendor packaging changes; it never declares changed dependencies unchanged. Exact duplicates reuse accepted records, including changed sources that become duplicates. Approval belongs to content, so changed content invalidates it.

Observe native/text/geometry/palette descriptors without a model call for every field. External reference data remains tainted, has explicit provenance, and is retrieved progressively. Phase 8 supplies learned preference reranking and rejected-pattern memory.
