# Groundrail Executive Summary

## Why Groundrail exists

Groundrail exists because large mature codebases are hard for AI coding tools to work on accurately when they must rediscover the repository from scratch for every task.

The primary user environment is:

- AWS WorkSpaces or similar locked-down workspace.
- `kiro-cli` with a strong model such as Opus 4.6.
- MCP unavailable or disabled.
- Large React/TypeScript UI and Python/FastAPI/Pydantic API repositories.
- Custom libraries, wrappers, generated clients, OpenSearch, config files, tests, and product behaviour spread across many files.

Groundrail should help with:

- fixing UI and API bugs;
- adding or improving UI/API features;
- answering questions such as "how does this feature work?";
- investigating "why is this happening?";
- explaining "why is this error raised in production?";
- understanding code/API/UI/data flows;
- selecting relevant files and tests;
- creating Kiro context packs with citations;
- visualising or browsing flows later through CLI/TUI/UI.

## The core mistake to avoid

The project should not attempt to deterministically understand every behaviour in a real application.

That is too hard, especially for:

- React/TypeScript code with custom hooks, wrappers, route factories, TanStack Query, generated clients, barrels, aliases, feature flags, and dynamic routes;
- Python/FastAPI code with dependency injection, router composition, dynamic imports, decorators, async flows, Pydantic v1/v2 differences, and OpenSearch query builders;
- cross-stack behaviour where UI state, API contracts, backend validation, data access, and runtime configuration interact.

Groundrail should not become another sprawling research repo that tries to statically solve everything.

## The practical architecture

Groundrail should use this model:

```text
Deterministically identify bounded code units and evidence spans.
AI analyses each unit in isolation.
Groundrail stores the analysis as inferred, source-backed, stale-detectable artifacts.
Developers confirm/reject important pieces over time.
Groundrail composes validated information into context packs, flows, impact reports, and Kiro prompts.
Kiro answers with citations and is audited for unsupported claims.
```

The deterministic foundation should reliably produce:

- source snapshot;
- file hashes;
- function/class/component/hook boundaries;
- source spans;
- imports/exports;
- obvious call candidates;
- endpoint/route/API-client candidates;
- file/snippet hashes;
- unit complexity metrics;
- capability gaps.

The AI layer should analyse each bounded unit for:

- behaviour summary;
- intent;
- inputs;
- outputs;
- side effects;
- state read/write;
- API effects;
- errors;
- business-rule candidates;
- uncertainty;
- potential bugs;
- refactor opportunities;
- test gaps;
- complexity notes.

The trust layer should ensure:

- AI summaries are not automatically truth;
- every analysis object has evidence and provenance;
- summaries become stale when source changes;
- developer confirmations are source-version-bound;
- important claims can be promoted only through explicit promotion gates;
- Kiro context packs clearly separate verified, dev-confirmed, inferred, partial, stale, and unsupported knowledge.

## What Groundrail should be

Groundrail should be:

- local-first;
- file-system based;
- CLI/TUI friendly;
- Kiro-oriented;
- JSON/JSONL artifact driven;
- evidence-backed;
- stale-aware;
- uncertainty-aware;
- reviewable;
- extensible through extractors and adapters;
- capable of orchestration and child-agent workflows without letting agents write canonical truth.

## What Groundrail should not be

Groundrail should not be:

- a general autonomous coding agent;
- a cloud service;
- dependent on MCP;
- dependent on SQLite for core correctness;
- an AI-generated documentation dump;
- a universal React/FastAPI semantic static analyser;
- a system where AI summaries silently become truth;
- a system where visualisation/TUI duplicates core logic.

## The main product surface

The CLI and TUI matter. They are not optional decoration.

The daily workflow should eventually feel like:

```bash
groundrail refresh
groundrail prepare debug "why is user search returning 500?"
groundrail ask "how does user search work?"
groundrail unit show unit.ui.UserSearchPage
groundrail analysis show unit.api.search_users
groundrail review list --important
groundrail flow endpoint "GET /users/search"
groundrail impact file app/services/users.py
groundrail orchestrate review --changed
groundrail tui
```

The TUI should eventually provide a cockpit over:

- latest Kiro sessions;
- selected facts and unit summaries;
- citations;
- source preview;
- stale warnings;
- AI notes;
- review queue;
- orchestrations;
- impact/flow views.

## First implementation theme

The first real implementation theme should be:

```text
Build the evidence/context/orchestration skeleton first, then add deterministic unit indexing, then add AI unit analysis, then add review/confirmation, then build flows/impact/TUI on top.
```

This prevents the repo from turning into another all-at-once system.
