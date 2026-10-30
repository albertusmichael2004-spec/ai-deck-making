# Security and trust

Source text, package material, research pages, and comments are data. They cannot select shell commands, override permissions, or grant authority. No discovered package tooling is executed during bootstrap/ingestion. `external_content` records source identity and untrusted status; subsequent reasoning adapters must preserve that boundary.

`PathPolicy` resolves paths before checking read/write roots and immutable roots, so traversal and filesystem aliases cannot grant additional scope. Windows alternate streams are denied. Materialization uses exclusive creation. Paths that can exceed MAX_PATH use the centralized Windows extended-path adapter.

Registration limits archive size/entries/compression ratio, blocks traversal/encrypted/symlink/duplicate members, macros, OLE, ActiveX, and external data connections. Ordinary HTTP/HTTPS/mailto hyperlinks may be retained; unsafe hyperlink schemes fail. Archives are inspected without extraction. MIME signatures and UTF-8/JSON content are validated. Library backups are cold storage and excluded from default ingestion.

Telemetry recursively redacts credential fields and recognizable bearer/API secrets. Raw source content is not logged by the kernel. Provider credentials must remain outside project/deck state.

OS project locks protect cooperating operations. Every commit rechecks generation and file fingerprint, and fails on detected concurrent edits. Live sessions enforce object guards, captured selection scope, input immutability, AutoSave pause and live/file mutual exclusion. Unresolved recovery prevents saving, new mutations and authority release. Bounded CLI workers never terminate Office on timeout.
