"""Build an auditable map of Groundrail's implemented flow.

The map is an artifact, not marketing copy: each layer reports the commands and
artifact files that currently represent it, plus whether those artifacts exist in
the current workspace.
"""

from __future__ import annotations

from typing import Any

from ..core import envelope, timeutil
from ..core.store import ArtifactStore
from ..core.workspace import Workspace

LAYER_MAP_PATH = "audit/layer-map.json"

_LAYER_DEFS: list[dict[str, Any]] = [
    {
        "layer": "source_snapshot",
        "goal": "Record source files, hashes, git state, and changed files.",
        "commands": ["init", "snapshot", "changed", "status", "refresh"],
        "artifacts": ["source/snapshot.json", "index/file-index.json", "audit/run-manifest.json"],
    },
    {
        "layer": "evidence_kernel",
        "goal": "Shared envelopes, evidence, validation, stale checks, gaps, guarded storage.",
        "commands": ["validate", "verify", "gaps", "doctor"],
        "artifacts": ["audit/stale-report.json", "gaps/capability-gaps.json"],
    },
    {
        "layer": "unit_index",
        "goal": "Bounded Python/TypeScript units, spans, imports, calls, endpoint candidates.",
        "commands": ["index units", "unit list", "unit show", "unit code"],
        "artifacts": ["index/unit-index.json", "index/import-index.json", "index/call-candidates.json"],
    },
    {
        "layer": "ai_unit_analysis",
        "goal": "Run bounded AI analysis over units with provenance, confidence, uncertainty, and stale binding.",
        "commands": ["analyze-unit", "analyze-units", "analysis show", "analysis validate"],
        "artifacts": ["analysis/units", "audit/unit-analysis-report.json"],
    },
    {
        "layer": "human_review",
        "goal": "Developer confirm/reject loop for summaries, claims, notes, and stale confirmations.",
        "commands": ["review list", "review show", "review confirm", "review reject", "review stale", "notes list"],
        "artifacts": ["review/reviews.jsonl", "review/confirmed-items.jsonl", "review/rejected-items.jsonl", "audit/stale-confirmations.json"],
    },
    {
        "layer": "knowledge_promotion",
        "goal": "Conservatively promote developer-confirmed, non-stale claims into reusable knowledge facts.",
        "commands": ["promote list-candidates", "promote claim", "knowledge show", "knowledge list"],
        "artifacts": ["knowledge/facts.json", "knowledge/promoted-claims.jsonl", "audit/promotion-report.json"],
    },
    {
        "layer": "flow_impact",
        "goal": "Compose unit graph, endpoint/unit flow, impact, likely tests, and coverage gaps.",
        "commands": ["graph build", "flow unit", "flow endpoint", "impact file", "impact unit", "tests-for"],
        "artifacts": ["graph/nodes.json", "graph/edges.json", "impact/latest.json", "testing/test-selection.json"],
    },
    {
        "layer": "context_router",
        "goal": "Search and build citation-aware context packs for Kiro.",
        "commands": ["search", "prepare", "ctx explain"],
        "artifacts": ["cache/retrieval-index.jsonl", "sessions"],
    },
    {
        "layer": "kiro_answer_audit",
        "goal": "Run Kiro, capture output, parse citation support, and fail strict audits.",
        "commands": ["ask", "audit answer", "smart"],
        "artifacts": ["sessions/<id>/kiro-output.raw.md", "sessions/<id>/audit.json"],
    },
    {
        "layer": "conductor_agents",
        "goal": "Orchestrate debug/review/plan workflows, validate agent results, quarantine unsupported findings.",
        "commands": ["orchestrate", "orchestrations", "synthesize", "conflicts", "agent-validate"],
        "artifacts": ["orchestrations"],
    },
    {
        "layer": "tui_cockpit",
        "goal": "Read-only cockpit over validated service outputs.",
        "commands": ["tui", "tui --print"],
        "artifacts": [],
    },
    {
        "layer": "evaluation_harness",
        "goal": "Regression checks for overclaiming, stale support, retrieval, and citation/audit quality.",
        "commands": ["eval run"],
        "artifacts": ["audit/eval-report.json"],
    },
]


class LayerMapBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store

    def build(self, *, write: bool = True) -> dict[str, Any]:
        layers = []
        for spec in _LAYER_DEFS:
            artifacts = [self._artifact_status(path) for path in spec["artifacts"]]
            layers.append({
                **spec,
                "artifacts": artifacts,
                "implemented": True,
                "workspace_ready": bool(artifacts) and all(a["exists"] for a in artifacts if not a["path"].endswith("/<id>/kiro-output.raw.md")),
            })
        flow_edges = [
            ("source_snapshot", "unit_index"),
            ("unit_index", "ai_unit_analysis"),
            ("ai_unit_analysis", "human_review"),
            ("human_review", "knowledge_promotion"),
            ("unit_index", "flow_impact"),
            ("ai_unit_analysis", "context_router"),
            ("knowledge_promotion", "context_router"),
            ("context_router", "kiro_answer_audit"),
            ("kiro_answer_audit", "conductor_agents"),
            ("conductor_agents", "tui_cockpit"),
            ("kiro_answer_audit", "evaluation_harness"),
        ]
        result = {
            "schema_version": "1",
            "created_at": timeutil.now_iso(),
            "workspace": str(self.workspace.path),
            "layers": layers,
            "flow_edges": [{"from": a, "to": b} for a, b in flow_edges],
            "note": "implemented=True means there is a command/artifact contract for the layer; workspace_ready depends on whether this workspace has generated the artifacts yet.",
        }
        if write:
            artifact = envelope.build_envelope(
                artifact_id="groundrail.audit.layer_map",
                artifact_kind="layer_map",
                generator=envelope.make_generator("groundrail map", "groundrail.layers"),
                source=envelope.make_source(),
                data=result,
            )
            self.store.write_json(LAYER_MAP_PATH, artifact)
        return result

    def _artifact_status(self, path: str) -> dict[str, Any]:
        if "<id>" in path:
            return {"path": path, "exists": False, "dynamic": True}
        full = self.store.resolve(path)
        return {"path": path, "exists": full.exists(), "dynamic": False}
