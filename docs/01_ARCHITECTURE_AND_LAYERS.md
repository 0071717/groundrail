# Groundrail Architecture and Layers

## Architecture principle

Groundrail must be built as layered services, not command-handler spaghetti.

The rule is:

```text
Lower layers can exist without higher layers.
Higher layers can consume lower layers.
Higher layers cannot write truth into lower layers directly.
```

The conductor, child agents, CLI, and TUI are important product surfaces, but they must sit above the trust kernel and artifact contracts.

## Full layer model

```text
Layer 9: CLI / TUI
Layer 8: Conductor / child agents
Layer 7: Query / context packs
Layer 6: Composition / flow / impact
Layer 5: Promotion / knowledge
Layer 4: Human review and confirmation
Layer 3: AI unit analysis
Layer 2: Deterministic unit index
Layer 1: Evidence kernel
Layer 0: Source snapshot
```

## Layer 0: Source snapshot

### Purpose

Record source reality before any extraction or AI analysis.

### Inputs

- repository paths;
- include/exclude rules;
- source/test/config/generated path rules;
- Git state;
- file contents.

### Outputs

```text
.groundrail/source/snapshot.json
.groundrail/index/file-index.json
.groundrail/change/changed-files.json
.groundrail/audit/run-manifest.json
```

### Tools to build

- `ProjectConfigLoader`
- `RepoScanner`
- `GitStateReader`
- `FileScanner`
- `FileClassifier`
- `FileHasher`
- `ManifestHasher`
- `ChangeDetector`
- `RunManifestWriter`

### Commands

```bash
groundrail init
groundrail snapshot
groundrail changed
groundrail status
groundrail refresh
```

### Notes

This layer should not understand code. It only knows files, hashes, source roots, and current repo state.

## Layer 1: Evidence kernel

### Purpose

Own the trust contract.

This layer defines:

- statuses;
- confidence values;
- evidence objects;
- provenance objects;
- artifact envelopes;
- validation;
- stale checks;
- capability gaps;
- guarded writes;
- promotion gates.

### Inputs

- source snapshot;
- artifacts from lower or same layer;
- schemas;
- current file hashes;
- validation rules.

### Outputs

```text
.groundrail/audit/validation-report.json
.groundrail/audit/stale-report.json
.groundrail/gaps/capability-gaps.json
```

### Tools to build

- `ArtifactEnvelopeBuilder`
- `EvidenceBuilder`
- `ProvenanceBuilder`
- `SchemaRegistry`
- `StrictValidator`
- `StaleVerifier`
- `CapabilityGapRegistry`
- `GuardedWriter`
- `PromotionGate`

### Commands

```bash
groundrail validate --strict
groundrail verify --strict
groundrail gaps
groundrail doctor
```

### Notes

This layer must not know about FastAPI, React, Kiro, or agents. It validates shape, evidence, provenance, status, and freshness.

## Layer 2: Deterministic unit index

### Purpose

Find bounded code units that can be analysed safely.

The unit index is the deterministic foundation for AI unit analysis.

### Units

- Python functions;
- Python methods;
- Python classes;
- FastAPI endpoint handlers;
- Pydantic model classes;
- TypeScript functions;
- React components;
- React hooks;
- API client functions;
- test functions;
- route candidates;
- generated-client operation candidates.

### Inputs

- file index;
- source files;
- parser outputs;
- language configuration;
- known library adapters.

### Outputs

```text
.groundrail/index/unit-index.json
.groundrail/index/import-index.json
.groundrail/index/call-candidates.json
.groundrail/index/endpoint-candidates.json
.groundrail/index/component-index.json
.groundrail/index/hook-index.json
.groundrail/index/test-index.json
```

### Unit record fields

Each unit should include at minimum:

- `unit_id`;
- `kind`;
- `repo`;
- `file_path`;
- `symbol`;
- `span`;
- `file_hash`;
- `snippet_hash`;
- `language`;
- `extractor`;
- `imports`;
- `exports`;
- `call_candidates`;
- `related_candidates`;
- `complexity`;
- `evidence`.

### Tools to build

- `PythonUnitIndexer`
- `TypeScriptUnitIndexer`
- `ReactComponentIndexer`
- `HookIndexer`
- `FastAPIEndpointCandidateIndexer`
- `PydanticUnitIndexer`
- `ImportIndexer`
- `CallCandidateIndexer`
- `ComplexityMeasurer`
- `UnitSpanHasher`
- `CapabilityGapDetector`

