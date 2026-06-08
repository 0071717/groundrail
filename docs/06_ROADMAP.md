# Groundrail Roadmap

This roadmap reflects the revised Groundrail architecture: deterministic unit indexing first, AI unit analysis second, human review/confirmation third, then composition, context, conductor, and TUI.

Do not implement later phases before the earlier contracts are stable.

## Phase 00: Planning and architecture pack

### Goal

Capture the product vision, architecture, contracts, CodeAtlas reuse plan, tool map, roadmap, risks, and implementation handoff.

### Outputs

```text
README.md
AGENTS.md
docs/00_EXECUTIVE_SUMMARY.md
docs/01_ARCHITECTURE_AND_LAYERS.md
docs/02_CONTRACTS_AND_ARTIFACTS.md
docs/03_AI_UNIT_ANALYSIS_AND_HUMAN_REVIEW.md
docs/04_CODEATLAS_REUSE_PLAN.md
docs/05_TOOLS_AND_COMMANDS.md
docs/06_ROADMAP.md
docs/07_RISKS_LIMITATIONS_CONCERNS.md
docs/08_IMPLEMENTATION_HANDOFF.md
```

### Done when

A reviewer can understand exactly what Groundrail is, what it is not, how it differs from CodeAtlas, what gets reused, what gets rejected, and how to implement the layers.

## Phase 01: Framework skeleton

### Goal

Create the Python package, CLI shell, workspace layout, artifact helpers, JSON/JSONL storage helpers, and tests.

### Scope

Implement only foundational plumbing:

- package structure;
- CLI parser;
- `.groundrail/` directory layout;
- artifact envelope helper;
- evidence/provenance model;
- JSON/JSONL read/write;
- basic validation;
- session store;
- seed/example retrieval item;
- no real extraction yet.

### Commands

```bash
groundrail init
groundrail validate
groundrail search
groundrail prepare
groundrail smart
```

### Done when

- CLI runs locally.
- Basic tests pass.
- Example context pack can be generated from seed data.

## Phase 02: Source snapshot and file index

### Goal

Record source reality.

### Scope

- project config;
- repo scanner;
- Git state;
- file scanner;
- ignore/generated rules;
- file hashing;
- file classification;
- changed-file detection;
- run manifest.

### Commands

```bash
groundrail snapshot
groundrail changed
groundrail status
groundrail refresh
```

### Artifacts

```text
.groundrail/source/snapshot.json
.groundrail/index/file-index.json
.groundrail/change/changed-files.json
.groundrail/audit/run-manifest.json
```

### Done when

Groundrail can reliably answer:

- what files exist;
- what commit was indexed;
- whether worktree is dirty;
- which files changed since last snapshot.

## Phase 03: Evidence kernel and strict validation

### Goal

Make artifacts trustworthy before adding AI analysis.

### Scope

- artifact envelope schema;
- evidence schema;
- provenance schema;
- status/confidence/review-status enums;
- strict validator;
- stale verifier;
- capability gaps;
- guarded writer.

### Commands

```bash
groundrail validate --strict
groundrail verify --strict
groundrail gaps
groundrail doctor
```

### Done when

Strict mode fails for:

- missing artifact envelope;
- missing evidence;
- unknown status;
- unknown confidence;
- stale source hash;
- bad snippet hash;
- malformed analysis/review objects.

## Phase 04: Deterministic unit index MVP

### Goal

Find bounded code units for AI to analyse.

### Scope

Start with Python:

- functions;
- methods;
- classes;
- source spans;
- imports;
- call candidates;
- complexity metrics;
- unit hashes.

Then add minimal TypeScript/React boundaries:

- functions;
- components;
- hooks;
- imports/exports;
- JSX component candidates;
- route/API/query candidates only as candidates.

### Commands

```bash
groundrail index units
groundrail unit list
groundrail unit show <unit-id>
groundrail unit code <unit-id>
```

### Artifacts

```text
.groundrail/index/unit-index.json
.groundrail/index/import-index.json
.groundrail/index/call-candidates.json
```

### Done when

