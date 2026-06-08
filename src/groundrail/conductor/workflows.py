"""Orchestration workflows: debug, review, and plan.

Each workflow:
  1. Runs preflight checks (snapshot freshness, stale units)
  2. Builds a context pack for the request
  3. Either dispatches to a child agent (if configured and ``--no-agent`` is
     not set) or generates a structured plan from the context pack alone
  4. Stores all events in the orchestration event log

No-agent mode is the primary path — useful without any external AI.
The child-agent path is additive: it enriches findings but the orchestration
completes either way.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core import timeutil, vocab
from ..core.workspace import Workspace
from ..indexer.snapshot import FILE_INDEX_PATH
from ..indexer.unit_index import UnitStore
from ..analyzer.store import AnalysisStore
from ..router.context_pack import ContextPackBuilder
from .agent import ChildAgentRunner
from .store import OrchestrationStore

_WORKFLOW_MODES = {
    "debug": "debug",
    "review": "review",
    "plan": "plan",
}


def _map_mode(workflow: str) -> str:
    mode_map = {"debug": "debug", "review": "review", "plan": "plan"}
    return mode_map.get(workflow, "ask")


def _preflight(workspace: Workspace) -> dict[str, Any]:
    """Check snapshot and index freshness. Returns a preflight summary."""
    store = workspace.store
    warnings = []

    if not store.exists(FILE_INDEX_PATH):
        warnings.append("no snapshot; run `groundrail snapshot` before orchestrating")

    if not store.exists("index/unit-index.jsonl"):
        warnings.append("no unit index; run `groundrail index units` first")

    stale_count = 0
    missing_count = 0
    units: list[Any] = []
    try:
        units = list(UnitStore(store).all())
        analyses = AnalysisStore(store)
        for unit in units:
            analysis = analyses.try_get(unit["unit_id"])
            if analysis is None:
                missing_count += 1
            elif analyses.is_stale(analysis, unit):
                stale_count += 1
    except Exception:
        warnings.append("could not check analysis freshness")

    if stale_count:
        warnings.append(
            f"{stale_count} unit(s) have stale analysis; consider `groundrail analyze-units --stale`"
        )
    if missing_count:
        warnings.append(
            f"{missing_count} unit(s) have no analysis; consider `groundrail analyze-units --missing`"
        )

    return {
        "ok": not any("no snapshot" in w or "no unit index" in w for w in warnings),
        "warnings": warnings,
        "unit_count": len(units),
        "stale_count": stale_count,
        "missing_count": missing_count,
    }


def _build_no_agent_plan(
    workflow: str,
    request: str,
    pack: dict[str, Any],
    workspace: Workspace,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    """Generate a structured plan from the context pack without a child agent."""
    selected_units = pack.get("source_evidence", [])
    gaps = pack.get("known_gaps", [])
    stale_items = pack.get("freshness", {}).get("stale_items", [])

    # Build findings from what we know about selected units
    findings = []
    analyses = AnalysisStore(workspace.store)

    for unit in selected_units:
        uid = unit["unit_id"]
        try:
            analysis = analyses.get(uid)
        except Exception:
            continue
        if analysis is None:
            continue
        conf = analysis.get("confidence", vocab.CONFIDENCE_LOW)
        state = analysis.get("state", vocab.STATUS_INFERRED)

        # Low confidence or uncertain units are worth flagging
        uncertainties = analysis.get("data", {}).get("uncertainties", [])
        notes = analysis.get("data", {}).get("ai_notes", [])
        security_notes = [n for n in notes if n.get("kind") == "security_concern"]
        bug_notes = [n for n in notes if n.get("kind") == "potential_bug"]

        if workflow == "debug":
            if uncertainties or bug_notes or conf == vocab.CONFIDENCE_LOW:
                findings.append({
                    "finding_id": f"plan-{uid[:40]}",
                    "severity": "medium" if conf != vocab.CONFIDENCE_LOW else "high",
                    "title": f"Investigate: {unit.get('name', uid)}",
                    "claim": (
                        f"Unit {uid!r} has "
                        + (f"{len(uncertainties)} uncertainty(ies)" if uncertainties else "")
                        + (" and " if uncertainties and bug_notes else "")
                        + (f"{len(bug_notes)} potential bug note(s)" if bug_notes else "")
                        or f"low confidence analysis (confidence={conf})"
                    ),
                    "support": "inferred",
                    "confidence": conf,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": ["needs_investigation"],
                })
            if security_notes:
                findings.append({
                    "finding_id": f"sec-{uid[:40]}",
                    "severity": "high",
                    "title": f"Security concern: {unit.get('name', uid)}",
                    "claim": f"AI analysis flagged a security concern in {uid!r}",
                    "support": "inferred",
                    "confidence": vocab.CONFIDENCE_LOW,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": ["security_concern"],
                })

        elif workflow == "review":
            review_status = analysis.get("review_status", vocab.REVIEW_UNREVIEWED)
            if review_status == vocab.REVIEW_UNREVIEWED:
                findings.append({
                    "finding_id": f"review-{uid[:40]}",
                    "severity": "low",
                    "title": f"Unreviewed: {unit.get('name', uid)}",
                    "claim": f"Unit {uid!r} has not been reviewed by a developer",
                    "support": "inferred",
                    "confidence": conf,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": ["unreviewed"],
                })
            elif review_status == vocab.REVIEW_STALE_CONFIRMATION:
                findings.append({
                    "finding_id": f"stale-{uid[:40]}",
                    "severity": "medium",
                    "title": f"Stale confirmation: {unit.get('name', uid)}",
                    "claim": f"Developer confirmation for {uid!r} is stale",
                    "support": "inferred",
                    "confidence": vocab.CONFIDENCE_LOW,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": ["stale_confirmation"],
                })

        elif workflow == "plan":
            # For plan: highlight what is well-understood vs. uncertain
            if conf == vocab.CONFIDENCE_HIGH and state == vocab.STATUS_INFERRED:
                findings.append({
                    "finding_id": f"plan-ok-{uid[:40]}",
                    "severity": "info",
                    "title": f"Well-understood: {unit.get('name', uid)}",
                    "claim": f"Unit {uid!r} has high-confidence inferred analysis",
                    "support": "inferred",
                    "confidence": conf,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": [],
                })
            elif conf == vocab.CONFIDENCE_LOW:
                findings.append({
                    "finding_id": f"plan-gap-{uid[:40]}",
                    "severity": "medium",
                    "title": f"Low confidence: {unit.get('name', uid)}",
                    "claim": (
                        f"Unit {uid!r} is poorly understood; implementation plan "
                        "may need manual investigation"
                    ),
                    "support": "inferred",
                    "confidence": conf,
                    "unit_ids": [uid],
                    "evidence": [],
                    "risk_tags": ["plan_uncertainty"],
                })

    # Capability gaps are always surfaced
    for gap in gaps:
        findings.append({
            "finding_id": f"gap-{gap.get('gap_id', uuid.uuid4().hex[:8])}",
            "severity": "info",
            "title": f"Capability gap: {gap.get('kind', 'unknown')}",
            "claim": gap.get("description", "extractor capability gap"),
            "support": "not_confirmed",
            "confidence": vocab.CONFIDENCE_LOW,
            "unit_ids": [],
            "evidence": [],
            "risk_tags": ["capability_gap"],
        })

    task_id = f"no-agent-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "agent_profile": "no-agent-plan",
        "status": "completed",
        "verdict": "issues_found" if findings else "no_issues",
        "confidence": vocab.CONFIDENCE_MEDIUM,
        "summary": (
            f"No-agent {workflow} plan for: {request!r}. "
            f"Context pack selected {len(selected_units)} unit(s). "
            f"Found {len(findings)} item(s) to address."
            + (f" {len(stale_items)} stale item(s) excluded." if stale_items else "")
            + (f" {len(gaps)} capability gap(s) noted." if gaps else "")
            + (f" Preflight warnings: {'; '.join(preflight['warnings'])}" if preflight["warnings"] else "")
        ),
        "findings": findings,
        "uncertainties": preflight["warnings"],
        "not_confirmed": [],
        "requested_followups": (
            ["Run `groundrail analyze-units --missing` to fill analysis gaps"]
            if preflight.get("missing_count", 0) > 0
            else []
        ),
    }


class OrchestratorWorkflow:
    """Runs debug / review / plan workflows with or without a child agent."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        agent_runner: ChildAgentRunner | None = None,
    ) -> None:
        self.ws = workspace
        self.store = OrchestrationStore(workspace)
        self.agent = agent_runner or ChildAgentRunner()

    def run(
        self,
        workflow: str,
        request: str,
        *,
        no_agent: bool = False,
    ) -> dict[str, Any]:
        if workflow not in _WORKFLOW_MODES:
            from ..core.errors import GroundrailError
            raise GroundrailError(f"unknown workflow {workflow!r}; choose debug, review, or plan")

        orch_id = self.store.create(workflow, request)

        # Preflight
        preflight = _preflight(self.ws)
        self.store.log_event(orch_id, "preflight", preflight)

        # Context pack
        try:
            mode = _map_mode(workflow)
            pack = ContextPackBuilder(self.ws).build(mode=mode, request=request)
            self.store.log_event(
                orch_id,
                "context_packed",
                {"units_selected": len(pack.get("source_evidence", []))},
            )
        except Exception as exc:
            self.store.log_event(orch_id, "context_pack_failed", {"error": str(exc)})
            self.store.update_status(orch_id, "failed")
            raise

        use_agent = (not no_agent) and self.agent.configured
        task_id = f"task-{uuid.uuid4().hex[:12]}"

        # Write the plan (ordered task steps) so get_plan() callers always succeed.
        self.store.write_plan(orch_id, [
            {
                "task_id": task_id,
                "type": "agent" if use_agent else "no_agent",
                "description": f"{workflow}: {request}",
            }
        ])

        if use_agent:
            prompt = _build_agent_prompt(workflow, request, pack, self.ws)
            self.store.log_event(orch_id, "agent_dispatched", {"task_id": task_id})
            result, errors = self.agent.dispatch(
                orch_store=self.store,
                orch_id=orch_id,
                task_id=task_id,
                prompt=prompt,
            )
            if errors:
                self.store.log_event(
                    orch_id, "agent_quarantined", {"task_id": task_id, "errors": errors}
                )
            else:
                self.store.log_event(orch_id, "agent_completed", {"task_id": task_id})
        else:
            result = _build_no_agent_plan(workflow, request, pack, self.ws, preflight)
            self.store.write_finding(orch_id, task_id, result)

        self.store.update_status(orch_id, "completed")
        return {
            "orchestration_id": orch_id,
            "workflow": workflow,
            "request": request,
            "mode": "agent" if use_agent else "no_agent",
            "task_id": task_id,
            "preflight": preflight,
            "finding": result,
        }