### Commands

```bash
groundrail index units
groundrail unit list
groundrail unit show <unit-id>
groundrail unit code <unit-id>
groundrail unit related <unit-id>
```

### Notes

The goal is not perfect behaviour extraction. The goal is reliable unit boundaries and source evidence.

## Layer 3: AI unit analysis

### Purpose

Use AI to analyse bounded code units one at a time.

AI should infer likely behaviour, intent, inputs, outputs, side effects, state, errors, and notes from a bounded source span.

### Inputs

- unit index record;
- source span text;
- imports/call candidates;
- endpoint/route candidates;
- related tests if available;
- prompt template;
- model/tool configuration;
- previous analysis if stale/reanalysis.

### Outputs

```text
.groundrail/analysis/units/<unit-id>.json
.groundrail/analysis/blocks/<unit-id>/<block-id>.json
.groundrail/audit/unit-analysis-report.json
```

### Tools to build

- `UnitAnalysisPromptBuilder`
- `UnitAnalysisRunner`
- `UnitAnalysisSchema`
- `UnitAnalysisValidator`
- `LargeUnitSplitter`
- `BlockAnalysisRunner`
- `UnitSynthesisRunner`
- `AnalysisStaleChecker`
- `AnalysisStore`
- `PromptHashComputer`

### Commands

```bash
groundrail analyze-unit <unit-id>
groundrail analyze-units --changed
groundrail analysis show <unit-id>
groundrail analysis validate --strict
groundrail analysis stale
```

### Notes

AI unit analyses are stored as `inferred` by default. They do not become canonical truth unless a separate promotion step accepts a narrow claim.

## Layer 4: Human review and confirmation

### Purpose

Allow developers to review important AI-inferred summaries, claims, notes, uncertainties, and promoted candidates.

### Inputs

- AI unit analyses;
- AI notes;
- review queue;
- developer action;
- source hash and commit metadata.

### Outputs

```text
.groundrail/review/reviews.jsonl
.groundrail/review/confirmed-items.jsonl
.groundrail/review/rejected-items.jsonl
.groundrail/audit/stale-confirmations.json
```

### Tools to build

- `ReviewQueueBuilder`
- `ReviewStore`
- `ConfirmationWriter`
- `ReviewStatusUpdater`
- `StaleConfirmationDetector`
- `ReviewPriorityRanker`

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

### Notes

Developer confirmation is source-version-bound. If the source span changes, the confirmation must become stale.

## Layer 5: Promotion / knowledge

### Purpose

Promote narrow, evidence-supported claims into stronger knowledge artifacts.

Promotion is not the same as review confirmation.

- Confirming says: a developer agrees the inferred analysis is accurate enough for context.
- Promoting says: this specific claim can be used as stronger knowledge under strict rules.

### Inputs

- AI claims;
- deterministic facts;
- developer confirmations;
- evidence spans;
- tests/contracts/runtime evidence if available;
- promotion rules.

### Outputs

```text
.groundrail/knowledge/facts.json
.groundrail/knowledge/promoted-claims.jsonl
.groundrail/audit/promotion-report.json
```

### Tools to build

- `ClaimExtractor`
- `PromotionCandidateFinder`
- `PromotionValidator`
- `ContradictionDetector`
- `KnowledgeWriter`

### Commands

```bash
groundrail promote list-candidates
groundrail promote claim <claim-id>
groundrail promote analysis <analysis-id>
groundrail knowledge show <fact-id>
```

### Notes

Promotion should be conservative. Broad intent or business-purpose claims should usually remain inferred unless strongly supported.

## Layer 6: Composition / flow / impact

### Purpose

Compose deterministic unit references, AI unit analyses, confirmed knowledge, and promoted facts into useful flows and impact reports.

### Inputs

- unit index;
- call candidates;
- endpoint/route candidates;
- AI unit analyses;
- promoted facts;
- review confirmations;
- graph edges;
- tests;
- changed files.

### Outputs

```text
.groundrail/graph/nodes.json
.groundrail/graph/edges.json
.groundrail/flows/unit-flows.json
.groundrail/flows/endpoint-flows.json
.groundrail/impact/latest.json
.groundrail/testing/test-selection.json
```

