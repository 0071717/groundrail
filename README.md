# Groundrail

Groundrail is a local, deterministic evidence and context-routing framework for AI-assisted code work on large codebases.

The immediate target environment is a filesystem-only developer workspace where `kiro-cli` is available, MCP is unavailable, and the developer needs accurate help with UI/API bug fixing, feature implementation, codebase questions, impact analysis, review planning, and flow understanding.

Groundrail is **not** another autonomous coding agent. It is the evidence boundary, context router, and orchestration substrate that AI coding tools operate inside.

## Core product promise

Groundrail helps Kiro and other AI tools answer better by giving them a compact, evidence-backed map of the codebase instead of forcing them to rediscover the whole repository on every task.

```text
source repos
  -> deterministic source/unit indexes
  -> AI unit analysis with evidence and uncertainty
  -> validation, review, stale checks, and promotion gates
  -> context packs and citations for Kiro
  -> conductor/orchestration workflows
  -> CLI/TUI cockpit for daily developer use
```

## The key architectural shift

Groundrail does **not** try to deterministically infer all software behaviour. That is too hard for real React/TypeScript, FastAPI/Pydantic, custom wrappers, generated clients, OpenSearch, and large codebases.

Instead, Groundrail uses this practical model:

```text
1. Deterministically identify bounded code units and evidence spans.
2. Use AI to deeply analyse each unit in isolation.
3. Store AI analysis as inferred, source-backed, stale-detectable analysis artifacts.
4. Let developers confirm, reject, annotate, and promote important claims.
5. Compose validated/unit-level knowledge into flows, impact reports, context packs, and Kiro prompts.
6. Audit AI answers so unsupported or stale claims remain visible.
```

## Main layers

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

See [`docs/01_ARCHITECTURE_AND_LAYERS.md`](docs/01_ARCHITECTURE_AND_LAYERS.md) for the full architecture.

## Key design rule

AI-generated summaries and notes are useful, but they are not automatically truth.

Every AI-generated object must carry:

- source evidence
- source commit/hash metadata
- confidence
- uncertainty
- review state
- stale-check inputs
- provenance

Developers can later confirm important inferred knowledge, but confirmations are source-version-bound and become stale when the source changes.

## Planning documents

Start here:

- [`docs/00_EXECUTIVE_SUMMARY.md`](docs/00_EXECUTIVE_SUMMARY.md)
- [`docs/01_ARCHITECTURE_AND_LAYERS.md`](docs/01_ARCHITECTURE_AND_LAYERS.md)
- [`docs/02_CONTRACTS_AND_ARTIFACTS.md`](docs/02_CONTRACTS_AND_ARTIFACTS.md)
- [`docs/03_AI_UNIT_ANALYSIS_AND_HUMAN_REVIEW.md`](docs/03_AI_UNIT_ANALYSIS_AND_HUMAN_REVIEW.md)
- [`docs/04_CODEATLAS_REUSE_PLAN.md`](docs/04_CODEATLAS_REUSE_PLAN.md)
- [`docs/05_TOOLS_AND_COMMANDS.md`](docs/05_TOOLS_AND_COMMANDS.md)
- [`docs/06_ROADMAP.md`](docs/06_ROADMAP.md)
- [`docs/07_RISKS_LIMITATIONS_CONCERNS.md`](docs/07_RISKS_LIMITATIONS_CONCERNS.md)
- [`docs/08_IMPLEMENTATION_HANDOFF.md`](docs/08_IMPLEMENTATION_HANDOFF.md)
- [`docs/09_INDEPENDENT_ARCHITECTURE_REVIEW.md`](docs/09_INDEPENDENT_ARCHITECTURE_REVIEW.md) — adversarial independent review of the plan

## Current status

This repository is currently the clean planning/specification home for Groundrail. Implementation should follow the architecture and roadmap documents before code is added.
