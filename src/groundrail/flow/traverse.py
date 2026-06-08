"""Confidence-aware graph traversal.

Finds reachable nodes while tracking, for each, the *best* path's weakest link —
the strongest chain of evidence that connects it to a seed. Bounded depth keeps
it cheap and acyclic-safe.
"""

from __future__ import annotations

from typing import Any

from ..core import vocab
from .graph import Graph
from .semantics import cap_at_inferred, weakest_confidence, weakest_state

_CONF_RANK = {vocab.CONFIDENCE_HIGH: 3, vocab.CONFIDENCE_MEDIUM: 2,
              vocab.CONFIDENCE_LOW: 1, vocab.CONFIDENCE_NONE: 0}


def propagate(graph: Graph, seeds: list[str], *, direction: str, depth: int = 6) -> dict[str, dict[str, Any]]:
    """Return ``{unit_id: {distance, confidence, state, edge}}`` reachable from seeds.

    ``direction`` is ``"out"`` (callees) or ``"in"`` (callers). Seeds appear at
    distance 0 with their own node trust.
    """
    best: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        node = graph.node(seed)
        if node is None:
            continue
        best[seed] = {
            "distance": 0,
            "confidence": node["eff_confidence"],
            "state": node["eff_state"],
            "edge": None,
        }

    adj = graph.out_edges if direction == "out" else graph.in_edges
    for _ in range(depth):
        changed = False
        for u in list(best):
            for edge in adj(u):
                v = edge["to_unit"] if direction == "out" else edge["from_unit"]
                node = graph.node(v)
                if node is None:
                    continue
                cand_conf = weakest_confidence(
                    [best[u]["confidence"], edge["confidence"], node["eff_confidence"]]
                )
                cand_state = cap_at_inferred(
                    weakest_state([best[u]["state"], edge["state"], node["eff_state"]])
                )
                if v not in best:
                    best[v] = {
                        "distance": best[u]["distance"] + 1,
                        "confidence": cand_conf,
                        "state": cand_state,
                        "edge": edge,
                    }
                    changed = True
                elif _CONF_RANK[cand_conf] > _CONF_RANK[best[v]["confidence"]]:
                    best[v].update({"confidence": cand_conf, "state": cand_state, "edge": edge})
                    best[v]["distance"] = min(best[v]["distance"], best[u]["distance"] + 1)
                    changed = True
        if not changed:
            break
    return best
