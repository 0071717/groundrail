"""View models: plain-data snapshots assembled from Groundrail services.

Every function here returns dicts/lists only — no curses, no I/O beyond the
service stores — so the whole TUI data layer is unit-testable without a terminal.
"""

from __future__ import annotations

from typing import Any

from ..analyzer.store import AnalysisStore
from ..core.gaps import CapabilityGapRegistry
from ..core.workspace import Workspace
from ..flow.graph import Graph, GraphBuilder
from ..indexer.snapshot import FILE_INDEX_PATH, load_file_index
from ..indexer.unit_index import UnitStore
from ..router.session import SessionStore

SCREENS = ("dashboard", "units", "sessions", "gaps")


class ViewModelBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.ws = workspace
        self.store = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)
        self.sessions = SessionStore(self.store)
        self._graph: Graph | None = None

    @property
    def graph(self) -> Graph:
        if self._graph is None:
            self._graph = GraphBuilder(self.ws).build(write=False)
        return self._graph

    # --- dashboard -----------------------------------------------------------
    def dashboard(self) -> dict[str, Any]:
        units = self.units.all()
        analyses = self.analyses.all()
        analysed_ids = {a["unit_id"] for a in analyses}
        units_by_id = {u["unit_id"]: u for u in units}
        stale = sum(
            1 for a in analyses
            if a["unit_id"] in units_by_id and self.analyses.is_stale(a, units_by_id[a["unit_id"]])
        )
        kinds: dict[str, int] = {}
        for u in units:
            kinds[u["kind"]] = kinds.get(u["kind"], 0) + 1
        return {
            "files": len(load_file_index(self.store)) if self.store.exists(FILE_INDEX_PATH) else 0,
            "units": len(units),
            "analysed": len(analysed_ids),
            "unanalysed": len(units) - len(analysed_ids),
            "stale": stale,
            "kinds": sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0])),
            "gaps": len(CapabilityGapRegistry(self.store).load()),
            "sessions": self._session_ids(),
            "latest_session": self._latest_session_brief(),
        }

    # --- units ---------------------------------------------------------------
    def units_rows(self) -> list[dict[str, Any]]:
        analysed = {a["unit_id"]: a for a in self.analyses.all()}
        rows = []
        for u in self.units.all():
            a = analysed.get(u["unit_id"])
            rows.append({
                "unit_id": u["unit_id"],
                "kind": u["kind"],
                "symbol": u["symbol"],
                "file_path": u["file_path"],
                "span": u["span"],
                "complexity": u["complexity"]["state"],
                "state": u["state"],
                "confidence": u["confidence"],
                "analysis_state": a["state"] if a else None,
                "review_status": (a or {}).get("review_status"),
            })
        return rows

    def unit_detail(self, unit_id: str) -> dict[str, Any]:
        unit = self.units.get(unit_id)
        analysis = self.analyses.try_get(unit_id)
        callees = [
            {"unit_id": e["to_unit"], "symbol": self._sym(e["to_unit"]), "confidence": e["confidence"]}
            for e in self.graph.out_edges(unit_id)
        ]
        callers = [
            {"unit_id": e["from_unit"], "symbol": self._sym(e["from_unit"]), "confidence": e["confidence"]}
            for e in self.graph.in_edges(unit_id)
        ]
        return {
            "unit": unit,
            "analysis": analysis,
            "callees": callees,
            "callers": callers,
            "source": self._source_lines(unit),
        }

    # --- sessions ------------------------------------------------------------
    def sessions_rows(self) -> list[dict[str, Any]]:
        rows = []
        for sid in self._session_ids():
            brief = {"session_id": sid, "mode": "", "request": "", "audit": ""}
            if self.sessions.has(sid, "context-pack.json"):
                pack = self.sessions.read(sid, "context-pack.json")
                brief["mode"] = pack.get("mode", "")
                brief["request"] = pack.get("request", "")
                brief["freshness"] = pack.get("freshness", {}).get("status", "")
            if self.sessions.has(sid, "audit.json"):
                brief["audit"] = self.sessions.read(sid, "audit.json").get("status", "")
            rows.append(brief)
        return rows

    def session_detail(self, session_id: str) -> dict[str, Any]:
        detail: dict[str, Any] = {"session_id": session_id}
        if self.sessions.has(session_id, "context-pack.md"):
            detail["pack_md"] = self.store.resolve(
                f"sessions/{session_id}/context-pack.md"
            ).read_text(encoding="utf-8")
        if self.sessions.has(session_id, "kiro-output.raw.md"):
            detail["answer"] = self.store.resolve(
                f"sessions/{session_id}/kiro-output.raw.md"
            ).read_text(encoding="utf-8")
        if self.sessions.has(session_id, "audit.json"):
            detail["audit"] = self.sessions.read(session_id, "audit.json")
        return detail

    # --- gaps ----------------------------------------------------------------
    def gaps_rows(self) -> list[dict[str, Any]]:
        return CapabilityGapRegistry(self.store).load()

    # --- helpers -------------------------------------------------------------
    def _sym(self, unit_id: str) -> str:
        node = self.graph.node(unit_id)
        return node["symbol"] if node else unit_id

    def _session_ids(self) -> list[str]:
        sessions_dir = self.store.resolve("sessions")
        if not sessions_dir.is_dir():
            return []
        return sorted(
            (p.name for p in sessions_dir.iterdir() if p.is_dir() and p.name.startswith("session-")),
            reverse=True,
        )

    def _latest_session_brief(self) -> dict[str, Any] | None:
        ids = self._session_ids()
        if not ids:
            return None
        rows = self.sessions_rows()
        return rows[0] if rows else None

    def _source_lines(self, unit: dict[str, Any], limit: int = 60) -> list[str]:
        try:
            repo_root = self.ws.repo_root(unit["repo"])
            text = (repo_root / unit["file_path"]).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return []
        span = unit["span"]
        lines = text.splitlines()[span["start_line"] - 1 : span["end_line"]]
        return lines[:limit]
