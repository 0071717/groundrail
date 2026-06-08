"""Call-graph construction from unit call candidates.

Resolves textual call candidates (``repository.search``, ``self.repo.get``) to
unit ids by their trailing symbol name. Resolution is deliberately conservative:
a unique symbol match yields a ``medium``-confidence edge, an ambiguous match
yields ``low``. Unresolved targets (library/builtins) produce no edge. Every edge
is ``inferred`` — never verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..analyzer.store import AnalysisStore
from ..core import envelope, vocab
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
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


class GraphBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)

    def build(self, *, write: bool = True, command: str = "groundrail graph build") -> Graph:
        units = self.units.all()
        analyses = {a["unit_id"]: a for a in self.analyses.all()}

        symbol_index: dict[str, list[str]] = {}
        for unit in units:
            symbol_index.setdefault(unit["symbol"], []).append(unit["unit_id"])

        graph = Graph()
        for unit in units:
            graph.nodes[unit["unit_id"]] = self._node(unit, analyses.get(unit["unit_id"]))
            graph.out_adj.setdefault(unit["unit_id"], [])
            graph.in_adj.setdefault(unit["unit_id"], [])

        edges: dict[tuple[str, str], dict[str, Any]] = {}
        for unit in units:
            src = unit["unit_id"]
            for cand in unit.get("call_candidates", []):
                base = _trailing_symbol(cand["target_text"])
                matches = symbol_index.get(base, [])
                if not matches:
                    continue
                edge_conf = vocab.CONFIDENCE_MEDIUM if len(matches) == 1 else vocab.CONFIDENCE_LOW
                line = cand.get("span", {}).get("start_line", 0)
                for dst in matches:
                    key = (src, dst)
                    existing = edges.get(key)
                    if existing is None:
                        edges[key] = {
                            "from_unit": src,
                            "to_unit": dst,
                            "via": [cand["target_text"]],
                            "lines": [line],
                            "confidence": edge_conf,
                            "state": vocab.STATUS_INFERRED,
                        }
                    else:
                        existing["via"].append(cand["target_text"])
                        existing["lines"].append(line)
                        # parallel call sites: keep the stronger resolution
                        if edge_conf == vocab.CONFIDENCE_MEDIUM:
                            existing["confidence"] = vocab.CONFIDENCE_MEDIUM

        for edge in edges.values():
            graph.out_adj[edge["from_unit"]].append(edge)
            graph.in_adj[edge["to_unit"]].append(edge)

        if write:
            self._write(graph, list(edges.values()), command)
        return graph

    def _node(self, unit: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
        stale = bool(analysis and self.analyses.is_stale(analysis, unit))
        if stale:
            eff_state = vocab.STATUS_STALE
        elif analysis is not None:
            eff_state = analysis["state"]
        else:
            eff_state = unit["state"]
        eff_conf = analysis["confidence"] if analysis is not None else unit["confidence"]
        return {
            "unit_id": unit["unit_id"],
            "kind": unit["kind"],
            "repo": unit["repo"],
            "file_path": unit["file_path"],
            "symbol": unit["symbol"],
            "span": unit["span"],
            "unit_state": unit["state"],
            "review_status": (analysis or {}).get("review_status", "unreviewed"),
            "has_analysis": analysis is not None,
            "stale": stale,
            "eff_state": eff_state,
            "eff_confidence": eff_conf,
            "endpoints": unit.get("related_candidates", {}).get("endpoint_candidates", []),
        }

    def _write(self, graph: Graph, edges: list[dict[str, Any]], command: str) -> None:
        source = envelope.make_source()
        self.store.write_json(
            NODES_PATH,
            envelope.build_envelope(
                artifact_id="groundrail.graph.nodes",
                artifact_kind="graph_nodes",
                generator=envelope.make_generator(command, "groundrail.flow"),
                source=source,
                data={"nodes": list(graph.nodes.values()), "node_count": len(graph.nodes)},
            ),
        )
        self.store.write_json(
            EDGES_PATH,
            envelope.build_envelope(
                artifact_id="groundrail.graph.edges",
                artifact_kind="graph_edges",
                generator=envelope.make_generator(command, "groundrail.flow"),
                source=source,
                data={"edges": edges, "edge_count": len(edges)},
            ),
        )