def _build_agent_prompt(
    workflow: str, request: str, pack: dict[str, Any], workspace: Workspace
) -> str:
    """Build the structured task prompt sent to the child agent."""
    # The markdown was already written to the session file during build(); read it
    # from there rather than re-rendering (which would require a live ContextPackBuilder).
    session_id = pack.get("session_id", "")
    pack_md = ""
    if session_id:
        md_path = workspace.store.resolve(f"sessions/{session_id}/context-pack.md")
        if md_path.exists():
            pack_md = md_path.read_text(encoding="utf-8")
    units = pack.get("source_evidence", [])

    instructions = {
        "debug": (
            "Analyse the provided context pack to investigate the following issue. "
            "Identify the most likely root-cause units, highlight uncertainties, "
            "and recommend tests to verify the fix."
        ),
        "review": (
            "Review the provided context pack. Identify units that need developer "
            "attention, flag stale or unreviewed items, and recommend confirmations "
            "or rejections for the review queue."
        ),
        "plan": (
            "Use the provided context pack to plan the implementation of the request. "
            "Identify which units will be affected, what dependencies exist, "
            "and what tests should be written or updated."
        ),
    }.get(workflow, "Analyse the provided context pack and report findings.")

    unit_ids = [u["unit_id"] for u in units]

    return f"""You are a Groundrail child agent. {instructions}

REQUEST: {request}

CONTEXT PACK:
{pack_md}

UNIT IDS IN PACK: {unit_ids}

INSTRUCTIONS:
- Your findings must be evidence-referenced (unit_ids, analysis_ids, or evidence spans).
- Do NOT claim state: verified. All your findings are inferred.
- Do NOT output any Groundrail canonical artifact (no artifact_kind, artifact_id fields).
- Wrap your entire result in <{RESULT_TAG}> ... </{RESULT_TAG}> tags.
- The result must be valid JSON matching the groundrail_agent_result schema.

RESULT TAG: {RESULT_TAG}
"""


# Keep the tag name accessible for the prompt builder
RESULT_TAG = "groundrail_agent_result"
