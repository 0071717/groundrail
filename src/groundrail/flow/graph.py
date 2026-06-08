"""Call and cross-layer graph construction.

Besides symbol-call edges, this graph links frontend API call candidates to
FastAPI endpoint handlers and backend search/data-access units to OpenSearch
resource nodes. These links are inferred and confidence-labelled; they make
impact analysis visible without pretending to be compiler/runtime proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..analyzer.store import AnalysisStore
from ..core import envelope, vocab
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..indexer.opensearch import load_opensearch_resources
from ..indexer.unit_index import UnitStore

NODES_PATH = "graph/nodes.json"
EDGES_PATH = "graph/edges.json"


@dataclass
class Graph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    out_adj: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    in_adj: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def out_edges(self, unit_id: str) -> list[dict[str, Any]]:
        return self.out_adj.get(unit_id, [])

    def in_edges(self, unit_id: str) -> list[dict[str, Any]]:
        return self.in_adj.get(unit_id, [])

    def node(self, unit_id: str) -> dict[str, Any] | None:
        return self.nodes.get(unit_id)


def _trailing_symbol(target_text: str) -> str:
    base = target_text.split("(")[0].strip()
    return base.split(".")[-1]


def _norm_path(path: str) -> str:
    path = (path or "").split("?", 1)[0].strip()
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith("/api/"):
        path = path[4:]
    return path.rstrip("/") or "/"


class GraphBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)

    def build(self, *, write: bool = True, command: str = "groundrail graph build") -> Graph:
        units = self.units.all()
        analyses = {a["unit_id"]: a for a in self.analyses.all()}
        resources = load_opensearch_resources(self.store)

        symbol_index: dict[str, list[str]] = {}
        endpoint_index: dict[tuple[str, str], list[str]] = {}
        for unit in units:
            symbol_index.setdefault(unit["symbol"], []).append(unit["unit_id"])
            for ep in unit.get("related_candidates", {}).get("endpoint_candidates", []) or []:
                endpoint_index.setdefault((ep.get("method", "GET").upper(), _norm_path(ep.get("path", ""))), []).append(unit["unit_id"])

        graph = Graph()
        for unit in units:
            self._add_node(graph, unit["unit_id"], self._node(unit, analyses.get(unit["unit_id"])))
        for resource in resources:
            rid = resource["resource_id"]
            self._add_node(graph, rid, {
                "unit_id": rid,
                "kind": "opensearch_resource",
                "repo": resource["repo"],
                "file_path": resource["file_path"],
                "symbol": resource["name"],
                "span": {"start_line": 1, "end_line": 1, "start_col": 1, "end_col": 1},
                "unit_state": resource["state"],
                "review_status": "unreviewed",
                "has_analysis": False,
                "stale": False,
                "eff_state": resource["state"],
                "eff_confidence": resource["confidence"],
                "endpoints": [],
                "resource": resource,
            })

        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for unit in units:
            src = unit["unit_id"]
            self._symbol_edges(unit, symbol_index, edges)
            self._frontend_api_edges(unit, endpoint_index, edges)
            self._opensearch_edges(unit, resources, edges)

        for edge in edges.values():
            graph.out_adj.setdefault(edge["from_unit"], []).append(edge)
            graph.in_adj.setdefault(edge["to_unit"], []).append(edge)

        if write:
            self._write(graph, list(edges.values()), command)
        return graph

    def _add_node(self, graph: Graph, node_id: str, node: dict[str, Any]) -> None:
        graph.nodes[node_id] = node
        graph.out_adj.setdefault(node_id, [])
        graph.in_adj.setdefault(node_id, [])

    def _symbol_edges(self, unit: dict[str, Any], symbol_index: dict[str, list[str]], edges: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        src = unit["unit_id"]
        for cand in unit.get("call_candidates", []):
            base = _trailing_symbol(cand["target_text"])
            matches = symbol_index.get(base, [])
            if not matches:
                continue
            edge_conf = vocab.CONFIDENCE_MEDIUM if len(matches) == 1 else vocab.CONFIDENCE_LOW
            for dst in matches:
                if dst == src:
                    continue
                self._add_edge(edges, src, dst, "call_candidate", cand["target_text"], cand.get("span", {}).get("start_line", 0), edge_conf)

    def _frontend_api_edges(self, unit: dict[str, Any], endpoint_index: dict[tuple[str, str], list[str]], edges: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        src = unit["unit_id"]
        for api in unit.get("related_candidates", {}).get("api_call_candidates", []) or []:
            key = (api.get("method", "GET").upper(), _norm_path(api.get("path", "")))
            matches = endpoint_index.get(key, [])
            if not matches and key[0] == "GET":
                # Many frontend helpers omit method; match any backend route with same path.
                matches = [uid for (method, path), ids_ in endpoint_index.items() if path == key[1] for uid in ids_]
            for dst in matches:
                self._add_edge(edges, src, dst, "frontend_api_to_fastapi", f"{key[0]} {key[1]}", api.get("span", {}).get("start_line", 0), vocab.CONFIDENCE_MEDIUM if len(matches) == 1 else vocab.CONFIDENCE_LOW)

    def _opensearch_edges(self, unit: dict[str, Any], resources: list[dict[str, Any]], edges: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        if not resources:
            return
        text = " ".join(unit.get("imports", [])) + " " + " ".join(c.get("target_text", "") for c in unit.get("call_candidates", [])) + " " + unit.get("file_path", "") + " " + unit.get("symbol", "")
        lower = text.lower()
        touches_search = any(token in lower for token in ("opensearch", "elasticsearch", "search", "index", "bulk"))
        if not touches_search:
            return
        explicit = [r for r in resources if r["name"].lower() in lower]
        targets = explicit or resources
        conf = vocab.CONFIDENCE_MEDIUM if explicit else vocab.CONFIDENCE_LOW
        for resource in targets[:20]:
            self._add_edge(edges, unit["unit_id"], resource["resource_id"], "backend_to_opensearch_resource", resource["name"], 0, conf)

    def _add_edge(self, edges: dict[tuple[str, str, str], dict[str, Any]], src: str, dst: str, edge_type: str, via: str, line: int, confidence: str) -> None:
        key = (src, dst, edge_type)
        existing = edges.get(key)
        if existing is None:
            edges[key] = {"from_unit": src, "to_unit": dst, "edge_type": edge_type, "via": [via], "lines": [line], "confidence": confidence, "state": vocab.STATUS_INFERRED}
        else:
            existing["via"].append(via); existing["lines"].append(line)
            if confidence == vocab.CONFIDENCE_MEDIUM:
                existing["confidence"] = vocab.CONFIDENCE_MEDIUM

    def _node(self, unit: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
        stale = bool(analysis and self.analyses.is_stale(analysis, unit))
        if stale: eff_state = vocab.STATUS_STALE
        elif analysis is not None: eff_state = analysis["state"]
        else: eff_state = unit["state"]
        eff_conf = analysis["confidence"] if analysis is not None else unit["confidence"]
        return {"unit_id": unit["unit_id"], "kind": unit["kind"], "repo": unit["repo"], "file_path": unit["file_path"], "symbol": unit["symbol"], "span": unit["span"], "unit_state": unit["state"], "review_status": (analysis or {}).get("review_status", "unreviewed"), "has_analysis": analysis is not None, "stale": stale, "eff_state": eff_state, "eff_confidence": eff_conf, "endpoints": unit.get("related_candidates", {}).get("endpoint_candidates", []), "related_candidates": unit.get("related_candidates", {})}

    def _write(self, graph: Graph, edges: list[dict[str, Any]], command: str) -> None:
        source = envelope.make_source()
        self.store.write_json(NODES_PATH, envelope.build_envelope(artifact_id="groundrail.graph.nodes", artifact_kind="graph_nodes", generator=envelope.make_generator(command, "groundrail.flow"), source=source, data={"nodes": list(graph.nodes.values()), "node_count": len(graph.nodes)}))
        self.store.write_json(EDGES_PATH, envelope.build_envelope(artifact_id="groundrail.graph.edges", artifact_kind="graph_edges", generator=envelope.make_generator(command, "groundrail.flow"), source=source, data={"edges": edges, "edge_count": len(edges)}))
