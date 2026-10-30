# Evidence engine

`EvidenceStore` owns immutable source registration and version refresh. `extract` owns native format parsing. `EvidenceGraph` owns typed evidence and support links. `DependencyGraph` tracks source values through calculations, claims, bindings, exhibits and slides. Arithmetic, unit validation and independent verification are separate small contracts.

The canonical `state/evidence_graph.json` includes source registry, evidence nodes and dependency/binding state. `data_bindings.json` and `dependency_graph.json` are rebuildable views of the same canonical rules, not separately maintained business logic.

Refresh checks source fingerprints, preserves old bytes, updates stable locator identities, recalculates affected numeric nodes in dependency order, and marks affected interpretations/recommendations stale for later reasoning review. Missing inputs or changed unit compatibility leave calculations stale. Source-date/period changes also invalidate consumers. A cycle is rejected before registration.

`EvidenceContext` is injected into compilation. Required slide claims must resolve, be current and pass raw-source verification. Source-note IDs must cover the full supporting source set. Source notes remain editable text placed by the layout adapter; the compiler does not decide consulting logic. Pure hypotheses must remain explicitly identified as such.

Manual terminal operations: `data ingest`, `data calculate`, `data claim`, `data bind`, `data refresh`, `data trace`, `data verify`, `data gaps` and `data inventory`. Requests and metadata are schema-validated JSON files. Source files and their text are untrusted data and are never executed.