For representative Python and TS/React fixture files, Groundrail can list units with correct file paths, line spans, snippet hashes, and complexity metadata.

## Phase 05: AI unit analysis pipeline

### Goal

Analyse bounded units one at a time using Kiro/AI.

### Scope

- unit-analysis prompt builder;
- source packet builder;
- configurable AI/Kiro command;
- JSON output parser;
- schema validator;
- large-unit splitter;
- analysis store;
- stale-analysis detection;
- AI notes;
- AI confidence.

### Commands

```bash
groundrail analyze-unit <unit-id>
groundrail analyze-units --changed
groundrail analyze-units --stale
groundrail analysis show <unit-id>
groundrail analysis validate --strict
```

### Artifacts

```text
.groundrail/analysis/units/<unit-id>.json
.groundrail/analysis/blocks/<unit-id>/<block-id>.json
.groundrail/audit/unit-analysis-report.json
```

### Done when

- AI analyses are source-bound and stale-detectable.
- AI cannot mark analysis as verified.
- Malformed AI output fails validation.
- Large units are split or marked partial.

## Phase 06: Human review, confirmation, and AI notes queue

### Goal

Let developers review, confirm, reject, and action important AI-inferred knowledge and AI notes.

### Scope

- review object schema;
- review store;
- confirmation writer;
- stale confirmation detector;
- AI notes store;
- review queue ranking;
- importance/severity/confidence filters.

### Commands

```bash
groundrail review list
groundrail review show <item-id>
groundrail review confirm <item-id>
groundrail review reject <item-id>
groundrail review stale
groundrail notes list
groundrail notes show <note-id>
groundrail notes confirm <note-id>
groundrail notes reject <note-id>
```

### Artifacts

```text
.groundrail/review/reviews.jsonl
.groundrail/review/confirmed-items.jsonl
.groundrail/review/rejected-items.jsonl
.groundrail/audit/stale-confirmations.json
```

### Done when

Developer confirmations are source-version-bound and become stale when source changes.

## Phase 07: Retrieval and context packs from unit analysis

### Goal

Make unit summaries and confirmed knowledge useful to Kiro.

### Scope

- retrieval index over facts, units, analyses, notes, flows;
- citation index;
- unit summary index;
- context-pack builder;
- session store;
- selection explanation;
- Kiro citation rules.

### Commands

```bash
groundrail search "user search"
groundrail prepare ask "how does user search work?"
groundrail prepare debug "why is user search returning 500?"
groundrail ctx explain latest
```

### Artifacts

```text
.groundrail/cache/retrieval-index.jsonl
.groundrail/cache/citation-index.jsonl
.groundrail/cache/unit-summary-index.jsonl
.groundrail/sessions/<id>/context-pack.md
.groundrail/sessions/<id>/context-pack.json
.groundrail/sessions/<id>/selection-explain.json
```

### Done when

Context packs clearly separate verified, dev-confirmed, inferred, stale, unsupported, and unknown information.

## Phase 08: Kiro ask and answer audit

### Goal

Run Kiro against context packs and audit answers.

### Scope

- `GROUNDRAIL_KIRO_CMD` runner;
- output capture;
- citation block parser;
- answer audit;
- unsupported-claim detection;
- strict failure modes.

### Commands

```bash
groundrail ask "how does user search work?"
groundrail audit answer latest
groundrail smart
```

### Artifacts

```text
.groundrail/sessions/<id>/kiro-output.raw.md
.groundrail/sessions/<id>/citations.json
.groundrail/sessions/<id>/audit.json
```

### Done when

Kiro must cite Groundrail IDs or mark claims as not confirmed. Strict audit fails on unsupported/stale/unknown cited support.

## Phase 09: Promotion / knowledge layer

### Goal

Allow narrow claims to graduate from deterministic or reviewed analysis into stronger facts.

### Scope

- promotion candidate finder;
- promotion validator;
- promoted fact writer;
- contradiction detector;
- promotion audit.

### Commands

```bash
groundrail promote list-candidates
groundrail promote claim <claim-id>
groundrail knowledge show <fact-id>
```

