# Groundrail Implementation Handoff

This document is for the person or agent who will review and implement Groundrail.

Do not treat this repo as an implementation request yet. Treat it as an architecture/specification package that must be reviewed before code is added.

## Product objective

Build Groundrail as a local evidence and context-routing framework that makes Kiro CLI more accurate and efficient on large codebases.

The central workflow is:

```text
user asks question / wants bug fix / wants feature plan
  -> Groundrail finds relevant units, analyses, facts, notes, gaps, stale state
  -> Groundrail builds compact cited context pack
  -> Kiro answers or proposes changes using that pack
  -> Groundrail audits citations and unsupported claims
  -> conductor/TUI help developer review and iterate
```

## Architecture summary

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

Implement from the bottom up.

## First implementation target

The first useful implementation target is not full extraction. It is the framework skeleton and context workflow.

### Minimum skeleton

Implement:

```text
Python package
CLI parser
Workspace layout
Artifact envelope model
Evidence/provenance model
JSON/JSONL stores
Basic validator
Seed retrieval/citation data
Context-pack builder
Kiro command wrapper
Session store
Smart MVP session viewer
Conductor shell with no-agent workflows
Tests
```

### Do not implement yet

- full Python/FastAPI extractor;
- TypeScript/React extractor;
- child-agent execution;
- graph visualiser;
- TUI beyond a simple MVP;
- promotion logic;
- business-rule extraction;
- SQLite.

## Recommended repository structure

```text
groundrail/
  README.md
  AGENTS.md
  pyproject.toml
  docs/
  src/
    groundrail/
      cli/
      core/
      source/
      units/
      analysis/
      review/
      knowledge/
      graph/
      impact/
      context/
      conductor/
      tui/
      evals/
  tests/
    groundrail/
      unit/
      integration/
      fixtures/
```

If starting smaller, a flat module layout is acceptable, but maintain service boundaries.

## Required services

Implement these as services before wiring complex commands.

### Core services

```text
Workspace
ArtifactStore
GuardedWriter
SchemaRegistry
EvidenceBuilder
ProvenanceBuilder
RunManifestWriter
StrictValidator
StaleVerifier
CapabilityGapRegistry
```

### Source services

```text
ProjectConfigLoader
RepoScanner
GitStateReader
FileScanner
FileClassifier
FileHasher
ChangeDetector
```

### Unit services

```text
UnitIndexBuilder
UnitStore
UnitCodeReader
UnitComplexityMeasurer
ImportIndexer
CallCandidateIndexer
```

### AI analysis services

```text
UnitAnalysisPromptBuilder
UnitAnalysisRunner
UnitAnalysisParser
UnitAnalysisValidator
LargeUnitSplitter
AnalysisStore
AnalysisStaleChecker
```

### Review services

```text
ReviewQueueBuilder
ReviewStore
ConfirmationWriter
StaleConfirmationDetector
AINoteStore
ReviewPriorityRanker
```

### Knowledge/promotion services

```text
ClaimExtractor
PromotionCandidateFinder
PromotionValidator
KnowledgeStore
ContradictionDetector
```

### Context services

```text
RetrievalIndexBuilder
CitationIndexBuilder
UnitSummaryIndexBuilder
ContextPackBuilder
SessionStore
KiroRunner
AnswerAuditor
```

### Conductor services

```text
OrchestrationStore
EventLog
Preflight
Planner
TaskContextBuilder
ChildAgentRunner
AgentResultParser
AgentResultValidator
AgentResultVerifier
Synthesizer
ConflictDetector
```

### TUI services

```text
SmartViewModelBuilder
SessionViewModel
UnitViewModel
AnalysisViewModel
ReviewQueueViewModel
OrchestrationViewModel
```

## First commands to implement

Implement in this order.

### 1. `groundrail init`

Creates `.groundrail` layout and optional seed/example data.

### 2. `groundrail validate`

Validates JSON parseability and basic envelope/schema rules.

### 3. `groundrail search`

Searches retrieval index JSONL.

### 4. `groundrail fact show/code`

Shows a fact and source evidence.

### 5. `groundrail prepare`

Builds a context pack from retrieval/citation/unit-summary stores.

### 6. `groundrail ask`

Builds context pack and optionally calls `GROUNDRAIL_KIRO_CMD`.

### 7. `groundrail audit answer`

Parses and audits `<groundrail_citations>`.

### 8. `groundrail smart`

Prints latest session output, context, citations, and audit.

### 9. `groundrail orchestrate debug/review/plan --no-agent`

Creates orchestration, plan, and context pack without running child agents.

## Unit-analysis implementation plan

After skeleton:

### Step 1: Python unit index

Use Python AST to index:

- functions;
- async functions;
- methods;
- classes;
- line spans;
- imports;
- obvious call candidates;
- complexity.

### Step 2: Unit code view

Implement:

```bash
groundrail unit show <unit-id>
groundrail unit code <unit-id>
```

