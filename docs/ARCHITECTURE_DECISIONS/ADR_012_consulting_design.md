# ADR 012 — Source-bound native consulting exhibits

Keep reasoning, source resolution, layout planning, native business-object generation and independent QA separate. Reuse EvidenceGraph bindings and the transactional file backend. New native chart/table parts are merged into the original OOXML package while untouched template assets stay byte-identical; python-pptx never rewrites a canonical deck.

Version additions preserve legacy schema contracts and goldens. Native label positions must be supported by their chart type. Explicit inversion policy preserves negative-series colors, and scatter markers have no connecting series line. BubbleSizes is independently checked as either native numbers or an exact workbook-range reference because Office can return either representation.

Density fails closed; no truncation or font-size weakening. Phase 6 handles file-mode creation; Critic, references, autonomous repair and live editing remain assigned to their subsequent gates.