### Tools to build

- `UnitGraphBuilder`
- `FlowComposer`
- `ImpactEngine`
- `TestSelector`
- `ContractChecker`
- `ConfidenceComposer`

### Commands

```bash
groundrail flow unit <unit-id>
groundrail flow endpoint "GET /users/search"
groundrail graph neighbors <target>
groundrail graph path <from> <to>
groundrail impact file <path>
groundrail impact unit <unit-id>
groundrail tests-for <target>
```

### Notes

Composition must preserve uncertainty. A chain with one inferred edge is not fully verified.

## Layer 7: Query / context packs

### Purpose

Build compact, cited, Kiro-ready context packs from the strongest available evidence and analyses.

### Inputs

- retrieval index;
- citation index;
- unit-summary index;
- promoted facts;
- AI unit analyses;
- review state;
- stale reports;
- flow/impact outputs;
- user question/task.

### Outputs

```text
.groundrail/cache/retrieval-index.jsonl
.groundrail/cache/citation-index.jsonl
.groundrail/cache/unit-summary-index.jsonl
.groundrail/sessions/<id>/context-pack.md
.groundrail/sessions/<id>/context-pack.json
.groundrail/sessions/<id>/selection-explain.json
.groundrail/sessions/<id>/kiro-output.raw.md
.groundrail/sessions/<id>/citations.json
.groundrail/sessions/<id>/audit.json
```

### Tools to build

- `RetrievalIndexBuilder`
- `CitationIndexBuilder`
- `UnitSummaryIndexBuilder`
- `ContextPackBuilder`
- `SessionStore`
- `KiroRunner`
- `AnswerAuditor`

### Commands

```bash
groundrail search "user search"
groundrail prepare ask "how does user search work?"
groundrail prepare debug "why is user search returning 500?"
groundrail ask "how does user search work?"
groundrail audit answer latest
groundrail ctx explain latest
```

### Notes

Context packs must separate:

- verified deterministic facts;
- developer-confirmed analyses;
- AI-inferred summaries;
- stale summaries;
- unsupported gaps;
- unconfirmed claims.

## Layer 8: Conductor / child agents

### Purpose

Coordinate multi-step workflows and child agents around Groundrail evidence.

### Inputs

- user task;
- source/analysis freshness;
- retrieval and context services;
- Kiro command configuration;
- agent profiles;
- orchestration plan.

### Outputs

```text
.groundrail/orchestrations/<id>/orchestration.json
.groundrail/orchestrations/<id>/events.jsonl
.groundrail/orchestrations/<id>/plan.json
.groundrail/orchestrations/<id>/tasks/<task-id>/context-pack.md
.groundrail/orchestrations/<id>/tasks/<task-id>/result.json
.groundrail/orchestrations/<id>/tasks/<task-id>/audit.json
.groundrail/orchestrations/<id>/summary.md
.groundrail/agents/findings/*.json
.groundrail/agents/quarantine/*.json
```

### Tools to build

- `OrchestrationStore`
- `EventLog`
- `Preflight`
- `Planner`
- `TaskContextBuilder`
- `ChildAgentRunner`
- `AgentResultValidator`
- `AgentResultVerifier`
- `Synthesizer`
- `ConflictDetector`
- `LockTable`
- `WorktreeManager`

### Commands

```bash
groundrail orchestrate debug "why is this happening?"
groundrail orchestrate review --changed
groundrail orchestrate plan "add CSV export"
groundrail delegate unit-analysis <unit-id>
groundrail agents list
groundrail synthesize latest
groundrail conflicts latest
```

### Notes

Child agents may produce findings and analyses. They must not write canonical facts directly.

## Layer 9: CLI / TUI

### Purpose

Make Groundrail usable every day.

### CLI tools

- command parser;
- JSON and human output modes;
- stable command contracts;
- strict failure modes;
- shell-friendly output.

### TUI tools

- dashboard;
- session viewer;
- source preview;
- citation viewer;
- unit browser;
- analysis viewer;
- AI notes/review queue;
- orchestration progress;
- flow/impact browser.

### Commands

```bash
groundrail tui
groundrail smart
```

### Notes

The TUI is a view/controller over lower-layer services. It must not duplicate validation, retrieval, impact, or orchestration logic.
