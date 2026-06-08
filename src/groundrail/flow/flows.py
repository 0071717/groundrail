"""Unit and endpoint flow composition."""

from __future__ import annotations

from typing import Any

from ..core import envelope
from ..core.errors import NotFoundError
from ..core.workspace import Workspace
from .graph import Graph, GraphBuilder
from .semantics import cap_at_inferred, weakest_confidence, weakest_state
from .traverse import propagate

UNIT_FLOWS_PATH = "flows/unit-flows.json"
ENDPOINT_FLOWS_PATH = "flows/endpoint-flows.json"


class FlowComposer:
    def __init__(self, workspace: Workspace, *, graph: Graph | None = None) -> None:
        self.workspace = workspace
        self.store = workspace.store
        self.graph = graph or GraphBuilder(workspace).build()

    def unit_flow(self, unit_id: str, *, depth: int = 4) -> dict[str, Any]:
        if self.graph.node(unit_id) is None:
            raise NotFoundError(f"unknown unit: {unit_id}")
        callees = propagate(self.graph, [unit_id], direction="out", depth=depth)
        callers = propagate(self.graph, [unit_id], direction="in", depth=depth)
        flow = {
            "unit_id": unit_id,
            "direct_callees": self._direct(unit_id, "out"),
            "direct_callers": self._direct(unit_id, "in"),
            "transitive_callees": self._reached(callees, unit_id),
            "transitive_callers": self._reached(callers, unit_id),
            "confidence": self._overall_confidence(callees, unit_id),
            "state": self._overall_state(callees, unit_id),
        }
        self.store.write_json(UNIT_FLOWS_PATH, self._wrap(flow, "unit_flow"))
        return flow

    def endpoint_flow(self, method: str, path: str, *, depth: int = 6) -> dict[str, Any]:
        root = self._find_endpoint(method, path)
        if root is None:
            raise NotFoundError(f"no endpoint handler for {method} {path}")
        reached = propagate(self.graph, [root], direction="out", depth=depth)
        flow = {
            "endpoint": {"method": method.upper(), "path": path},
            "root_unit": root,
            "nodes": self._reached(reached, None),
            "confidence": self._overall_confidence(reached, root),
            "state": self._overall_state(reached, root),
            "depth": max((r["distance"] for r in reached.values()), default=0),
        }
        self.store.write_json(ENDPOINT_FLOWS_PATH, self._wrap(flow, "endpoint_flow"))
        return flow

    # --- helpers -------------------------------------------------------------
    def _direct(self, unit_id: str, direction: str) -> list[dict[str, Any]]:
        edges = self.graph.out_edges(unit_id) if direction == "out" else self.graph.in_edges(unit_id)
        out = []
        for edge in edges:
            other = edge["to_unit"] if direction == "out" else edge["from_unit"]
            node = self.graph.node(other)
            out.append({
                "unit_id": other,
                "symbol": node["symbol"] if node else other,
                "confidence": edge["confidence"],
                "via": edge["via"],
            })
        return out

    def _reached(self, reached: dict[str, dict[str, Any]], seed: str | None) -> list[dict[str, Any]]:
        out = []
        for uid, info in reached.items():
            if uid == seed:
                continue
            node = self.graph.node(uid)
            out.append({
                "unit_id": uid,
                "symbol": node["symbol"] if node else uid,
                "file_path": node["file_path"] if node else "",
                "distance": info["distance"],
                "confidence": info["confidence"],
                "state": info["state"],
            })
        return sorted(out, key=lambda r: (r["distance"], r["unit_id"]))

    def _overall_confidence(self, reached: dict[str, dict[str, Any]], seed: str) -> str:
        return weakest_confidence([info["confidence"] for info in reached.values()] or
                                  [self.graph.node(seed)["eff_confidence"]])

    def _overall_state(self, reached: dict[str, dict[str, Any]], seed: str) -> str:
        return cap_at_inferred(
            weakest_state([info["state"] for info in reached.values()] or
                          [self.graph.node(seed)["eff_state"]])
        )

    def _find_endpoint(self, method: str, path: str) -> str | None:
        method = method.upper()
        for uid, node in self.graph.nodes.items():
            if node["kind"] != "fastapi_endpoint_handler":
                continue
            for ep in node.get("endpoints", []):
                if ep.get("method", "").upper() == method and ep.get("path") == path:
                    return uid
        return None

    def _wrap(self, data: dict[str, Any], kind: str) -> dict[str, Any]:
        return envelope.build_envelope(
            artifact_id=f"groundrail.flow.{kind}",
            artifact_kind=kind,
            generator=envelope.make_generator(f"groundrail flow {kind}", "groundrail.flow"),
            source=envelope.make_source(),
            data=data,
        )
