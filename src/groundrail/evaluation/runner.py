"""Small built-in evaluation harness for Groundrail artifacts.

This is not a benchmark suite yet; it is a regression guard for the trust model.
It checks that generated artifacts do not overclaim verified AI truth, stale
analyses are visible, retrieval exists, and capability gaps stay readable.
"""

from __future__ import annotations

from typing import Any

from ..analyzer.store import AnalysisStore
from ..core import envelope, vocab
from ..core.gaps import CapabilityGapRegistry
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..indexer.unit_index import UNIT_INDEX_PATH, UnitStore
from ..router.retrieval import RETRIEVAL_PATH

EVAL_REPORT_PATH = "audit/eval-report.json"


class EvaluationRunner:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store

    def run(self) -> dict[str, Any]:
        checks = [
            self._check_units_exist(),
            self._check_ai_never_verified(),
            self._check_stale_detectable(),
            self._check_retrieval_exists(),
            self._check_gap_registry_readable(),
        ]
        failures = [c for c in checks if c["status"] == "fail"]
        warnings = [c for c in checks if c["status"] == "warn"]
        result = {
            "status": "fail" if failures else ("warn" if warnings else "ok"),
            "checks": checks,
            "failures": len(failures),
            "warnings": len(warnings),
        }
        artifact = envelope.build_envelope(
            artifact_id="groundrail.audit.eval",
            artifact_kind="eval_report",
            generator=envelope.make_generator("groundrail eval run", "groundrail.evaluation"),
            source=envelope.make_source(),
            data=result,
        )
        self.store.write_json(EVAL_REPORT_PATH, artifact)
        return result

    def _check_units_exist(self) -> dict[str, Any]:
        units = UnitStore(self.store).all()
        return {
            "name": "unit_index_present",
            "status": "ok" if units else "warn",
            "detail": f"{len(units)} indexed unit(s)",
            "artifact": UNIT_INDEX_PATH,
        }

    def _check_ai_never_verified(self) -> dict[str, Any]:
        bad = [a["analysis_id"] for a in AnalysisStore(self.store).all() if a.get("state") == vocab.STATUS_VERIFIED]
        return {
            "name": "ai_analysis_not_verified",
            "status": "fail" if bad else "ok",
            "detail": "AI analyses claiming verified: " + ", ".join(bad) if bad else "no AI analyses claim verified",
        }

    def _check_stale_detectable(self) -> dict[str, Any]:
        units = {u["unit_id"]: u for u in UnitStore(self.store).all()}
        store = AnalysisStore(self.store)
        stale = [a["analysis_id"] for a in store.all() if a.get("unit_id") in units and store.is_stale(a, units[a["unit_id"]])]
        return {
            "name": "stale_analysis_detection",
            "status": "warn" if stale else "ok",
            "detail": f"{len(stale)} stale analysis artifact(s)",
            "items": stale,
        }

    def _check_retrieval_exists(self) -> dict[str, Any]:
        exists = self.store.exists(RETRIEVAL_PATH)
        return {
            "name": "retrieval_index_present",
            "status": "ok" if exists else "warn",
            "detail": "retrieval index exists" if exists else "run `groundrail search` or `groundrail prepare`",
            "artifact": RETRIEVAL_PATH,
        }

    def _check_gap_registry_readable(self) -> dict[str, Any]:
        gaps = CapabilityGapRegistry(self.store).load()
        return {
            "name": "capability_gaps_readable",
            "status": "ok",
            "detail": f"{len(gaps)} recorded gap(s)",
        }
