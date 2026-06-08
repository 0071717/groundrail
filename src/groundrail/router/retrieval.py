"""Retrieval index over units and analyses, with simple keyword scoring.

No SQLite, no embeddings: a JSONL index plus token-overlap scoring. This is
deliberately boring and deterministic; relevance quality is measured by the eval
harness, not assumed.
"""

from __future__ import annotations

import re
from typing import Any

from ..core import envelope
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..analyzer.store import AnalysisStore
from ..indexer.unit_index import UnitStore

RETRIEVAL_PATH = "cache/retrieval-index.jsonl"

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN.findall(text or ""):
        lowered = raw.lower()
        out.append(lowered)
        # split snake_case / camelCase so "search_users" matches "search"
        out.extend(p.lower() for p in re.split(r"_|(?<=[a-z])(?=[A-Z])", raw) if p)
    return out


def _priority_from_complexity(state: str) -> float:
    return {"complex": 0.9, "moderate": 0.6, "simple": 0.4}.get(state, 0.5)


class RetrievalIndexBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)

    def build(self, *, command: str = "groundrail search") -> int:
        rows: list[dict[str, Any]] = []
        analyses = {a["unit_id"]: a for a in self.analyses.all()}
        for unit in self.units.all():
            rows.append(self._unit_row(unit))
            analysis = analyses.get(unit["unit_id"])
            if analysis is not None:
                rows.append(self._analysis_row(unit, analysis))
        self.store.write_jsonl(RETRIEVAL_PATH, rows)
        # marker artifact so `validate` sees an enveloped record of the build
        self.store.write_json(
            "cache/retrieval-index.meta.json",
            envelope.build_envelope(
                artifact_id="groundrail.cache.retrieval",
                artifact_kind="retrieval_index_meta",
                generator=envelope.make_generator(command, "groundrail.router"),
                source=envelope.make_source(),
                data={"row_count": len(rows)},
            ),
        )
        return len(rows)

    def _unit_row(self, unit: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": unit["unit_id"],
            "item_type": "unit",
            "title": unit["symbol"],
            "text": f"{unit.get('qualified_name', unit['symbol'])} {unit['kind']}",
            "path": unit["file_path"],
            "symbol": unit["symbol"],
            "unit_id": unit["unit_id"],
            "analysis_id": "",
            "fact_id": "",
            "priority": _priority_from_complexity(unit["complexity"]["state"]),
            "state": unit["state"],
            "confidence": unit["confidence"],
            "review_status": "unreviewed",
        }

    def _analysis_row(self, unit: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": analysis["analysis_id"],
            "item_type": "unit_analysis",
            "title": unit["symbol"],
            "text": analysis.get("summary", ""),
            "path": unit["file_path"],
            "symbol": unit["symbol"],
            "unit_id": unit["unit_id"],
            "analysis_id": analysis["analysis_id"],
            "fact_id": "",
            "priority": 0.7,
            "state": analysis["state"],
            "confidence": analysis["confidence"],
            "review_status": analysis.get("review_status", "unreviewed"),
        }


class RetrievalIndex:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def rows(self) -> list[dict[str, Any]]:
        return self.store.read_jsonl(RETRIEVAL_PATH)

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self.rows():
            haystack = set(
                tokenize(f"{row['title']} {row['text']} {row['symbol']} {row['path']}")
            )
            overlap = len(q_tokens & haystack)
            if overlap == 0:
                continue
            score = overlap + float(row.get("priority", 0.5))
            scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in scored[:limit]]
