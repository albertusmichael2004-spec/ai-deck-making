# Supplied evidence and source policy

Project inputs are copied once into `input/sources/<source_id>/<sha256>/` and never overwritten. A source identity is stable by its registered origin, while byte hashes identify immutable versions. Changes generate a new materialization and retain prior versions; unchanged bytes and ingestion context skip work. Source dates and periods are explicit metadata and remain separate from retrieval/refresh timestamps.

Extractors handle CSV, XLSX, JSON/JSONL, PDF text/tables, DOCX paragraphs/tables, TXT and Markdown. Locators identify rows/columns, sheet cells, JSON pointers, pages/tables or text lines. Formula cells are retained with their expression/cache metadata and stay unverified until independently recalculated. PDF pages without text remain OCR gaps. Missing facts are never manufactured.

Evidence types distinguish raw facts, calculated facts, interpretations, hypotheses and recommendations. Hypotheses alone cannot ground material conclusions. Unknown/stale evidence and unspecified/mixed units cannot silently enter a material numeric calculation or exhibit binding.

Calculations use a bounded whitelist of arithmetic syntax with Decimal and explicit input IDs/units. Calls, attributes, indexing, comprehensions and exponentiation are denied. Numeric verification re-extracts raw immutable source bytes and recomputes the calculation before comparing displayed values; it does not trust the cached result.

External facts are not researched in Phase 3. Phase 4 research results must satisfy the same source identity, source-quality, contradiction, freshness and lineage rules before promotion. Package evaluations and production tooling are separate knowledge roles and are not ordinary evidence retrieval instructions.
