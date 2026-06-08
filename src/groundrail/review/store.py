"""Human review store for AI analyses, claims, and notes.

This is intentionally conservative: confirmations never rewrite source truth or
turn AI analysis into ``verified``. They only attach source-version-bound human
review status to an analysis, claim, or note.
"""

from __future__ import annotations

from typing import Any

from ..analyzer.store import AnalysisStore, analysis_path
from ..core import envelope, timeutil, vocab
from ..core.errors import GroundrailError, NotFoundError
from ..core.store import ArtifactStore
from ..indexer.unit_index import UnitStore

REVIEWS_PATH = "review/reviews.jsonl"
CONFIRMED_PATH = "review/confirmed-items.jsonl"
REJECTED_PATH = "review/rejected-items.jsonl"
STALE_CONFIRMATIONS_PATH = "audit/stale-confirmations.json"


class ReviewStore:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self.analyses = AnalysisStore(store)
        self.units = UnitStore(store)

    def queue(self) -> list[dict[str, Any]]:
        """Return reviewable summaries, claims, uncertainties, and AI notes."""
        out: list[dict[str, Any]] = []
        units = {u["unit_id"]: u for u in self.units.all()}
        for analysis in self.analyses.all():
            unit = units.get(analysis["unit_id"])
            stale = bool(unit and self.analyses.is_stale(analysis, unit))
            out.append(self._item(analysis, "unit_summary", analysis["analysis_id"], analysis.get("summary", ""), analysis.get("review_status"), stale))
            for field in ("intent", "inputs", "outputs", "side_effects", "state_access", "calls", "errors", "behavioral_notes"):
                for claim in analysis.get(field, []) or []:
                    item_id = f"{analysis['analysis_id']}:{claim.get('claim_id')}"
                    out.append(self._item(analysis, field, item_id, claim.get("text", ""), claim.get("review_status"), stale))
            for i, note in enumerate(analysis.get("ai_notes", []) or []):
                item_id = f"{analysis['analysis_id']}:note.{i}"
                text = f"[{note.get('severity', '?')}] {note.get('type', '?')}: {note.get('text', '')}"
                out.append(self._item(analysis, "ai_note", item_id, text, note.get("review_status"), stale))
            for i, uncertainty in enumerate(analysis.get("uncertainties", []) or []):
                item_id = f"{analysis['analysis_id']}:uncertainty.{i}"
                out.append(self._item(analysis, "uncertainty", item_id, uncertainty.get("text", ""), vocab.REVIEW_NEEDS_REVIEW, stale))
        return out

    def get_item(self, item_id: str) -> dict[str, Any]:
        for item in self.queue():
            if item["item_id"] == item_id:
                return item
        raise NotFoundError(f"unknown review item: {item_id}")

    def confirm(self, item_id: str, *, reviewer: str = "developer", note: str = "") -> dict[str, Any]:
        return self._set_review(item_id, vocab.REVIEW_DEV_CONFIRMED, reviewer=reviewer, note=note)

    def reject(self, item_id: str, *, reviewer: str = "developer", note: str = "") -> dict[str, Any]:
        return self._set_review(item_id, vocab.REVIEW_DEV_REJECTED, reviewer=reviewer, note=note)

    def stale_confirmations(self) -> dict[str, Any]:
        units = {u["unit_id"]: u for u in self.units.all()}
        stale: list[dict[str, Any]] = []
        for analysis in self.analyses.all():
            unit = units.get(analysis["unit_id"])
            if not unit or not self.analyses.is_stale(analysis, unit):
                continue
            if analysis.get("review_status") == vocab.REVIEW_DEV_CONFIRMED:
                stale.append({"item_id": analysis["analysis_id"], "unit_id": analysis["unit_id"], "scope": "unit_summary"})
            for field in ("intent", "inputs", "outputs", "side_effects", "state_access", "calls", "errors", "behavioral_notes"):
                for claim in analysis.get(field, []) or []:
                    if claim.get("review_status") == vocab.REVIEW_DEV_CONFIRMED:
                        stale.append({
                            "item_id": f"{analysis['analysis_id']}:{claim.get('claim_id')}",
                            "unit_id": analysis["unit_id"],
                            "scope": field,
                        })
        result = {"status": "stale" if stale else "ok", "count": len(stale), "items": stale}
        artifact = envelope.build_envelope(
            artifact_id="groundrail.audit.stale_confirmations",
            artifact_kind="stale_confirmations",
            generator=envelope.make_generator("groundrail review stale", "groundrail.review"),
            source=envelope.make_source(),
            data=result,
        )
        self.store.write_json(STALE_CONFIRMATIONS_PATH, artifact)
        return result

    def _item(self, analysis: dict[str, Any], scope: str, item_id: str, text: str, review_status: str | None, stale: bool) -> dict[str, Any]:
        return {
            "item_id": item_id,
            "analysis_id": analysis["analysis_id"],
            "unit_id": analysis["unit_id"],
            "scope": scope,
            "text": text,
            "state": vocab.STATUS_STALE if stale else analysis.get("state", vocab.STATUS_INFERRED),
            "confidence": analysis.get("confidence", vocab.CONFIDENCE_LOW),
            "review_status": review_status or vocab.REVIEW_UNREVIEWED,
            "stale": stale,
        }

    def _set_review(self, item_id: str, status: str, *, reviewer: str, note: str) -> dict[str, Any]:
        if status not in (vocab.REVIEW_DEV_CONFIRMED, vocab.REVIEW_DEV_REJECTED):
            raise GroundrailError(f"unsupported review status: {status}")
        analysis_id = item_id.split(":", 1)[0]
        analysis = self._analysis_by_id(analysis_id)
        changed = self._apply_status(analysis, item_id, status)
        if not changed:
            raise NotFoundError(f"unknown review item: {item_id}")
        record = {
            "review_id": f"review.{timeutil.compact_id()}",
            "item_id": item_id,
            "analysis_id": analysis_id,
            "unit_id": analysis["unit_id"],
            "status": status,
            "reviewer": reviewer,
            "note": note,
            "created_at": timeutil.now_iso(),
            "source_commit": analysis.get("analysis_provenance", {}).get("source_commit", "unknown"),
            "unit_hash": analysis.get("analysis_provenance", {}).get("unit_hash", "unknown"),
        }
        self._write_analysis(analysis)
        self.store.append_jsonl(REVIEWS_PATH, record)
        self.store.append_jsonl(CONFIRMED_PATH if status == vocab.REVIEW_DEV_CONFIRMED else REJECTED_PATH, record)
        return record

    def _analysis_by_id(self, analysis_id: str) -> dict[str, Any]:
        for analysis in self.analyses.all():
            if analysis.get("analysis_id") == analysis_id:
                return analysis
        raise NotFoundError(f"unknown analysis: {analysis_id}")

    def _apply_status(self, analysis: dict[str, Any], item_id: str, status: str) -> bool:
        if item_id == analysis["analysis_id"]:
            analysis["review_status"] = status
            analysis["review"] = {"status": status, "updated_at": timeutil.now_iso()}
            return True
        suffix = item_id.split(":", 1)[1] if ":" in item_id else ""
        for field in ("intent", "inputs", "outputs", "side_effects", "state_access", "calls", "errors", "behavioral_notes"):
            for claim in analysis.get(field, []) or []:
                if claim.get("claim_id") == suffix:
                    claim["review_status"] = status
                    return True
        if suffix.startswith("note."):
            try:
                idx = int(suffix.split(".", 1)[1])
                analysis.get("ai_notes", [])[idx]["review_status"] = status
                return True
            except (ValueError, IndexError, TypeError):
                return False
        return False

    def _write_analysis(self, analysis: dict[str, Any]) -> None:
        path = analysis_path(analysis["unit_id"])
        old = self.store.read_json(path)
        old["data"] = analysis
        self.store.write_json(path, old)
