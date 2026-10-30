# Schema governance

Every executable data contract carries `schema_version: '1.0'`. JSON Schemas use Draft 2020-12 and are checked with the standards validator. Kernel schemas cover project state, implementation state, transaction journals and capability manifests. Project state and journal objects reject unknown properties.

Phase 1 adds BriefSpec, DeckSpec, SlideSpec, ObjectSpec, PatchSpec and EditScope. Compilation validates brief identity, page budget, ordered slide membership, object uniqueness and each object schema. Unsupported exhibit/brand/template requirements fail explicitly instead of being silently ignored. Non-finite and non-JSON values are rejected.

Later phases add evidence/research/storyline/interaction contracts before those capabilities are advertised. A future version needs a deliberate migration; incompatible state cannot silently pass by removing version checks.
