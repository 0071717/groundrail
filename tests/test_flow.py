"""Flow/impact tests: call resolution, weakest-link, blast radius, test selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrail.analyzer.pipeline import AnalysisPipeline
from groundrail.analyzer.runner import UnitAnalysisRunner
from groundrail.core.workspace import Workspace
from groundrail.flow.flows import FlowComposer
from groundrail.flow.graph import GraphBuilder
from groundrail.flow.impact import ImpactEngine
from groundrail.flow.semantics import cap_at_inferred, weakest_confidence, weakest_state
from groundrail.indexer.snapshot import SourceSnapshotter
from groundrail.indexer.unit_index import UnitIndexBuilder

ROUTES = '''\
from fastapi import APIRouter
from app.services.users import search_users

router = APIRouter()


@router.get("/users/search")
async def search_endpoint(q: str):
    return search_users(q)
'''

USERS = '''\
from app.repo import search


def search_users(query, limit=10):
    results = search(query)
    return results[:limit]
'''

REPO = '''\
def search(query):
    return run_query(query)
'''

TEST_USERS = '''\
from app.services.users import search_users


def test_search_users():
    assert search_users("x") == []
'''

ENDPOINT = "unit.api.app.api.routes.search_endpoint"
SEARCH_USERS = "unit.api.app.services.users.search_users"
SEARCH = "unit.api.app.repo.search"
TEST_UNIT = "unit.api.tests.test_users.test_search_users"


@pytest.fixture
def flow_ws(tmp_path: Path) -> Workspace:
    (tmp_path / "app" / "api").mkdir(parents=True)
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "api" / "routes.py").write_text(ROUTES, encoding="utf-8")
    (tmp_path / "app" / "services" / "users.py").write_text(USERS, encoding="utf-8")
    (tmp_path / "app" / "repo.py").write_text(REPO, encoding="utf-8")
    (tmp_path / "tests" / "test_users.py").write_text(TEST_USERS, encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.init(repo_name="api")
    SourceSnapshotter(ws).run()
    UnitIndexBuilder(ws).build()
    return ws


def _analyze(ws, unit_id, ai_confidence=0.8):
    from groundrail.indexer.unit_index import UnitStore

    start = UnitStore(ws.store).get(unit_id)["span"]["start_line"]
    runner = UnitAnalysisRunner(
        run_fn=lambda _p: json.dumps(
            {"summary": "x", "ai_confidence": ai_confidence,
             "intent": [{"text": "x", "confidence": 0.8, "evidence_lines": [start]}],
             "uncertainties": []}
        )
    )
    AnalysisPipeline(ws, runner=runner).analyze_unit(unit_id)


# --- semantics ---------------------------------------------------------------
def test_weakest_link_helpers():
    assert weakest_confidence(["high", "low", "medium"]) == "low"
    assert weakest_state(["verified", "inferred", "stale"]) == "stale"
    assert cap_at_inferred("verified") == "inferred"
    assert cap_at_inferred("partial") == "partial"


# --- graph -------------------------------------------------------------------
def test_graph_resolves_call_candidates(flow_ws):
    graph = GraphBuilder(flow_ws).build()
    out = {e["to_unit"] for e in graph.out_edges(ENDPOINT)}
    assert SEARCH_USERS in out
    out2 = {e["to_unit"] for e in graph.out_edges(SEARCH_USERS)}
    assert SEARCH in out2
    # unique symbol resolution -> medium-confidence edge
    edge = graph.out_edges(SEARCH_USERS)[0]
    assert edge["confidence"] == "medium"
    assert edge["state"] == "inferred"


# --- flows -------------------------------------------------------------------
def test_endpoint_flow_follows_callees(flow_ws):
    flow = FlowComposer(flow_ws).endpoint_flow("GET", "/users/search")
    assert flow["root_unit"] == ENDPOINT
    reached = {n["unit_id"] for n in flow["nodes"]}
    assert SEARCH_USERS in reached and SEARCH in reached


def test_composition_never_claims_verified(flow_ws):
    # All units are verified Python boundaries, but the *flow* is inferred.
    flow = FlowComposer(flow_ws).endpoint_flow("GET", "/users/search")
    assert flow["state"] == "inferred"


def test_unit_flow_callers_and_callees(flow_ws):
    flow = FlowComposer(flow_ws).unit_flow(SEARCH_USERS)
    callees = {c["unit_id"] for c in flow["direct_callees"]}
    callers = {c["unit_id"] for c in flow["direct_callers"]}
    assert SEARCH in callees
    assert ENDPOINT in callers and TEST_UNIT in callers


def test_weakest_link_pulls_flow_confidence_down(flow_ws):
    _analyze(flow_ws, SEARCH_USERS, ai_confidence=0.3)  # -> low confidence node
    flow = FlowComposer(flow_ws).endpoint_flow("GET", "/users/search")
    assert flow["confidence"] == "low"


# --- impact ------------------------------------------------------------------
def test_impact_file_blast_radius(flow_ws):
    report = ImpactEngine(flow_ws).impact_file("app/repo.py")
    impacted = {e["unit_id"] for e in report["impacted_upstream"]}
    assert SEARCH_USERS in impacted
    assert ENDPOINT in impacted
    assert TEST_UNIT in impacted
    assert any(t["unit_id"] == TEST_UNIT for t in report["likely_tests"])
    assert report["summary"]["total"] >= 3


def test_impact_categories_reflect_trust(flow_ws):
    _analyze(flow_ws, SEARCH_USERS, ai_confidence=0.8)
    report = ImpactEngine(flow_ws).impact_unit(SEARCH)
    cats = {e["unit_id"]: e["category"] for e in report["impacted_upstream"]}
    assert cats[SEARCH_USERS] == "ai_inferred"          # has analysis
    assert cats[ENDPOINT] == "deterministic_structural"  # no analysis, verified boundary


def test_tests_for_finds_reaching_tests(flow_ws):
    result = ImpactEngine(flow_ws).tests_for(SEARCH)
    assert not result["coverage_gap"]
    assert any(t["unit_id"] == TEST_UNIT for t in result["tests"])


def test_tests_for_reports_coverage_gap(flow_ws):
    # The endpoint handler itself has no test reaching it.
    result = ImpactEngine(flow_ws).tests_for(ENDPOINT)
    assert result["coverage_gap"]


# --- CLI ---------------------------------------------------------------------
def test_cli_impact_and_flow(flow_ws, monkeypatch, capsys):
    from groundrail.cli.main import main

    monkeypatch.chdir(flow_ws.project_root)
    assert main(["impact", "file", "app/repo.py"]) == 0
    assert "impacted upstream" in capsys.readouterr().out
    assert main(["flow", "endpoint", "GET", "/users/search"]) == 0
    assert "search_users" in capsys.readouterr().out
    assert main(["tests-for", SEARCH]) == 0
    assert "test_search_users" in capsys.readouterr().out
