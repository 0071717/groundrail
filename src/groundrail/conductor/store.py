"""Orchestration store — record, plan, append-only event log, tasks, findings.

Layout under ``.groundrail/`` mirrors ``docs/02_CONTRACTS_AND_ARTIFACTS.md``:

  orchestrations/<id>/orchestration.json       — record (workflow, request, status)
  orchestrations/<id>/plan.json                — the plan: ordered task steps
  orchestrations/<id>/events.jsonl             — append-only event log
  orchestrations/<id>/tasks/<task>/result.json — validated task result (full)
  orchestrations/<id>/synthesis.json           — merged synthesis
  orchestrations/<id>/summary.md               — human-readable summary
  agents/findings/<id>__<task>.json            — global index of validated findings
  agents/quarantine/<id>__<task>.json          — global index of rejected results

Agents (and this store on their behalf) write ONLY to the paths above; never to
canonical indexes (index/, analysis/, source/) — see AGENTS.md layer discipline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..core import timeutil
from ..core.store import ArtifactStore
from ..core.workspace import Workspace

ORCH_ROOT = "orchestrations"
AGENTS_FINDINGS = "agents/findings"
AGENTS_QUARANTINE = "agents/quarantine"
VALID_WORKFLOW_STATUSES = frozenset({"running", "completed", "failed", "partial"})


def _new_id() -> str:
    # Microsecond precision so ids created in the same second still sort.
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


class OrchestrationStore:
    """Reads and writes orchestration state under ``.groundrail/``."""

    def __init__(self, workspace: Workspace) -> None:
        self._ws = workspace
        self._store: ArtifactStore = workspace.store

    def _rel(self, orch_id: str, *parts: str) -> str:
        return "/".join([ORCH_ROOT, orch_id, *parts])

    @staticmethod
    def _index_name(orch_id: str, task_id: str) -> str:
        return f"{orch_id}__{task_id}.json"

    # --- lifecycle -----------------------------------------------------------
    def create(self, workflow: str, request: str) -> str:
        orch_id = _new_id()
        now = timeutil.now_iso()
        record = {
            "schema_version": "1",
            "orchestration_id": orch_id,
            "workflow": workflow,
            "request": request,
            "created_at": now,
            "status": "running",
        }
        self._store.write_json(self._rel(orch_id, "orchestration.json"), record)
        self.log_event(orch_id, "created", {"workflow": workflow, "request": request})
        return orch_id

    def write_plan(self, orch_id: str, tasks: list[dict[str, Any]]) -> None:
        """Record the plan: the ordered task steps this orchestration will run."""
        plan = {
            "schema_version": "1",
            "orchestration_id": orch_id,
            "created_at": timeutil.now_iso(),
            "tasks": tasks,
        }
        self._store.write_json(self._rel(orch_id, "plan.json"), plan)
        self.log_event(orch_id, "planned", {"task_count": len(tasks)})

    def update_status(self, orch_id: str, status: str) -> None:
        if status not in VALID_WORKFLOW_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        record = self._store.read_json(self._rel(orch_id, "orchestration.json"))
        record["status"] = status
        record["updated_at"] = timeutil.now_iso()
        self._store.write_json(self._rel(orch_id, "orchestration.json"), record)

    def log_event(
        self, orch_id: str, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        row: dict[str, Any] = {"ts": timeutil.now_iso(), "event": event_type}
        if data:
            row.update(data)
        self._store.append_jsonl(self._rel(orch_id, "events.jsonl"), row)

    # --- reads ---------------------------------------------------------------
    def get_orchestration(self, orch_id: str) -> dict[str, Any]:
        return self._store.read_json(self._rel(orch_id, "orchestration.json"))

    def get_plan(self, orch_id: str) -> dict[str, Any]:
        return self._store.read_json(self._rel(orch_id, "plan.json"))

    def get_events(self, orch_id: str) -> list[dict[str, Any]]:
        return self._store.read_jsonl(self._rel(orch_id, "events.jsonl"))

    def list_all(self) -> list[dict[str, Any]]:
        orch_dir = self._store.root / ORCH_ROOT
        if not orch_dir.is_dir():
            return []
        records = []
        for entry in sorted(orch_dir.iterdir()):
            rec_path = f"{ORCH_ROOT}/{entry.name}/orchestration.json"
            if entry.is_dir() and self._store.exists(rec_path):
                records.append(self._store.read_json(rec_path))
        return sorted(records, key=lambda r: r.get("orchestration_id", ""), reverse=True)

    def latest_id(self) -> str | None:
        records = self.list_all()
        return records[0]["orchestration_id"] if records else None

    # --- task results / quarantine -------------------------------------------
    def write_finding(self, orch_id: str, task_id: str, finding: dict[str, Any]) -> None:
        # Full result lives with the orchestration's task; a lightweight index
        # entry goes to the global agents/findings/ view (docs/02 layout).
        self._store.write_json(
            self._rel(orch_id, "tasks", task_id, "result.json"), finding
        )
        self._store.write_json(
            f"{AGENTS_FINDINGS}/{self._index_name(orch_id, task_id)}",
            {
                "orchestration_id": orch_id,
                "task_id": task_id,
                "agent_profile": finding.get("agent_profile"),
                "verdict": finding.get("verdict"),
                "confidence": finding.get("confidence"),
                "finding_count": len(finding.get("findings", [])),
            },
        )
        self.log_event(orch_id, "finding_stored", {"task_id": task_id})

    def quarantine_result(
        self, orch_id: str, task_id: str, reason: str, raw: str
    ) -> None:
        record = {
            "quarantined_at": timeutil.now_iso(),
            "orchestration_id": orch_id,
            "task_id": task_id,
            "reason": reason,
            "raw_excerpt": raw[:2000],
        }
        self._store.write_json(
            self._rel(orch_id, "tasks", task_id, "quarantine.json"), record
        )
        self._store.write_json(
            f"{AGENTS_QUARANTINE}/{self._index_name(orch_id, task_id)}", record
        )
        self.log_event(orch_id, "quarantined", {"task_id": task_id, "reason": reason})

    def list_findings(self, orch_id: str) -> list[dict[str, Any]]:
        tasks_dir = self._store.root / ORCH_ROOT / orch_id / "tasks"
        if not tasks_dir.is_dir():
            return []
        out = []
        for task_dir in sorted(tasks_dir.iterdir()):
            rel = f"{ORCH_ROOT}/{orch_id}/tasks/{task_dir.name}/result.json"
            if self._store.exists(rel):
                out.append(self._store.read_json(rel))
        return out

    def list_quarantine(self, orch_id: str) -> list[dict[str, Any]]:
        tasks_dir = self._store.root / ORCH_ROOT / orch_id / "tasks"
        if not tasks_dir.is_dir():
            return []
        out = []
        for task_dir in sorted(tasks_dir.iterdir()):
            rel = f"{ORCH_ROOT}/{orch_id}/tasks/{task_dir.name}/quarantine.json"
            if self._store.exists(rel):
                out.append(self._store.read_json(rel))
        return out

    # --- global agents view --------------------------------------------------
    def list_agent_findings(self) -> list[dict[str, Any]]:
        return self._read_index_dir(AGENTS_FINDINGS)

    def list_agent_quarantine(self) -> list[dict[str, Any]]:
        return self._read_index_dir(AGENTS_QUARANTINE)

    def _read_index_dir(self, rel_dir: str) -> list[dict[str, Any]]:
        d = self._store.root / rel_dir
        if not d.is_dir():
            return []
        return [
            self._store.read_json(f"{rel_dir}/{e.name}")
            for e in sorted(d.iterdir())
            if e.suffix == ".json"
        ]

    # --- synthesis / summary -------------------------------------------------
    def write_synthesis(self, orch_id: str, synthesis: dict[str, Any]) -> None:
        self._store.write_json(self._rel(orch_id, "synthesis.json"), synthesis)
        self.log_event(
            orch_id, "synthesized", {"finding_count": len(synthesis.get("findings", []))}
        )

    def get_synthesis(self, orch_id: str) -> dict[str, Any]:
        return self._store.read_json(self._rel(orch_id, "synthesis.json"))

    def write_summary(self, orch_id: str, markdown: str) -> None:
        path = self._store.resolve(self._rel(orch_id, "summary.md"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
