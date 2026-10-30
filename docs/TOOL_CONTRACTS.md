# Tool contracts

`orchestration.contracts` defines small `ProjectContract` and `FilesContract` protocols and an explicit capability registry. Unavailable capabilities raise structured `CAPABILITY_UNAVAILABLE`; registry entries cannot advertise availability without an implementation.

Project operations: create/open, snapshot, begin, candidate, commit, abort, detect_conflict, rollback, recover. Only `Project.commit(transaction_id, validator)` replaces the canonical file. The validator must return `passed: true` and no errors, and must not mutate the candidate. Later phases supply structural/render/QA validators; the kernel itself makes no visual-success claim.

Files: inspect verifies authorized paths, extension, magic/format, archive entries and security constraints. Materialize copies to an exclusively created destination, checks source hash, and records provenance. Original package scripts stay inert. Repeated materialization cannot overwrite an existing input.

Error codes live in `state.errors.ErrorCode`; canonical folder definitions live only in `config/defaults/paths.yaml`. New versions require explicit schema migration. Unknown schema versions fail validation.
