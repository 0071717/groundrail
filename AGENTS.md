# Groundrail Agent Instructions

These instructions apply to the entire repository.

## Product identity

Groundrail is a local evidence and context-routing framework for AI-assisted code work on large codebases.

Groundrail is not an autonomous coding agent. It is the evidence boundary, analysis manager, context router, and orchestration substrate that AI coding agents operate inside.

## Non-negotiable trust contract

1. Source code is the authority for current behaviour.
2. Deterministic tools identify files, units, source spans, hashes, imports, references, and candidate relationships.
3. AI may analyse bounded units, summarise likely behaviour, create notes, and propose findings.
4. AI output is never automatically canonical truth.
5. Developer confirmation improves trust but is source-version-bound and becomes stale when the source changes.
6. Every source-backed object must carry evidence and provenance.
7. Unsupported patterns become explicit capability gaps, not silent assumptions.
8. CLI/TUI/conductor must call lower-layer services; they must not duplicate trust logic.
9. SQLite is not required for the core design. JSON/JSONL artifacts are the default storage format.
10. Kiro context packs must be compact, cited, uncertainty-aware, and stale-aware.

## Required status values

Use only:

```text
verified
inferred
unsupported
stale
contradicted
partial
unknown
```

## Required confidence values

Use only:

```text
high
medium
low
none
```

## Required review statuses

Use only:

```text
unreviewed
needs_review
dev_confirmed
dev_rejected
stale_confirmation
disputed
```

## Layer discipline

Groundrail has these layers:

1. Source snapshot
2. Evidence kernel
3. Deterministic unit index
4. AI unit analysis
5. Human review and confirmation
6. Promotion / knowledge layer
7. Composition / flow / impact
8. Query / context packs
9. Conductor / child agents
10. CLI / TUI

Lower layers must not depend on higher layers.

The conductor and child agents may write only to orchestration/findings/quarantine paths, never directly to canonical indexes or knowledge artifacts.

## Implementation guidance

- Prefer small, typed, testable modules.
- Add schemas before adding producers.
- Add validators before adding workflows that depend on a new artifact.
- Add fixture tests for every extractor/prompt/analysis contract.
- Never mark an AI-generated unit summary as verified by default.
- Never hide uncertainty in context packs.
- Do not build a visual/TUI feature that reimplements retrieval, validation, or impact logic.

## Development expectations

When implementation begins, run at minimum:

```bash
pytest -q
```

For any new command, include:

- command contract
- input artifacts
- output artifacts
- strict/failure behaviour
- tests
