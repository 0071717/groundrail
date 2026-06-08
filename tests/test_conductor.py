"""Conductor tests: orchestration store, agent result validation, workflows, and CLI."""

from __future__ import annotations

import json
import textwrap

import pytest

from groundrail.cli.main import main
from groundrail.conductor.agent import (
    RESULT_TAG,
    extract_result_block,
    parse_agent_result,
    validate_agent_result,
    ChildAgentRunner,
)
from groundrail.conductor.store import OrchestrationStore
from groundrail.conductor.synthesize import synthesize
from groundrail.conductor.workflows import OrchestratorWorkflow


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _valid_result(task_id: str = "task-abc", **overrides) -> dict:
    base = {
        "task_id": task_id,
        "agent_profile": "test-agent",
        "status": "completed",
        "verdict": "no_issues",
        "confidence": "medium",
        "summary": "Everything looks fine.",
        "findings": [],
        "uncertainties": [],
        "not_confirmed": [],
        "requested_followups": [],
    }
    base.update(overrides)
    return base


def _wrap(obj: dict) -> str:
    return f"<{RESULT_TAG}>{json.dumps(obj)}</{RESULT_TAG}>"


def _run_fn(raw: str):
    """Minimal agent run_fn that just echoes the raw text."""
    return raw


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

def test_orchestration_create_and_list(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "why is login broken")
    plans = store.list_all()
    assert len(plans) == 1
    assert plans[0]["orchestration_id"] == oid
    assert plans[0]["workflow"] == "debug"
    assert plans[0]["request"] == "why is login broken"


