# Deterministic QA and real rendering

The renderer opens a read-only verified working copy in an isolated PowerPoint instance. It refuses an instance containing existing presentations, forces macro automation security, disables alerts and closes only the copy it opened. Native Office APIs reject extended-path syntax; the adapter uses a short hash-verified staging copy below `runtime/native_render/` and copies actual PNGs plus native metrics to the transaction output.

Text overflow uses PowerPoint's actual `TextRange2` bounding boxes and margin metrics. Line counts and font runs use the documented [`TextRange.Lines`](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.textrange.lines) and Runs collection methods. It does not estimate text fit from character count. Unavailable real metrics fail QA.

Canonical QA rules live in `config/qa_rules/deterministic.yaml`: canvas bounds, overflow tolerance, minimum font, title-line maximum, explicit permitted overlaps, cropped image aspect ratios, and visual regression tolerances. Protected object and outside-scope changes are blockers. Missing renders and missing registered visible citations are blockers; major layout issues fail the commit regardless of aggregate score. The isolated semantic/visual Critic uses `config/qa_rules/semantic.yaml` and actual render images.

`PresentationValidator` combines structural validation, real PNG generation, actual native geometry/text checks, image/crop verification, and protected-scope comparison. It persists render/QA reports and a contact sheet. `project.commit` validates the candidate before replacing canonical and rechecks candidate/canonical fingerprints and generation. Failure leaves canonical unchanged.

Rollback reuses the same durable transaction journal instead of a separate mutation path. Recovery can reconcile an interrupted commit or rollback; concurrent external changes become conflicts and are preserved.

The controlled golden fixture has editable input, source specification, actual PowerPoint PNGs and an explicitly reviewed manifest with renderer/font/resolution/hash/tolerance. It proves rendering stability, not consulting-quality readiness. A changed baseline cannot silently approve itself during a test.