### Step 3: AI unit prompt

Build a prompt packet containing:

- unit metadata;
- source span;
- imports;
- call candidates;
- related units/tests;
- known gaps;
- strict output schema;
- prompt-injection boundary.

### Step 4: AI unit analysis runner

Use configurable command:

```bash
export GROUNDRAIL_AI_CMD='kiro-cli'
```

or reuse `GROUNDRAIL_KIRO_CMD` if one command handles both context and analysis.

### Step 5: Validate and store

Reject malformed JSON. Store valid output under:

```text
.groundrail/analysis/units/<unit-id>.json
```

### Step 6: Search and context integration

Index analyses into:

```text
.groundrail/cache/unit-summary-index.jsonl
.groundrail/cache/retrieval-index.jsonl
```

Context packs should then prefer:

1. verified deterministic facts;
2. fresh dev-confirmed analyses;
3. fresh AI-inferred analyses;
4. partial/low-confidence analyses;
5. stale items only as warnings.

## CodeAtlas reuse implementation plan

### Reuse first

1. CLI command grammar.
2. Context-pack structure.
3. Citation display and `fact code` behaviour.
4. Kiro command wrapper.
5. Answer audit concept.
6. Conductor shell concepts.
7. Structured child-agent result validation.
8. Smart terminal concept.

### Do not reuse first

1. SQLite cache.
2. Legacy prompt-first extraction.
3. Old Atlas path sprawl.
4. Agents writing canonical artifacts.
5. Regex frontend relationships as verified claims.

### Adaptation requirement

Any CodeAtlas-derived component must be mapped to one Groundrail layer and one artifact contract before being ported.

## Required tests

### Core tests

- status/confidence/review enum validation;
- artifact envelope validation;
- evidence validation;
- stale hash detection;
- missing artifact envelope failure;
- malformed JSON failure.

### Unit index tests

- Python function spans;
- Python class spans;
- nested functions;
- decorators;
- import extraction;
- call candidate extraction;
- stable unit IDs;
- complexity metrics.

### AI analysis tests

- valid analysis accepted;
- missing required fields rejected;
- `state: verified` from AI rejected;
- evidence lines outside unit span rejected;
- stale source hash detected;
- huge unit marked partial;
- prompt-injection fixture handled.

### Human review tests

- confirm item;
- reject item;
- stale confirmation after source change;
- review queue prioritisation;
- note filtering.

### Context/audit tests

- context pack includes selected unit analyses;
- stale items excluded from support;
- citation block parsed;
- unknown cited ID fails audit;
- inferred item overclaimed as verified fails audit;
- `Not confirmed by Groundrail` accepted for unsupported claim.

### Conductor tests

- orchestration created;
- event log written;
- no-agent plan created;
- child-agent malformed result rejected;
- unsupported finding quarantined;
- synthesis preserves uncertainty.

## Strict mode policy

Strict mode should be available for:

```bash
groundrail validate --strict
groundrail verify --strict
groundrail analysis validate --strict
groundrail audit answer latest --strict
groundrail orchestrate review --strict
```

Strict mode should fail closed on:

- malformed artifacts;
- stale source evidence;
- stale developer confirmations used as support;
- AI analyses with invalid schema;
- AI analyses claiming verified;
- unsupported Kiro claims;
- missing citation block;
- child-agent supported findings without evidence;
- promoted claims without evidence.

## TUI implementation guidance

TUI should not be implemented until service APIs are stable.

When implemented, TUI screens should include:

```text
Dashboard
Latest session
Context pack viewer
Kiro answer viewer
Citation/audit panel
Unit browser
Source preview
AI analysis viewer
AI notes list
Review queue
Stale confirmations
Orchestration timeline
Impact/flow browser
Capability gaps
```

The first TUI can be a simple textual view, but it must read service outputs and not duplicate business logic.

## Biggest review questions before implementation

Reviewers should explicitly decide:

1. Should Groundrail use `.groundrail/` as the only generated directory?
2. Should AI analysis use Kiro CLI directly or a configurable generic AI command?
3. What is the minimum accepted unit index for v0.1?
4. Which CodeAtlas modules are safe to port first?
5. Should TypeScript/React extractor live inside Groundrail initially or become a separate repo later?
6. What user identity should developer confirmations use in local-only environments?
7. What is the first strict schema set?
8. How should secrets be redacted from context packs?
9. What should be included in the first eval fixtures?
10. What TUI toolkit, if any, should be used later?

## Final implementation warning

The project should not implement all layers at once.

The correct path is:

```text
contracts -> validators -> stores -> CLI shell -> unit index -> AI unit analysis -> review/confirmation -> context packs -> audit -> conductor -> flow/impact -> TUI
```

If implementation jumps straight to orchestration, TUI, or graph visualisation without the contracts and stale checks, Groundrail will repeat CodeAtlas's sprawl.
