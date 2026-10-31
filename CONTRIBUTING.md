# Contributing

AI Presentation Studio is a managed presentation workspace. Application changes must preserve its existing architecture, project isolation, immutable originals, and validated commit workflow.

## Before changing the application

1. Read [AGENTS.md](AGENTS.md), the [architecture](docs/AI_Presentation_Studio_Architecture_v6_6.md), and the relevant operating guide.
2. Keep changes focused. Use existing command, schema, transaction, and recovery contracts.
3. Run checks appropriate to the change. Native rendering and live collaboration require real PowerPoint verification; mocked tests do not replace those checks.
4. Update affected documentation and `implementation/IMPLEMENTATION_STATUS.yaml`. Retain a verified checkpoint for completed application work.

Use the setup and test commands in the [README](README.md). Do not commit credentials, personal settings, user projects, source documents, generated presentations, runtime caches, or local archives. Knowledge and reference originals remain in local managed storage.

## Commit messages

Describe the concrete change using a short imperative subject. Use a body when a reviewer needs the reason, compatibility impact, or verification details.

Examples:

```text
Document installation and presentation workflows
Separate CLI commands by workflow
Preserve the working presentation during validated updates
```

Avoid temporary labels such as “baseline snapshot before refactoring,” vague messages such as “update files,” or tool names that do not explain the resulting behavior. Name an integration when that is the actual subject of the change.

Keep the configured human author and committer identity. Do not append automated AI co-author or generated-by trailers unless the repository owner explicitly requests them. Claude Code attribution is disabled in the repository settings and Studio launcher; this does not disable the integration itself.

## Pull requests

Explain the problem, the resulting behavior, and the checks performed. Include concrete limitations or unresolved failures. Do not describe a native or model-quality check as passing unless its actual evidence is available.
