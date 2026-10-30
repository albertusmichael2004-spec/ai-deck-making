# ADR 011 — Knowledge guidance and evidence-grounded reasoning

Reuse validated native package artifacts. Keep evaluation/tooling/archive content out of ordinary retrieval, preserve immutable sources and commit normalized generations through ingestion manifests. Lexical FTS is a transparent baseline; embeddings can be introduced behind KnowledgeRetriever without changing reasoning orchestration.

Reasoning strategies separate generic model inference from explicit offline driver analysis. Both emit the same StorylineGraph and face the same full schema, MECE, numerical and narrative QA. The canonical EvidenceGraph supplies business facts; library text supplies guidance only. Store conclusions only after independent verification and evidence concurrency checks.

Provider output syntax may omit unsupported constraints such as uniqueItems, but local validation retains them. This is an adapter projection, not a contract migration or weaker acceptance gate.
