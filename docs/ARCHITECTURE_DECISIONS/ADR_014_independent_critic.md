# ADR 014 — Independent image review and factual-neutral preferences

Use an image-capable isolated inference adapter rather than asking the Builder to defend itself. Whitelist review context; only raw/calculated facts receive a verified label. Interpretations are explicitly candidate claim lineage. Validate native proof hashes, per-slide completeness, finding targets, canonical severity and scores; deterministic blockers dominate model scores.

Preference learning is an independent event store with contextual shrinkage/decay and explicit reset/override rules. Factual/data/requirement/scope/brand edits remain neutral. Replayed event IDs are idempotent and conflicting replays fail. Reranking affects only eligible visual choices; it cannot alter source values or scope policy.
