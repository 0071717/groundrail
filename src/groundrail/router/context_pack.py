"""Context-pack builder.

Selects the strongest available evidence for a request, under a token budget,
with explicit inclusion rules (docs/09): stale items are excluded from support,
low-confidence inferred analyses are excluded by default, and every item keeps
its state/confidence/review status so Kiro can see what is solid vs. guessed.
"""

from __future__ import annotations

from typing import Any

from ..core import timeutil, vocab
from ..core.gaps import CapabilityGapRegistry
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..analyzer.store import AnalysisStore
from ..indexer.unit_index import UnitStore
from ..knowledge import KnowledgeStore
from .retrieval import RetrievalIndex, RetrievalIndexBuilder, tokenize
from .session import SessionStore

DEFAULT_TOKEN_BUDGET = 6000


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ContextPackBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)
        self.knowledge = KnowledgeStore(self.store)
        self.sessions = SessionStore(self.store)

    def build(
        self,
        *,
        mode: str,
        request: str,
        allow_inferred_low: bool = False,
        token_budget: int | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if mode not in vocab.CONTEXT_MODES:
            from ..core.errors import GroundrailError

            raise GroundrailError(
                f"unknown mode {mode!r}; expected one of {sorted(vocab.CONTEXT_MODES)}"
            )
        budget = token_budget or self._configured_budget()

        RetrievalIndexBuilder(self.workspace).build(command="groundrail prepare")
        results = RetrievalIndex(self.store).search(request, limit=40)

        selected_units: list[dict[str, Any]] = []
        selected_analyses: list[dict[str, Any]] = []
        selected_notes: list[dict[str, Any]] = []
        selected_facts = self._matching_facts(request)
        stale_items: list[str] = []
        explain: list[dict[str, Any]] = []
        used = sum(estimate_tokens(f.get("text", "")) for f in selected_facts)
        seen_units: set[str] = set()

        for row in results:
            unit_id = row["unit_id"]
            if unit_id in seen_units:
                continue
            unit = self.units.get(unit_id)
            analysis = self.analyses.try_get(unit_id)

            decision, reason = self._decide(unit, analysis, allow_inferred_low)
            if decision != "include":
                explain.append({"item_id": unit_id, "decision": decision, "reason": reason})
                if reason == "stale_analysis":
                    stale_items.append(unit_id)
                continue

            entry = self._unit_entry(unit)
            cost = estimate_tokens(entry["summary"] + entry["snippet"])
            if used + cost > budget:
                explain.append({"item_id": unit_id, "decision": "excluded", "reason": "token_budget"})
                continue

            used += cost
            seen_units.add(unit_id)
            selected_units.append(entry["source_evidence"])
            if analysis is not None:
                selected_analyses.append(self._analysis_entry(unit, analysis))
                selected_notes.extend(self._notable_notes(unit, analysis))
            explain.append(
                {"item_id": unit_id, "decision": "included", "reason": reason, "tokens": cost}
            )

        gaps = CapabilityGapRegistry(self.store).load()
        pack = {
            "schema_version": "1",
            "session_id": session_id or "",
            "mode": mode,
            "request": request,
            "created_at": timeutil.now_iso(),
            "freshness": {
                "status": "stale" if stale_items else "ok",
                "stale_items": stale_items,
            },
            "token_budget": budget,
            "tokens_used": used,
            "selected_facts": selected_facts,
            "selected_unit_analyses": selected_analyses,
            "selected_ai_notes": selected_notes,
            "selected_flows": [],
            "source_evidence": selected_units,
            "known_gaps": gaps[:10],
            "citation_rules": {
                "required_block": vocab.CITATION_BLOCK_TAG,
                "unsupported_phrase": vocab.UNSUPPORTED_PHRASE,
            },
        }

        sid = session_id or self.sessions.create()
        pack["session_id"] = sid
        self.sessions.write(sid, "context-pack.json", pack)
        self.sessions.write_text(sid, "context-pack.md", self.render_markdown(pack))
        self.sessions.write(
            sid, "selection-explain.json", {"request": request, "decisions": explain}
        )
        return pack

    # --- selection rules -----------------------------------------------------
    def _decide(
        self, unit: dict[str, Any], analysis: dict[str, Any] | None, allow_inferred_low: bool
    ) -> tuple[str, str]:
        if analysis is None:
            return "include", "unit_only"
        if self.analyses.is_stale(analysis, unit):
            return "excluded", "stale_analysis"
        if analysis["state"] == vocab.STATUS_STALE:
            return "excluded", "stale_analysis"
        if (
            analysis["state"] == vocab.STATUS_INFERRED
            and analysis["confidence"] == vocab.CONFIDENCE_LOW
            and analysis.get("review_status") != vocab.REVIEW_DEV_CONFIRMED
            and not allow_inferred_low
        ):
            return "excluded", "inferred_low_confidence"
        return "include", f"{analysis['state']}/{analysis['confidence']}"

    # --- entry builders ------------------------------------------------------
    def _unit_entry(self, unit: dict[str, Any]) -> dict[str, Any]:
        span = unit["span"]
        return {
            "summary": f"{unit['symbol']} ({unit['kind']})",
            "snippet": unit.get("qualified_name", unit["symbol"]),
            "source_evidence": {
                "unit_id": unit["unit_id"],
                "file_path": unit["file_path"],
                "symbol": unit["symbol"],
                "span": span,
                "state": unit["state"],
                "confidence": unit["confidence"],
            },
        }

    def _analysis_entry(self, unit: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "analysis_id": analysis["analysis_id"],
            "unit_id": unit["unit_id"],
            "symbol": unit["symbol"],
            "summary": analysis.get("summary", ""),
            "state": analysis["state"],
            "confidence": analysis["confidence"],
            "review_status": analysis.get("review_status", "unreviewed"),
            "intent": [c["text"] for c in analysis.get("intent", [])],
            "uncertainties": [u["text"] for u in analysis.get("uncertainties", [])],
        }

    def _matching_facts(self, request: str) -> list[dict[str, Any]]:
        facts = self.knowledge.all()
        if not facts:
            return []
        request_tokens = set(tokenize(request))
        ranked: list[tuple[int, dict[str, Any]]] = []
        for fact in facts:
            text_tokens = set(tokenize(fact.get("text", "")))
            score = len(request_tokens & text_tokens)
            if score or not request_tokens:
                ranked.append((score, fact))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [fact for _, fact in ranked[:10]]

    def _notable_notes(self, unit: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for note in analysis.get("ai_notes", []):
            if note.get("severity") in ("critical", "high", "medium") and note.get("confidence", 0) >= 0.65:
                out.append(
                    {
                        "unit_id": unit["unit_id"],
                        "type": note["type"],
                        "severity": note["severity"],
                        "text": note["text"],
                        "review_status": note.get("review_status", "unreviewed"),
                    }
                )
        return out

    def _configured_budget(self) -> int:
        try:
            return int(
                self.workspace.load_config().get("context_pack", {}).get(
                    "token_budget", DEFAULT_TOKEN_BUDGET
                )
            )
        except Exception:  # noqa: BLE001
            return DEFAULT_TOKEN_BUDGET

    # --- markdown view -------------------------------------------------------
    def render_markdown(self, pack: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append(f"# Groundrail context pack ({pack['mode']})")
        lines.append("")
        lines.append(f"**Request:** {pack['request']}")
        lines.append(f"**Freshness:** {pack['freshness']['status']}")
        if pack["freshness"]["stale_items"]:
            lines.append(f"**Stale (excluded from support):** {', '.join(pack['freshness']['stale_items'])}")
        lines.append("")

        if pack["selected_facts"]:
            lines.append("## Developer-confirmed promoted facts")
            for fact in pack["selected_facts"]:
                lines.append(
                    f"- [{fact['state']}/{fact['confidence']}/{fact['review_status']}] "
                    f"{fact['text']} (`{fact['fact_id']}` from `{fact['source_item_id']}`)"
                )
            lines.append("")

        confirmed = [a for a in pack["selected_unit_analyses"] if a["review_status"] == "dev_confirmed"]
        inferred = [a for a in pack["selected_unit_analyses"] if a["review_status"] != "dev_confirmed"]

        if confirmed:
            lines.append("## Developer-confirmed analyses")
            for a in confirmed:
                lines.append(self._analysis_md(a))
            lines.append("")
        if inferred:
            lines.append("## AI-inferred analyses (not confirmed)")
            for a in inferred:
                lines.append(self._analysis_md(a))
            lines.append("")

        lines.append("## Source evidence (inspect these first)")
        for ev in pack["source_evidence"]:
            s = ev["span"]
            lines.append(
                f"- `{ev['symbol']}` — {ev['file_path']}:{s['start_line']}-{s['end_line']} "
                f"[{ev['state']}/{ev['confidence']}] (`{ev['unit_id']}`)"
            )
        lines.append("")

        if pack["selected_ai_notes"]:
            lines.append("## AI notes worth attention")
            for n in pack["selected_ai_notes"]:
                lines.append(f"- [{n['severity']}] {n['type']}: {n['text']} (`{n['unit_id']}`)")
            lines.append("")

        if pack["known_gaps"]:
            lines.append("## Known capability gaps")
            for g in pack["known_gaps"]:
                lines.append(f"- {g.get('kind')}: {g.get('detail')} ({g.get('location')})")
            lines.append("")

        rules = pack["citation_rules"]
        lines.append("## Mandatory citation contract")
        lines.append(
            f"You MUST end every answer with exactly one `<{rules['required_block']}>` JSON block. "
            "Every substantive claim in your answer must have one entry in `claims`. "
            f"For anything not supported by the ids in this context pack, write \"{rules['unsupported_phrase']}\" "
            "in the answer text and set support to `not_confirmed`."
        )
        lines.append("")
        lines.append("Allowed support values: `supported`, `inferred`, `not_confirmed`, `contradicted`.")
        lines.append("Use `supported` only for source evidence or developer-confirmed promoted facts. Use `inferred` for AI analysis.")
        lines.append("Do not invent ids. Do not cite stale or missing ids. Do not present inferred analyses as verified.")
        lines.append("")
        lines.append("Citation block schema:")
        lines.append("```json")
        lines.append("{")
        lines.append('  "claims": [')
        lines.append("    {")
        lines.append('      "claim_id": "claim-001",')
        lines.append('      "text": "Short paraphrase of the claim",')
        lines.append('      "support": "supported",')
        lines.append('      "fact_ids": [],')
        lines.append('      "unit_ids": [],')
        lines.append('      "analysis_ids": [],')
        lines.append('      "evidence_ids": []')
        lines.append("    }")
        lines.append("  ]")
        lines.append("}")
        lines.append("```")
        lines.append(f"Wrap only the JSON object, not the fenced code block, in `<{rules['required_block']}>...</{rules['required_block']}>`.")
        return "\n".join(lines) + "\n"

    def _analysis_md(self, a: dict[str, Any]) -> str:
        parts = [
            f"- **{a['symbol']}** [{a['state']}/{a['confidence']}] (`{a['analysis_id']}`): {a['summary']}"
        ]
        for u in a.get("uncertainties", []):
            parts.append(f"    - uncertainty: {u}")
        return "\n".join(parts)
