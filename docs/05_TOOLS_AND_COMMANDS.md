# Groundrail Tools and Commands

This document lists the tools required to build each Groundrail layer and the command contracts future implementation should expose.

## Command design principles

1. Every command should support `--json` when useful.
2. Every command that uses source-backed artifacts should check freshness or clearly warn when stale.
3. Every command that produces artifacts should write a run manifest event.
4. Every command should have a stable input/output contract.
5. CLI output should be human-friendly; JSON output should be machine-friendly.
6. TUI should call the same services as CLI commands.

## Top-level command groups

```text
groundrail init
groundrail refresh
groundrail snapshot
groundrail validate
groundrail verify
groundrail changed
groundrail gaps

groundrail index units
groundrail unit list/show/code/related

groundrail analyze-unit
groundrail analyze-units
groundrail analysis show/validate/stale/report

groundrail review list/show/confirm/reject/stale
groundrail notes list/show/confirm/reject/export

groundrail promote list-candidates/claim/analysis

groundrail search
groundrail fact show/code
groundrail evidence show
groundrail prepare
groundrail ask
groundrail audit answer
groundrail ctx explain

groundrail flow unit/endpoint
groundrail graph neighbors/path
groundrail impact file/unit/endpoint
groundrail tests-for

groundrail orchestrate debug/review/plan
groundrail delegate
groundrail agents list/show/validate
groundrail synthesize
groundrail conflicts

groundrail smart
groundrail tui
```

## Source tools

### `groundrail init`

Creates `.groundrail/` structure and starter config.

Inputs:

- current working directory;
- optional config path.

Outputs:

```text
.groundrail/config.json
.groundrail/source/
.groundrail/index/
.groundrail/cache/
.groundrail/sessions/
.groundrail/orchestrations/
.groundrail/audit/
```

Failure cases:

- cannot write `.groundrail`;
- invalid existing config.

### `groundrail snapshot`

Scans configured repositories and records current source state.

Inputs:

- config;
- repository roots;
- ignore rules;
- current Git state;
- file contents.

Outputs:

```text
.groundrail/source/snapshot.json
.groundrail/index/file-index.json
.groundrail/audit/run-manifest.json
```

Strict behaviour:

- fail if configured repo is missing;
- fail if file cannot be read unless explicitly ignored;
- warn or fail on dirty worktree depending policy.

### `groundrail changed`

Compares current files to last snapshot.

Outputs:

```text
.groundrail/change/changed-files.json
```

## Evidence kernel tools

### `groundrail validate --strict`

Validates artifacts.

Checks:

- artifact envelope shape;
- required fields;
- allowed status/confidence/review status;
- evidence objects;
- analysis schema;
- review schema;
- promoted fact schema;
- graph reference integrity;
- context-pack citation references.

Outputs:

```text
.groundrail/audit/validation-report.json
```

### `groundrail verify --strict`

Verifies source freshness.

Checks:

- file hashes;
- snippet hashes;
- unit span existence;
- AI analysis source hash;
- developer confirmation source hash;
- promoted fact evidence freshness.

Outputs:

```text
.groundrail/audit/stale-report.json
```

### `groundrail gaps`

Shows unsupported or missing capabilities.

Examples:

- TypeScript route factory detected but unsupported;
- internal API client wrapper detected but no adapter;
- huge component cannot be analysed in one pass;
- generated client not mapped to OpenAPI;
- dynamic FastAPI route cannot be resolved.

Outputs:

```text
.groundrail/gaps/capability-gaps.json
```

## Unit index tools

### `groundrail index units`

Builds deterministic unit index.

Inputs:

- file index;
- source files;
- parser adapters;
- language config.

Outputs:

```text
.groundrail/index/unit-index.json
.groundrail/index/import-index.json
.groundrail/index/call-candidates.json
.groundrail/index/endpoint-candidates.json
.groundrail/index/component-index.json
.groundrail/index/hook-index.json
.groundrail/index/test-index.json
```

Implementation phases:

1. Python function/class boundaries.
2. FastAPI endpoint candidate detection.
3. Pydantic model units.
4. TypeScript function/component/hook boundaries.
5. React route/API/query candidates.

Strict behaviour:

- fail on malformed parser output;
- mark unsupported patterns as gaps;
- never silently skip a detectable unsupported framework pattern.

### `groundrail unit list`

Lists units, filterable by kind, path, repo, stale state, complexity.

Examples:

```bash
groundrail unit list --kind react_component
groundrail unit list --path src/features/users
groundrail unit list --complexity complex
```

### `groundrail unit show <unit-id>`

Shows unit metadata, source span, complexity, candidates, analysis state, review state.

### `groundrail unit code <unit-id>`

Prints line-addressable source span.

### `groundrail unit related <unit-id>`

Shows related candidate calls, imports, tests, endpoint/route candidates, analyses, notes, and flows.

## AI analysis tools

### `groundrail analyze-unit <unit-id>`

Runs AI analysis on one unit.

Inputs:

- unit record;
- source span text;
- imports/call candidates;
- related tests;
- known gaps;
- unit-analysis prompt template;
- Kiro/model command config.

Outputs:

```text
.groundrail/analysis/units/<unit-id>.json
```

Failure cases:

- missing unit;
- stale unit index;
- source span missing;
- Kiro command not configured;
- invalid AI JSON;
- AI output missing required fields;
- prompt-injection policy violation detected;
- model output too large or malformed.

### `groundrail analyze-units --changed`

Analyses changed or stale units only.

Options:

```bash
--changed
--stale
--important
--kind python_function
--kind react_component
--limit 50
--dry-run
```