### Artifacts

```text
.groundrail/knowledge/facts.json
.groundrail/knowledge/promoted-claims.jsonl
.groundrail/audit/promotion-report.json
```

### Done when

Promotion is conservative and fails if evidence is missing, stale, broad, contradicted, or only weakly inferred.

## Phase 10: Flow and impact from units

### Goal

Compose unit references and analyses into useful flow/impact views.

### Scope

- unit graph;
- confidence-preserving composition;
- endpoint flow;
- component/hook/API flow;
- changed-file impact;
- test selection;
- coverage gaps.

### Commands

```bash
groundrail flow unit <unit-id>
groundrail flow endpoint "GET /users/search"
groundrail impact file <path>
groundrail impact unit <unit-id>
groundrail tests-for <target>
```

### Artifacts

```text
.groundrail/graph/nodes.json
.groundrail/graph/edges.json
.groundrail/flows/unit-flows.json
.groundrail/flows/endpoint-flows.json
.groundrail/impact/latest.json
.groundrail/testing/test-selection.json
```

### Done when

Flows/impact outputs preserve uncertainty and do not upgrade inferred chains into verified claims.

## Phase 11: Conductor shell and no-agent workflows

### Goal

Implement orchestration without child-agent execution first.

### Scope

- orchestration store;
- event log;
- preflight;
- planner;
- context builder;
- synthesis shell;
- debug/review/plan workflows with `--no-agent`.

### Commands

```bash
groundrail orchestrate debug "why is this happening?" --no-agent
groundrail orchestrate review --changed --no-agent
groundrail orchestrate plan "add CSV export" --no-agent
groundrail orchestrations list
groundrail synthesize latest
```

### Done when

Orchestration can create task plans and context packs without running agents.

## Phase 12: Child agents and findings validation

### Goal

Enable child agents safely.

### Scope

- agent profiles;
- child-agent context builder;
- headless Kiro runner;
- result block parser;
- result schema validator;
- verifier;
- quarantine;
- conflicts;
- synthesis.

### Commands

```bash
groundrail delegate unit-analysis <unit-id>
groundrail orchestrate review --changed
groundrail agents list
groundrail agents validate
groundrail conflicts latest
```

### Done when

Malformed or unsupported agent findings are rejected/quarantined. Agents cannot write canonical artifacts.

## Phase 13: TUI MVP

### Goal

Give the developer a daily cockpit.

### Scope

- session viewer;
- selected facts/units;
- context pack viewer;
- Kiro answer viewer;
- citation audit panel;
- unit analysis panel;
- review queue panel;
- orchestration event log.

### Commands

```bash
groundrail tui
groundrail smart
```

### Done when

The TUI reads service outputs and does not duplicate core logic.

## Phase 14: TypeScript/React extractor expansion

### Goal

Improve frontend unit detection and candidate relationships.

### Scope

- TypeScript project loader;
- tsconfig path alias support;
- import/export resolver;
- React component/hook detection;
- React Router candidates;
- TanStack Query candidates;
- API client candidates;
- adapter SDK for internal libraries.

### Done when

Frontend units can be indexed, analysed, searched, and used in context packs with clear confidence/gaps.

## Phase 15: Evaluation harness

### Goal

Prevent regression and overclaiming.

### Scope

Fixtures for:

- Python unit indexing;
- FastAPI endpoints;
- React components;
- AI unit analysis schema;
- prompt injection;
- stale summaries;
- stale developer confirmations;
- unsupported libraries;
- answer audit;
- promotion failures.

### Commands

```bash
groundrail eval run
groundrail eval add <case>
```

### Done when

Groundrail can measure false verified claims, stale support, unsupported overclaims, retrieval quality, and citation correctness.

## Phase 16: Real graph/TUI/visual flow explorer

### Goal

Add richer visualisation after stable data exists.

### Scope

- flow graph export;
- TUI graph navigation;
- source preview;
- clickable evidence;
- filters by status/review/confidence;
- optional future browser UI.

### Done when

Visualization is a view over validated artifacts, not an alternate truth source.
