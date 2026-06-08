# CodeAtlas Reuse Plan

Groundrail should treat CodeAtlas as the donor/research repository, not as a codebase to copy wholesale.

CodeAtlas contains useful ideas and partially implemented systems, but it also reflects years of changing vision, experiments, legacy paths, and overlapping concerns. Groundrail should port selected concepts behind stricter layers and contracts.

## Reuse principle

```text
Reuse the proven/productive concepts.
Port selected modules only after their contracts are rewritten for Groundrail.
Do not import the sprawl.
```

## What to reuse from CodeAtlas

## 1. CLI command grammar and workflow surface

### What exists in CodeAtlas

CodeAtlas/ngk already has command groups for:

```text
atlas index
sources
fact show/yaml/code
drift
impact
review
contract
eval
test-select
test-plan
trace
graph neighbors/path
ctx build/explain
ask
verify-answer
smart
orchestrations
tool
agents
hooks
delegate
orchestrate
critic
synthesize
conflicts
locks
worktrees
```

### Why reuse it

The command grammar maps closely to the desired Groundrail user experience. It already captures the developer workflow around evidence lookup, Kiro context, impact, review, orchestration, and smart terminal output.

### How to adapt it

Rename and simplify:

```text
ngk atlas index        -> groundrail index
ngk sources            -> groundrail search
ngk fact show/code     -> groundrail fact show/code
ngk trace              -> groundrail flow
ngk impact             -> groundrail impact
ngk ctx build          -> groundrail prepare
ngk ask                -> groundrail ask
ngk verify-answer      -> groundrail audit answer
ngk smart              -> groundrail smart / groundrail tui
ngk orchestrate review -> groundrail orchestrate review
```

### Caution

Do not port command handlers as the architecture. Groundrail should implement services first, then expose them through CLI/TUI.

## 2. Citation and source evidence display

### What exists in CodeAtlas

CodeAtlas has commands that:

- resolve a fact by ID;
- show claim/confidence/source pointer;
- collect source evidence;
- attach source span data;
- print related traces/tests;
- print source code lines for evidence-backed facts.

### Why reuse it

This directly supports Groundrail's goal: users must be able to jump from a summary or claim to source evidence quickly.

### Groundrail adaptation

Extend citation display beyond facts:

```bash
groundrail fact show <fact-id>
groundrail fact code <fact-id>
groundrail unit show <unit-id>
groundrail unit code <unit-id>
groundrail analysis show <analysis-id>
groundrail evidence show <evidence-id>
groundrail note show <note-id>
```

### Required changes

- Replace Atlas-specific pointers with Groundrail artifact paths.
- Support unit IDs and analysis IDs, not just fact IDs.
- Show review status and stale status.
- Show dev-confirmed vs AI-inferred state.
- Include AI notes and uncertainties where relevant.

## 3. Context-pack builder

### What exists in CodeAtlas

CodeAtlas has a context-pack builder that:

- selects relevant facts;
- selects related traces;
- includes drift status;
- includes related tests;
- records known gaps;
- writes Markdown and JSON context packs;
- writes selected facts/traces;
- writes selection explanation;
- requires a citation block in Kiro output.

### Why reuse it

This is one of the most important CodeAtlas pieces. Groundrail's immediate value is producing compact, cited Kiro context packs.

### Groundrail adaptation

The context pack should include:

- selected promoted facts;
- selected developer-confirmed unit analyses;
- selected AI-inferred unit analyses;
- selected AI notes;
- selected source evidence;
- selected flows/impact if available;
- stale warnings;
- unsupported gaps;
- files Kiro should inspect first;
- required `groundrail_citations` output contract.

### Required context-pack sections

```text
User task
Freshness / stale status
Verified deterministic facts
Developer-confirmed behaviour
AI-inferred unit summaries
Relevant AI notes
Known uncertainties
Unsupported gaps
Source evidence
Related tests
Files to inspect first
Citation rules
Required output schema
```

### Caution

Kiro should not read the entire Groundrail knowledge store. It should receive compact task-shaped context packs.

## 4. Kiro wrapper

### What exists in CodeAtlas

CodeAtlas uses an environment variable command template to run Kiro with a context pack and then stores:

```text
kiro-output.raw.md
kiro-output.parsed.json
citations.json
audit.json
```

### Why reuse it

The user's target environment has `kiro-cli` available. Groundrail should be able to call it without MCP or cloud integrations.

### Groundrail adaptation

Use:

```bash
export GROUNDRAIL_KIRO_CMD='kiro-cli --prompt-file {context_pack}'
```

or stdin mode:

```bash
export GROUNDRAIL_KIRO_CMD='kiro-cli'
```

Commands:

```bash
groundrail ask "how does user search work?"
groundrail orchestrate debug "why is user search returning 500?"
```

### Caution

Kiro output must be audited. It should not silently become Groundrail knowledge.

## 5. Answer audit and citation verification

### What exists in CodeAtlas

CodeAtlas planned/implemented answer-audit concepts:

- parse AI citation block;
- check cited fact IDs exist;
- check cited facts have evidence;
- check facts are fresh;
- surface unsupported claims;
- fail strict mode when unsupported claims exist.

### Why reuse it

With AI unit summaries, answer audit becomes even more important.

### Groundrail adaptation

Audit should validate references to:

- `fact_ids`;
- `unit_ids`;
- `analysis_ids`;
- `evidence_ids`;
- `note_ids`.

Audit should check:

- cited IDs exist;
- cited items are fresh;
- inferred analysis is not presented as verified;
- stale summaries are not used as support;
- dev-confirmed items have fresh confirmations;
- unsupported claims are labelled `Not confirmed by Groundrail`;
- Kiro did not cite summary prose when structured evidence was available.

