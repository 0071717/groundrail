"""Orchestration store — append-only event log, plans, findings, quarantine.

Layout under ``.groundrail/``:
  orchestrations/<id>/plan.json               — workflow definition and status
  orchestrations/<id>/events.jsonl            — append-only event log
  orchestrations/<id>/findings/<task>.json    — validated agent findings
  orchestrations/<id>/quarantine/<task>.json  — malformed or rejected results
  orchestrations/<id>/synthesis.json          — merged synthesis output
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core import timeutil
from ..core.store import ArtifactStore
from ..core.workspace import Workspace

ORCH_ROOT = "orchestrations"
VALID_WORKFLOW_STATUSES = frozenset({"running", "completed", "failed", "partial"})


def _new_id() -> str:
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


class OrchestrationStore:
    """Reads and writes orchestration state under ``.groundrail/orchestrations/``."""

    def __init__(self, workspace: Workspace) -> None:
        self._ws = workspace
        self._store: ArtifactStore = workspace.store

    def _rel(self, orch_id: str, *parts: str) -> str:
        return "/".join([ORCH_ROOT, orch_id, *parts])

    # --- lifecycle -----------------------------------------------------------
    def create(self, workflow: str, request: str) -> str:
        orch_id = _new_id()
        now = timeutil.now_iso()
        plan = {
            "schema_version": "1",
            "orchestration_id": orch_id,
            "workflow": workflow,
            "request": request,
            "created_at": now,
            "status": "running",
        }
        self._store.write_json(self._rel(orch_id, "plan.json"), plan)
        self._store.append_jsonl(
            self._rel(orch_id, "events.jsonl"),
            {"ts": now, "event": "created", "workflow": workflow, "request": request},
        )
        return orch_id

    def update_status(self, orch_id: str, status: str) -> None:
        if status not in VALID_WORKFLOW_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        plan = self._store.read_json(self._rel(orch_id, "plan.json"))
        plan["status"] = status
        plan["updated_at"] = timeutil.now_iso()
        self._store.write_json(self._rel(orch_id, "plan.json"), plan)

    def log_event(
        self, orch_id: str, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        row: dict[str, Any] = {"ts": timeutil.now_iso(), "event": event_type}
        if data:
            row.update(data)
        self._store.append_jsonl(self._rel(orch_id, "events.jsonl"), row)

    # --- reads ---------------------------------------------------------------
    def get_plan(self, orch_id: str) -> dict[str, Any]:
        return self._store.read_json(self._rel(orch_id, "plan.json"))

    def get_events(self, orch_id: str) -> list[dict[str, Any]]:
        return self._store.read_jsonl(self._rel(orch_id, "events.jsonl"))

    def list_all(self) -> list[dict[str, Any]]:
        orch_dir = self._store.root / ORCH_ROOT
        if not orch_dir.is_dir():
            return []
        plans = []
        for entry in sorted(orch_dir.iterdir()):
            if entry.is_dir() and self._store.exists(f"{ORCH_ROOT}/{entry.name}/plan.json"):
                plans.append(self._store.read_json(f"{ORCH_ROOT}/{entry.name}/plan.json"))
        return sorted(plans, key=lambda p: p.get("orchestration_id", ""), reverse=True)

    def latest_id(self) -> str | None:
        plans = self.list_all()
        return plans[0]["orchestration_id"] if plans else None

    # --- findings / quarantine -----------------------------------------------
    def write_finding(self, orch_id: str, task_id: str, finding: dict[str, Any]) -> None:
        self._store.write_json(
            self._rel(orch_id, "findings", f"{task_id}.json"), finding
        )
        self.log_event(orch_id, "finding_stored", {"task_id": task_id})

    def quarantine_result(
        self, orch_id: str, task_id: str, reason: str, raw: str
    ) -> None:
        record = {
            "quarantined_at": timeutil.now_iso(),
            "task_id": task_id,
            "reason": reason,
            "raw_excerpt": raw[:2000],
        }
        self._store.write_json(
            self._rel(orch_id, "quarantine", f"{task_id}.json"), record
        )
        self.log_event(orch_id, "quarantined", {"task_id": task_id, "reason": reason})

    def list_findings(self, orch_id: str) -> list[dict[str, Any]]:
        findings_dir = self._store.root / ORCH_ROOT / orch_id / "findings"
        if not findings_dir.is_dir():
            return []
        return [
            self._store.read_json(f"{ORCH_ROOT}/{orch_id}/findings/{e.name}")
            for e in sorted(findings_dir.iterdir())
            if e.suffix == ".json"
        ]

    def list_quarantine(self, orch_id: str) -> list[dict[str, Any]]:
        q_dir = self._store.root / ORCH_ROOT / orch_id / "quarantine"
        if not q_dir.is_dir():
            return []
        return [
            self._store.read_json(f"{ORCH_ROOT}/{orch_id}/quarantine/{e.name}")
            for e in sorted(q_dir.iterdir())
            if e.suffix == ".json"
        ]

    # --- synthesis -----------------------------------------------------------
    def write_synthesis(self, orch_id: str, synthesis: dict[str, Any]) -> None:
        self._store.write_json(self._rel(orch_id, "synthesis.json"), synthesis)
        self.log_event(
            orch_id,
            "synthesized",
            {"finding_count": len(synthesis.get("findings", []))},
        )

    def get_synthesis(self, orch_id: str) -> dict[str, Any]:
        return self._store.read_json(self._rel(orch_id, "synthesis.json"))