def test_orchestration_event_log_appended(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("review", "check payments module")
    store.log_event(oid, "preflight", {"ok": True})
    store.log_event(oid, "context_packed", {"units_selected": 3})
    events = store.get_events(oid)
    # created event + 2 explicit events
    assert len(events) == 3
    event_types = [e["event"] for e in events]
    assert "created" in event_types
    assert "preflight" in event_types
    assert "context_packed" in event_types


def test_orchestration_update_status(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("plan", "implement search feature")
    store.update_status(oid, "completed")
    plan = store.get_plan(oid)
    assert plan["status"] == "completed"


def test_finding_stored_and_retrieved(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "test")
    finding = _valid_result("task-1")
    store.write_finding(oid, "task-1", finding)
    findings = store.list_findings(oid)
    assert len(findings) == 1
    assert findings[0]["task_id"] == "task-1"


def test_quarantine_stores_reason_and_excerpt(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "test")
    store.quarantine_result(oid, "task-bad", "missing result block", "raw output here")
    q = store.list_quarantine(oid)
    assert len(q) == 1
    assert q[0]["reason"] == "missing result block"
    assert "raw_excerpt" in q[0]


def test_latest_id_returns_most_recent(workspace):
    store = OrchestrationStore(workspace)
    store.create("debug", "first")
    oid2 = store.create("plan", "second")
    # list_all sorts newest first
    assert store.latest_id() == oid2


# ---------------------------------------------------------------------------
# agent result parsing and validation
# ---------------------------------------------------------------------------

def test_extract_result_block():
    obj = _valid_result()
    raw = f"Some preamble.\n{_wrap(obj)}\nSome postamble."
    block = extract_result_block(raw)
    assert block is not None
    parsed = json.loads(block)
    assert parsed["task_id"] == "task-abc"


def test_extract_result_block_missing_returns_none():
    assert extract_result_block("no tags here") is None


def test_parse_agent_result_valid():
    obj = _valid_result()
    result, errors = parse_agent_result(_wrap(obj))
    assert not errors
    assert result is not None
    assert result["verdict"] == "no_issues"


def test_parse_agent_result_missing_block():
    _, errors = parse_agent_result("no block here")
    assert errors
    assert "missing" in errors[0].lower()


def test_parse_agent_result_malformed_json():
    raw = f"<{RESULT_TAG}>{{bad json</{RESULT_TAG}>"
    _, errors = parse_agent_result(raw)
    assert errors
    assert "malformed" in errors[0].lower()


def test_validate_rejects_verified_state():
    obj = _valid_result(state="verified")
    errors = validate_agent_result(obj)
    assert any("verified" in e for e in errors)


def test_validate_rejects_canonical_fields():
    obj = _valid_result(artifact_kind="unit_analysis")
    errors = validate_agent_result(obj)
    assert any("canonical" in e for e in errors)


def test_validate_rejects_artifact_id_field():
    obj = _valid_result(artifact_id="some.artifact")
    errors = validate_agent_result(obj)
    assert any("canonical" in e for e in errors)


def test_validate_rejects_invalid_status():
    obj = _valid_result(status="unknown_status")
    errors = validate_agent_result(obj)
    assert any("status" in e for e in errors)


def test_validate_rejects_invalid_verdict():
    obj = _valid_result(verdict="totally_fine")
    errors = validate_agent_result(obj)
    assert any("verdict" in e for e in errors)


def test_validate_supported_finding_without_evidence_rejected():
    obj = _valid_result(findings=[{
        "finding_id": "f1",
        "severity": "high",
        "title": "Bug found",
        "claim": "There is a bug",
        "support": "supported",
        "confidence": "high",
        "evidence": [],
        "unit_ids": [],
        "analysis_ids": [],
        "fact_ids": [],
    }])
    errors = validate_agent_result(obj)
    assert any("supported" in e and "evidence" in e for e in errors)


def test_validate_supported_finding_with_unit_ids_ok():
    obj = _valid_result(findings=[{
        "finding_id": "f1",
        "severity": "high",
        "title": "Bug found",
        "claim": "There is a bug",
        "support": "supported",
        "confidence": "high",
        "evidence": [],
        "unit_ids": ["unit.api.foo.bar"],
        "analysis_ids": [],
        "fact_ids": [],
    }])
    errors = validate_agent_result(obj)
    assert not any("supported" in e for e in errors)


def test_validate_inferred_finding_without_evidence_ok():
    obj = _valid_result(findings=[{
        "finding_id": "f1",
        "severity": "low",
        "title": "Possible issue",
        "claim": "This might be a problem",
        "support": "inferred",
        "confidence": "low",
        "evidence": [],
        "unit_ids": [],
    }])
    errors = validate_agent_result(obj)
    assert not errors


# ---------------------------------------------------------------------------
# child agent runner
# ---------------------------------------------------------------------------

def test_child_agent_runner_dispatches_valid_result(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "test dispatch")
    obj = _valid_result("task-dispatch", verdict="issues_found")
    runner = ChildAgentRunner(run_fn=lambda _prompt: _wrap(obj))
    result, errors = runner.dispatch(
        orch_store=store, orch_id=oid, task_id="task-dispatch", prompt="check this"
    )
    assert not errors
    assert result is not None
    findings = store.list_findings(oid)
    assert len(findings) == 1
    # quarantine must be empty
    assert store.list_quarantine(oid) == []


def test_child_agent_runner_quarantines_malformed(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "test quarantine")
    runner = ChildAgentRunner(run_fn=lambda _prompt: "no result block here")
    result, errors = runner.dispatch(
        orch_store=store, orch_id=oid, task_id="task-bad", prompt="check this"
    )
    assert errors
    assert result is None
    assert store.list_quarantine(oid) != []
    # findings must be empty
    assert store.list_findings(oid) == []


def test_child_agent_runner_quarantines_canonical_artifact_attempt(workspace):
    store = OrchestrationStore(workspace)
    oid = store.create("debug", "test canon guard")
    obj = _valid_result("task-canon", artifact_kind="unit_analysis")
    runner = ChildAgentRunner(run_fn=lambda _prompt: _wrap(obj))
    result, errors = runner.dispatch(
        orch_store=store, orch_id=oid, task_id="task-canon", prompt=""
    )
    assert errors
    assert any("canonical" in e for e in errors)
    assert store.list_quarantine(oid)


# ---------------------------------------------------------------------------
# synthesis
# ---------------------------------------------------------------------------

def test_synthesize_empty_findings():
    result = synthesize([], orchestration_id="o1", workflow="debug", request="?")
    assert result["finding_count"] == 0
    assert result["overall_confidence"] == "none"
    assert result["state"] == "inferred"


def test_synthesize_merges_deduplicates():
    f1 = _valid_result("t1", findings=[{
        "finding_id": "dup-1",
        "severity": "high",
        "title": "Same issue",
        "claim": "the bug is in payment",
        "support": "inferred",
        "confidence": "high",
        "unit_ids": ["unit.api.payments.process"],
        "evidence": [],
    }])
    f2 = _valid_result("t2", findings=[{
        "finding_id": "dup-2",
        "severity": "high",
        "title": "Same issue",
        "claim": "the bug is in payment",
        "support": "inferred",
        "confidence": "medium",  # lower than f1
        "unit_ids": ["unit.api.payments.process"],
        "evidence": [],
    }])
    result = synthesize([f1, f2], orchestration_id="o1", workflow="debug", request="bugs")
    # Same (unit, claim) → deduplicated to one
    assert result["finding_count"] == 1
    # Weakest-link: medium beats high in terms of lowness
    assert result["findings"][0]["confidence"] == "medium"
    assert result["overall_confidence"] == "medium"


def test_synthesize_detects_supported_contradicted_conflict():
    f1 = _valid_result("t1", findings=[{
        "finding_id": "con-1",
        "severity": "high",
        "title": "Issue",
        "claim": "payments is broken",
        "support": "supported",
        "confidence": "high",
        "unit_ids": ["unit.api.payments.process"],
        "evidence": ["span:1"],
    }])
    f2 = _valid_result("t2", findings=[{
        "finding_id": "con-2",
        "severity": "low",
        "title": "No issue",
        "claim": "payments is broken",
        "support": "contradicted",
        "confidence": "medium",
        "unit_ids": ["unit.api.payments.process"],
        "evidence": [],
    }])
    result = synthesize([f1, f2], orchestration_id="o1", workflow="debug", request="q")
    assert result["conflict_count"] > 0
    assert any("supported" in c["description"] for c in result["conflicts"])


def test_synthesize_state_always_inferred():
    f = _valid_result("t1", findings=[])
    result = synthesize([f], orchestration_id="o1", workflow="plan", request="x")
    assert result["state"] == "inferred"


# ---------------------------------------------------------------------------
# workflows (no-agent)
# ---------------------------------------------------------------------------

def test_no_agent_debug_workflow_creates_orchestration(indexed_workspace):
    orchestrator = OrchestratorWorkflow(indexed_workspace)
    outcome = orchestrator.run("debug", "login is broken", no_agent=True)
    assert "orchestration_id" in outcome
    assert outcome["mode"] == "no_agent"
    assert outcome["workflow"] == "debug"
    orch_store = OrchestrationStore(indexed_workspace)
    plan = orch_store.get_plan(outcome["orchestration_id"])
    assert plan["status"] == "completed"


def test_no_agent_plan_workflow_writes_finding(indexed_workspace):
    orchestrator = OrchestratorWorkflow(indexed_workspace)
    outcome = orchestrator.run("plan", "add a new endpoint", no_agent=True)
    store = OrchestrationStore(indexed_workspace)
    findings = store.list_findings(outcome["orchestration_id"])
    assert len(findings) == 1
    assert findings[0]["agent_profile"] == "no-agent-plan"


def test_no_agent_review_workflow_logs_events(indexed_workspace):
    orchestrator = OrchestratorWorkflow(indexed_workspace)
    outcome = orchestrator.run("review", "check users module", no_agent=True)
    store = OrchestrationStore(indexed_workspace)
    events = store.get_events(outcome["orchestration_id"])
    event_types = [e["event"] for e in events]
    assert "created" in event_types
    assert "preflight" in event_types
    assert "context_packed" in event_types


def test_agent_workflow_uses_run_fn(indexed_workspace):
    obj = _valid_result("task-agent", verdict="issues_found", findings=[{
        "finding_id": "agent-f1",
        "severity": "medium",
        "title": "Possible bug",
        "claim": "search_users may return stale results",
        "support": "inferred",
        "confidence": "medium",
        "unit_ids": ["unit.api.app.services.users.search_users"],
        "evidence": [],
    }])
    runner = ChildAgentRunner(run_fn=lambda _prompt: _wrap(obj))
    orchestrator = OrchestratorWorkflow(indexed_workspace, agent_runner=runner)
    outcome = orchestrator.run("debug", "search returns wrong results")
    assert outcome["mode"] == "agent"
    store = OrchestrationStore(indexed_workspace)
    findings = store.list_findings(outcome["orchestration_id"])
    assert findings


def test_agent_workflow_quarantines_on_malformed(indexed_workspace):
    runner = ChildAgentRunner(run_fn=lambda _prompt: "oops, no result block")
    orchestrator = OrchestratorWorkflow(indexed_workspace, agent_runner=runner)
    outcome = orchestrator.run("debug", "some issue")
    store = OrchestrationStore(indexed_workspace)
    assert store.list_quarantine(outcome["orchestration_id"])
    assert store.list_findings(outcome["orchestration_id"]) == []


# ---------------------------------------------------------------------------
# synthesize + conflicts CLI
# ---------------------------------------------------------------------------

def test_synthesize_stores_and_conflicts_readable(indexed_workspace):
    orch_store = OrchestrationStore(indexed_workspace)
    oid = orch_store.create("debug", "some bug")
    f = _valid_result("t1", findings=[])
    orch_store.write_finding(oid, "t1", f)
    result = synthesize([f], orchestration_id=oid, workflow="debug", request="some bug")
    orch_store.write_synthesis(oid, result)
    loaded = orch_store.get_synthesis(oid)
    assert loaded["orchestration_id"] == oid


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_cli_orchestrate_debug_no_agent(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    rc = main(["orchestrate", "debug", "login", "is", "broken", "--no-agent"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "orchestration:" in out
    assert "mode:      no_agent" in out


def test_cli_orchestrate_review_json(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    rc = main(["orchestrate", "review", "check users module", "--no-agent", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "orchestration_id" in data
    assert data["workflow"] == "review"


def test_cli_orchestrations_list(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    main(["orchestrate", "plan", "add feature", "--no-agent"])
    rc = main(["orchestrations", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "plan" in out


def test_cli_orchestrations_show(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    main(["orchestrate", "debug", "investigate crash", "--no-agent"])
    rc = main(["orchestrations", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "workflow" in out
    assert "events" in out


def test_cli_synthesize(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    main(["orchestrate", "debug", "test issue", "--no-agent"])
    rc = main(["synthesize"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "synthesis:" in out
    assert "confidence:" in out


def test_cli_conflicts_no_conflicts(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    main(["orchestrate", "debug", "no conflict test", "--no-agent"])
    main(["synthesize"])
    rc = main(["conflicts"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no conflicts" in out or "conflict" in out


def test_cli_agent_validate_valid_file(tmp_path, capsys):
    obj = _valid_result()
    f = tmp_path / "result.txt"
    f.write_text(_wrap(obj), encoding="utf-8")
    rc = main(["agent-validate", str(f)])
    assert rc == 0
    assert "VALID" in capsys.readouterr().out


def test_cli_agent_validate_invalid_file(tmp_path, capsys):
    obj = _valid_result(status="bad_status")
    f = tmp_path / "result.txt"
    f.write_text(_wrap(obj), encoding="utf-8")
    rc = main(["agent-validate", str(f)])
    assert rc == 1


def test_cli_agent_validate_canonical_attempt_rejected(tmp_path, capsys):
    obj = _valid_result(artifact_kind="unit_analysis")
    f = tmp_path / "result.txt"
    f.write_text(_wrap(obj), encoding="utf-8")
    rc = main(["agent-validate", str(f)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "canonical" in out
