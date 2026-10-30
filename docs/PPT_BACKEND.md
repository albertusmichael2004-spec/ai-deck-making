# PowerPoint backend

The compiler depends on capability-specific protocols, not concrete PowerPoint libraries. `OOXMLBackend` opens ZIP packages, inspects native identities/text/geometry, creates editable text and shapes from validated baseline intent, and applies scoped text/geometry/fill patches. Untouched payloads remain byte-identical. Masters, layouts, chart data, media, notes, hyperlink relationships and animation XML are preserved in round-trip fixtures.

The adapter uses the pinned python-pptx package's blank OOXML template for new packages. Production edits use XML leaf mutation rather than library resave, which could discard unknown structures. Shape assembly, XML parsing, mutation and package adaptation have separate modules. Generated object identities use stable UUIDs with deterministic native numeric IDs and explicit collision rejection.

Protected scope includes ancestor groups. All patch targets require preplanned object fingerprints. `MUST_CHANGE`, `MAY_CHANGE` and `MUST_NOT_CHANGE` scopes are validated; a patch cannot write canonical or immutable inputs directly. The kernel controls canonical commit.

Phase 1 validates structural correctness only and explicitly records `rendered: false`. Actual render/overflow/visual QA is required in Phase 2 before presentation-safe success can be claimed. Advanced consulting exhibits/brands arrive in Phase 6. Native chart workbooks already present in a source deck are validated recursively and preserved; chart creation is not yet advertised.

The early Windows probe attaches only to an existing instance, inspects open presentations/active selection/comments when supported, and can use SaveCopyAs for safe snapshots. It never saves the open deck or launches a live revision workflow. Runtime limitations are structured capability failures. Full live collaboration remains Phase 10.
