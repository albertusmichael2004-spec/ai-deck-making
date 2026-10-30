# Architecture decisions

## ADR-001: Local Python kernel

Use Python 3.12, small capability-specific contracts and standard filesystem operations. Use JSON Schema 2020-12 through jsonschema; YAML contains configuration and state, with explicit schema_version. No service framework or GUI.

## ADR-002: Immutable corpus and archive compatibility

Move the complete original relative tree into the architecture-mandated canonical package. Inventory all 11 initial root entries and hash every file before migration. Preserve nested archives in the original tree. Root archives live in archives with byte-identical compatibility copies in original_package so the original Markdown ZIP link remains valid. All ZIPs and compatibility copies are excluded from normal ingestion. Windows denied hardlinks; the rename attempt was rolled back and retried with verified copies. Two metadata files present only in the complete archive were safely restored without altering existing content.

## ADR-003: Windows long paths

The canonical tree creates paths longer than MAX_PATH (first affected source PDF was 269 characters). Verification detected the issue and rolled back migration before retrying. Filesystem adapters use Windows extended path prefixes while metadata retains original package-relative identities. No system setting changed.

## ADR-004: Durable commit intent

OS-level project locks serialize cooperating mutations. Capture hash, mtime, size and generation; validate a separate candidate, journal intent, recheck, replace atomically and update project state. Recovery resolves interrupted intent and preserves concurrent external changes. Later render/QA gates supply presentation-specific validators. Phase 0 does not claim rendering or PPTX compilation.

## ADR-005: Lossless file-mode edits

Create native baseline objects from a trusted pinned blank OOXML template. Edit selected XML leaves directly, preserving unknown/untouched parts instead of reserializing decks through a feature-limited authoring library. Preserve native chart workbooks with recursive security validation, while retaining macro/OLE/external-connection blocks. Independent reader and byte-comparison fixtures verify the output.

## ADR-006: Actual native rendering with scoped authority

Use an isolated read-only PowerPoint worker and verified short render copies to bridge Office path constraints. Native metrics drive deterministic text/layout QA. No simulated preview can pass the real-render gate. A worker refuses existing user presentations and only closes its own copy.

## ADR-007: Project-state 1.1 and enforced render proof

Retain project-state 1.0 schema. Read/validate legacy state, explicitly migrate to 1.1 adding validation_policy=presentation, and persist the upgrade on the next state write. New projects default to the mandatory render/QA gate; raw kernel validation is restricted to test-root fixtures. Commit checks the render report candidate SHA-256. Rollback reuses the journaled transaction lifecycle and accepts an injected validator; the state kernel stays independent of concrete backends.

## ADR-008: Immutable versioned supplied evidence

Stable origin identities and exact locators coexist with immutable hash-addressed input versions. EvidenceGraph is canonical; bindings/dependencies are derived. Numeric verification recomputes from raw versions, not cached outputs. Unverified formula cells and OCR pages remain gaps.

## ADR-009: Explicit units and local schema references

Unit dimensions/currencies/scales constrain arithmetic and result declarations. Currency addition cannot bypass compatibility with a transformation label; exchange rates have explicit dimensions and source inputs. A single unit schema is reused through a filesystem-only resolver rooted in schemas; external schema retrieval is forbidden.
