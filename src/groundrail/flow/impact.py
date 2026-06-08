"""Impact analysis and test selection.

Given a changed file or unit, finds dependent units/resources and categorises the
blast radius. Cross-layer links are inferred and confidence-labelled.
"""

from __future__ import annotations

from typing import Any

from ..core import envelope, vocab
from ..core.errors import NotFoundError
from ..core.gaps import CapabilityGapRegistry
from ..core.workspace import Workspace
from .graph import Graph, GraphBuilder
from .traverse import propagate

IMPACT_PATH = "impact/latest.json"
TEST_SELECTION_PATH = "testing/test-selection.json"


def _category(node: dict[str, Any]) -> str:
    if node.get("kind") == "opensearch_resource":
        return "data_resource_inferred"
    if node.get("review_status") == vocab.REVIEW_DEV_CONFIRMED:
        return "developer_confirmed"
    if node.get("eff_state") == vocab.STATUS_STALE:
        return "stale"
    if node.get("eff_state") == vocab.STATUS_PARTIAL:
        return "partial"
    if node.get("has_analysis") and node.get("eff_state") == vocab.STATUS_INFERRED:
        return "ai_inferred"
    if not node.get("has_analysis") and node.get("unit_state") == vocab.STATUS_VERIFIED:
        return "deterministic_structural"
    return "structural_inferred"


class ImpactEngine:
    def __init__(self, workspace: Workspace, *, graph: Graph | None = None) -> None:
        self.workspace = workspace
        self.store = workspace.store
        self.graph = graph or GraphBuilder(workspace).build()

    def impact_file(self, file_path: str, *, depth: int = 8) -> dict[str, Any]:
        seeds = [uid for uid, n in self.graph.nodes.items() if n.get("file_path") == file_path]
        if not seeds:
            raise NotFoundError(f"no indexed units/resources in file: {file_path}")
        return self._impact(seeds, target_label=file_path, kind="file", depth=depth)

    def impact_unit(self, unit_id: str, *, depth: int = 8) -> dict[str, Any]:
        if self.graph.node(unit_id) is None:
            raise NotFoundError(f"unknown unit/resource: {unit_id}")
        return self._impact([unit_id], target_label=unit_id, kind="unit", depth=depth)

    def tests_for(self, target: str, *, depth: int = 8) -> dict[str, Any]:
        seeds = self._seeds_for(target)
        callers = propagate(self.graph, seeds, direction="in", depth=depth)
        tests = []
        for uid, info in callers.items():
            node = self.graph.node(uid)
            if node and node.get("kind") == "test_function":
                tests.append({"unit_id": uid, "symbol": node["symbol"], "file_path": node["file_path"], "distance": info["distance"], "confidence": info["confidence"]})
        result = {"target": target, "seeds": seeds, "tests": sorted(tests, key=lambda t: (t["distance"], t["unit_id"])), "coverage_gap": len(tests) == 0}
        self.store.write_json(TEST_SELECTION_PATH, self._wrap(result, "test_selection"))
        return result

    def _impact(self, seeds: list[str], *, target_label: str, kind: str, depth: int) -> dict[str, Any]:
        upstream = propagate(self.graph, seeds, direction="in", depth=depth)
        downstream = propagate(self.graph, seeds, direction="out", depth=depth)
        impacted: list[dict[str, Any]] = []
        resources: list[dict[str, Any]] = []
        tests: list[dict[str, Any]] = []
        for uid, info in upstream.items():
            if uid in seeds:
                continue
            node = self.graph.node(uid)
            if not node:
                continue
            entry = {"unit_id": uid, "symbol": node["symbol"], "file_path": node["file_path"], "distance": info["distance"], "link_confidence": info["confidence"], "link_state": info["state"], "category": _category(node), "kind": node.get("kind", "")}
            impacted.append(entry)
            if node.get("kind") == "test_function":
                tests.append({"unit_id": uid, "symbol": node["symbol"], "distance": info["distance"]})
        for uid, info in downstream.items():
            node = self.graph.node(uid)
            if node and node.get("kind") == "opensearch_resource":
                resources.append({"resource_id": uid, "name": node["symbol"], "file_path": node["file_path"], "distance": info["distance"], "link_confidence": info["confidence"], "category": _category(node)})
        seed_files = {self.graph.node(s)["file_path"] for s in seeds if self.graph.node(s)}
        gaps = [g for g in CapabilityGapRegistry(self.store).load() if any(g.get("location", "").startswith(f) for f in seed_files)]
        result = {"target": target_label, "target_kind": kind, "changed_units": seeds, "impacted_upstream": sorted(impacted, key=lambda r: (r["distance"], r["unit_id"])), "depends_on_downstream": [{"unit_id": uid, "symbol": self.graph.node(uid)["symbol"], "kind": self.graph.node(uid).get("kind", ""), "distance": info["distance"], "confidence": info["confidence"]} for uid, info in sorted(downstream.items(), key=lambda kv: kv[1]["distance"]) if uid not in seeds and self.graph.node(uid)], "impacted_resources": sorted(resources, key=lambda r: (r["distance"], r["resource_id"])), "likely_tests": sorted(tests, key=lambda t: t["distance"]), "capability_gaps": gaps, "summary": self._summary(impacted + resources)}
        self.store.write_json(IMPACT_PATH, self._wrap(result, "impact_report"))
        return result

    def _summary(self, impacted: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in impacted:
            counts[entry["category"]] = counts.get(entry["category"], 0) + 1
        counts["total"] = len(impacted)
        return counts

    def _seeds_for(self, target: str) -> list[str]:
        if self.graph.node(target) is not None:
            return [target]
        seeds = [uid for uid, n in self.graph.nodes.items() if n.get("file_path") == target]
        if not seeds:
            raise NotFoundError(f"no unit/resource or file matches: {target}")
        return seeds

    def _wrap(self, data: dict[str, Any], kind: str) -> dict[str, Any]:
        return envelope.build_envelope(artifact_id=f"groundrail.{kind}", artifact_kind=kind, generator=envelope.make_generator(f"groundrail {kind}", "groundrail.flow"), source=envelope.make_source(), data=data)