## 6. Orchestrator / conductor architecture

### What exists in CodeAtlas

CodeAtlas has an established orchestrator design with:

- orchestration store;
- event log;
- preflight;
- planner;
- context builder;
- headless Kiro runner;
- agent profiles;
- result verifier;
- synthesizer;
- conflict detector;
- lock table;
- worktree manager;
- Kiro hooks;
- delegate/orchestrate commands.

### Why reuse it

The user explicitly wants orchestration and child agents. CodeAtlas already explored this design space.

### Groundrail adaptation

Groundrail conductor should coordinate:

```text
preflight
  -> check source/index/analysis freshness
  -> identify stale/missing unit analyses
  -> build plan
  -> optionally run child agents
  -> validate child outputs
  -> synthesize findings
  -> build final context/answer/review output
```

### First conductor workflows

```bash
groundrail orchestrate debug "why is user search returning 500?"
groundrail orchestrate review --changed
groundrail orchestrate plan "add CSV export"
groundrail delegate unit-analysis <unit-id>
groundrail synthesize latest
groundrail conflicts latest
```

### Caution

The conductor writes only to:

```text
.groundrail/orchestrations/
.groundrail/agents/findings/
.groundrail/agents/quarantine/
```

It does not write canonical facts or indexes directly.

## 7. Structured child-agent result contract

### What exists in CodeAtlas

CodeAtlas validates structured agent result blocks with required fields such as:

- schema version;
- task ID;
- agent profile;
- status;
- verdict;
- confidence;
- summary;
- findings;
- uncertainties;
- not confirmed;
- requested followups.

Findings must include support state, confidence, fact IDs, evidence, tests, and risk tags.

### Why reuse it

This protects Groundrail from free-form child-agent output.

### Groundrail adaptation

Use:

```text
<groundrail_agent_result>
...
</groundrail_agent_result>
```

Add references for:

- `unit_ids`;
- `analysis_ids`;
- `evidence_ids`;
- `note_ids`;
- `claim_ids`.

### Caution

Supported findings must cite fact/evidence. Inferred findings must include reasons and uncertainty. Unsupported findings must stay in findings/quarantine.

## 8. Smart terminal / TUI concept

### What exists in CodeAtlas

CodeAtlas has a `smart` MVP that shows session output and citation IDs, and a richer design for a smart terminal cockpit with panels for:

- Kiro answer;
- audit status;
- sources;
- source preview;
- code evidence;
- impact graph;
- affected tests;
- drift warnings;
- contract warnings;
- session history;
- service status.

### Why reuse it

The CLI/TUI is central to the user's workflow.

### Groundrail adaptation

Groundrail TUI should add panels for:

- unit browser;
- unit analysis summary;
- AI notes;
- review queue;
- dev confirmations;
- stale confirmations;
- orchestration event log;
- Kiro session viewer;
- citation audit;
- source preview;
- impact/flow.

### Caution

The TUI must not duplicate retrieval, validation, or impact logic.

## 9. Eval / adversarial fixtures

### What exists in CodeAtlas

CodeAtlas includes eval concepts around:

- missing citations;
- nonexistent facts;
- not-confirmed claims;
- contradictions;
- overconfidence;
- prompt injection;
- stale evidence;
- malformed JSON;
- nested orchestration;
- read-only/write boundaries.

### Why reuse it

Groundrail's AI unit-analysis approach increases the need for evals.

### Groundrail adaptation

Add eval cases for:

- AI summary overclaims;
- AI ignores source boundary;
- AI follows prompt injection in comments;
- stale unit summary used as support;
- dev-confirmed summary becomes stale;
- huge component incorrectly marked medium/high confidence;
- AI note lacks evidence lines;
- promoted claim lacks deterministic support;
- Kiro cites inferred analysis as verified.

## What not to reuse directly

## 1. SQLite as a required read model

CodeAtlas uses SQLite for a local cache. Groundrail should not require SQLite for core correctness.

Use JSONL indexes first:

```text
.groundrail/cache/retrieval-index.jsonl
.groundrail/cache/citation-index.jsonl
.groundrail/cache/unit-summary-index.jsonl
.groundrail/cache/source-cards.jsonl
```

SQLite can be added later as an optional performance cache if necessary.

## 2. Legacy prompt-first extraction

Do not import legacy prompt-first extraction paths as canonical behaviour.

AI analysis is allowed, but only after deterministic unit boundaries exist.

## 3. Old Atlas artifact sprawl

Do not copy every CodeAtlas directory and artifact type.

Groundrail should start with a smaller artifact set and add layers only when the contract is enforced.

## 4. Regex React extraction as verified truth

Regex or heuristic frontend extraction may produce candidates or inferred summaries, but not verified claims.

## 5. Agents writing canonical artifacts

Do not reuse any pattern where agents or Kiro can directly create facts/indexes.

Agents produce:

```text
findings
analyses
notes
quarantine items
promotion candidates
```

The kernel/promotion gate decides what becomes knowledge.

## Migration strategy from CodeAtlas

### Phase 1: Documentation and contracts

Already captured in Groundrail docs.

### Phase 2: Port CLI shape

Port command grammar, but implement handlers against Groundrail services.

### Phase 3: Port context/citation/session concepts

Adapt CodeAtlas context packs to include unit analyses, review states, and AI notes.

### Phase 4: Port conductor shell

Bring orchestration store, event log, planner, result validator, synthesizer concepts.

### Phase 5: Port/adapt extractors carefully

Only port extractor logic after Groundrail unit-index contract exists.

### Phase 6: Port smart/TUI concept

Start with session viewer, then build a proper TUI over stable services.

## Final reuse rule

If a CodeAtlas component does not clearly fit one Groundrail layer and one contract, do not port it yet.