Outputs:

```text
.groundrail/audit/unit-analysis-report.json
```

### `groundrail analysis show <unit-id>`

Shows latest analysis for a unit.

### `groundrail analysis stale`

Lists stale analyses.

### `groundrail analysis validate --strict`

Validates all AI analyses.

Checks:

- schema;
- source hash match;
- no illegal `verified` state from AI;
- evidence line references within unit span;
- allowed note types;
- confidence bounds;
- required uncertainties for complex/partial units.

## Review and note tools

### `groundrail review list`

Shows review queue.

Options:

```bash
--important
--stale
--type potential_bug
--unit <unit-id>
--confidence low
--review-status unreviewed
```

### `groundrail review show <item-id>`

Shows a reviewable item with source evidence.

### `groundrail review confirm <item-id>`

Adds developer confirmation.

Required fields:

- reviewer ID; default from environment/user config;
- source commit;
- file hash;
- snippet hash;
- scope;
- optional notes.

### `groundrail review reject <item-id>`

Marks item rejected and records reviewer notes.

### `groundrail notes list/show/confirm/reject/export`

Manages AI notes.

Export targets later:

- Markdown report;
- JSONL;
- GitHub issue drafts;
- PR review summary.

## Promotion tools

### `groundrail promote list-candidates`

Lists specific claims eligible for promotion.

Candidate sources:

- deterministic facts;
- developer-confirmed AI claims;
- AI claims with strong source evidence;
- tests/contracts/runtime evidence later.

### `groundrail promote claim <claim-id>`

Promotes one claim if validation passes.

Strict checks:

- claim has source evidence;
- claim is narrow;
- evidence is fresh;
- no contradiction;
- required support type is satisfied;
- review/promotion policy allows promotion.

Outputs:

```text
.groundrail/knowledge/facts.json
.groundrail/audit/promotion-report.json
```

## Query and context tools

### `groundrail search <query>`

Searches retrieval index over facts, units, analyses, notes, flows, tests.

### `groundrail fact show/code`

Shows promoted facts and source code.

### `groundrail evidence show <evidence-id>`

Shows evidence object and source preview.

### `groundrail prepare <mode> <request>`

Builds context pack without running Kiro.

Modes:

```text
ask
debug
review
plan
implement
```

Outputs:

```text
.groundrail/sessions/<id>/context-pack.md
.groundrail/sessions/<id>/context-pack.json
.groundrail/sessions/<id>/selection-explain.json
```

### `groundrail ask <question>`

Builds context pack and optionally runs Kiro.

Configuration:

```bash
export GROUNDRAIL_KIRO_CMD='kiro-cli --prompt-file {context_pack}'
```

Outputs:

```text
.groundrail/sessions/<id>/kiro-output.raw.md
.groundrail/sessions/<id>/citations.json
.groundrail/sessions/<id>/audit.json
```

### `groundrail audit answer latest`

Audits Kiro output.

Checks:

- citation block present;
- cited IDs exist;
- cited items fresh;
- inferred items not overclaimed;
- stale items not used as support;
- unsupported claims marked;
- malformed citation JSON.

## Flow and impact tools

### `groundrail flow unit <unit-id>`

Shows known/inferred flow around a unit.

### `groundrail flow endpoint "GET /path"`

Shows endpoint flow if available.

### `groundrail impact file <path>`

Shows possible impact of file change.

Impact categories:

- high-confidence deterministic links;
- developer-confirmed links;
- AI-inferred links;
- partial links;
- unsupported gaps;
- likely tests.

### `groundrail tests-for <target>`

Suggests related tests and coverage gaps.

## Conductor tools

### `groundrail orchestrate debug <issue>`

Debug workflow:

```text
preflight
  -> search relevant units/facts/analyses
  -> find stale/missing analyses
  -> optionally analyse units
  -> build debug context pack
  -> optionally run Kiro
  -> audit answer
  -> synthesize summary
```

### `groundrail orchestrate review --changed`

Review workflow:

```text
changed files
  -> impacted units
  -> stale analyses
  -> analysis updates
  -> impact/test plan
  -> child-agent findings
  -> synthesis
```

### `groundrail orchestrate plan <feature>`

Feature planning workflow:

```text
search similar units/features
  -> selected context
  -> likely files to change
  -> risks/gaps/tests
  -> implementation plan context for Kiro
```

### `groundrail delegate <profile>`

Runs a child-agent profile or creates its context pack.

Profiles to support later:

```text
unit-analysis
backend-impact
frontend-impact
api-contract
data-impact
test-gaps
security
synthesis
critic
```

## TUI tools

### `groundrail smart`

MVP terminal session viewer.

Shows:

- latest context pack;
- Kiro output;
- citation audit;
- selected facts/units;
- stale warnings.

### `groundrail tui`

Future interactive TUI.

Panels:

- dashboard;
- sessions;
- unit browser;
- analysis viewer;
- source preview;
- AI notes;
- review queue;
- orchestrations;
- impact/flow;
- gaps/stale reports.

## Service interfaces to implement

Avoid direct command logic. Implement service classes:

```text
Workspace
ArtifactStore
GuardedWriter
SourceSnapshotter
FileIndex
UnitIndex
AnalysisStore
ReviewStore
KnowledgeStore
RetrievalIndex
CitationIndex
ContextPackBuilder
KiroRunner
AnswerAuditor
FlowComposer
ImpactEngine
TestSelector
OrchestrationStore
EventLog
Planner
AgentRunner
ResultVerifier
Synthesizer
SmartViewModelBuilder
```

Commands should call these services.
