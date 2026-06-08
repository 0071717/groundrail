"""Promotion and knowledge artifact writer.

Promotion is deliberately narrow: only developer-confirmed, non-stale claims can
be promoted. Promoted facts remain ``dev_confirmed`` knowledge, not source-
verified truth.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..analyzer.store import AnalysisStore
from ..core import envelope, timeutil, vocab
from ..core.errors import GroundrailError, NotFoundError
from ..core.store import ArtifactStore
from ..indexer.unit_index import UnitStore

FACTS_PATH = "knowledge/facts.json"
PROMOTED_PATH = "knowledge/promoted-claims.jsonl"
PROMOTION_REPORT_PATH = "audit/promotion-report.json"


class KnowledgeStore:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self.analyses = AnalysisStore(store)
        self.units = UnitStore(store)

    def candidates(self) -> list[dict[str, Any]]:
        units = {u["unit_id"]: u for u in self.units.all()}
        out: list[dict[str, Any]] = []
        for analysis in self.analyses.all():
            unit = units.get(analysis["unit_id"])
            stale = bool(unit and self.analyses.is_stale(analysis, unit))
            for field in ("intent", "inputs", "outputs", "side_effects", "state_access", "calls", "errors", "behavioral_notes"):
                for claim in analysis.get(field, []) or []:
                    if claim.get("review_status") != vocab.REVIEW_DEV_CONFIRMED:
                        continue
                    item_id = f"{analysis['analysis_id']}:{claim.get('claim_id')}"
                    out.append({
                        "item_id": item_id,
                        "analysis_id": analysis["analysis_id"],
                        "unit_id": analysis["unit_id"],
                        "scope": field,
                        "text": claim.get("text", ""),
                        "eligible": not stale,
                        "reason": "ok" if not stale else "stale_source",
                        "confidence": claim.get("confidence", analysis.get("confidence", vocab.CONFIDENCE_LOW)),
                    })
        return out

    def promote(self, item_id: str, *, promoted_by: str = "developer") -> dict[str, Any]:
        candidate = next((c for c in self.candidates() if c["item_id"] == item_id), None)
        if candidate is None:
            raise NotFoundError(f"no promotable confirmed claim: {item_id}")
        if not candidate["eligible"]:
            raise GroundrailError(f"claim cannot be promoted: {candidate['reason']}")
        facts = self._load_facts()
        if any(f.get("source_item_id") == item_id for f in facts):
            return next(f for f in facts if f.get("source_item_id") == item_id)
        fact = {
            "fact_id": f"fact.{uuid.uuid4().hex[:12]}",
            "source_item_id": item_id,
            "analysis_id": candidate["analysis_id"],
            "unit_id": candidate["unit_id"],
            "scope": candidate["scope"],
            "text": candidate["text"],
            "state": vocab.STATUS_INFERRED,
            "confidence": candidate["confidence"],
            "review_status": vocab.REVIEW_DEV_CONFIRMED,
            "promoted_by": promoted_by,
            "promoted_at": timeutil.now_iso(),
            "promotion_policy": "developer_confirmed_non_stale_claim_only",
        }
        facts.append(fact)
        self._write_facts(facts)
        self.store.append_jsonl(PROMOTED_PATH, fact)
        self._write_report({"status": "ok", "promoted": 1, "fact_id": fact["fact_id"]})
        return fact

    def get(self, fact_id: str) -> dict[str, Any]:
        for fact in self._load_facts():
            if fact.get("fact_id") == fact_id:
                return fact
        raise NotFoundError(f"unknown fact: {fact_id}")

    def all(self) -> list[dict[str, Any]]:
        return self._load_facts()

    def _load_facts(self) -> list[dict[str, Any]]:
        if not self.store.exists(FACTS_PATH):
            return []
        return self.store.read_json(FACTS_PATH).get("data", {}).get("facts", [])

    def _write_facts(self, facts: list[dict[str, Any]]) -> None:
        artifact = envelope.build_envelope(
            artifact_id="groundrail.knowledge.facts",
            artifact_kind="knowledge_facts",
            generator=envelope.make_generator("groundrail promote", "groundrail.knowledge"),
            source=envelope.make_source(),
            data={"facts": facts, "count": len(facts)},
        )
        self.store.write_json(FACTS_PATH, artifact)

    def _write_report(self, data: dict[str, Any]) -> None:
        artifact = envelope.build_envelope(
            artifact_id="groundrail.audit.promotion",
            artifact_kind="promotion_report",
            generator=envelope.make_generator("groundrail promote", "groundrail.knowledge"),
            source=envelope.make_source(),
            data=data,
        )
        self.store.write_json(PROMOTION_REPORT_PATH, artifact)
