"""Router tests: retrieval, context-pack inclusion rules, sessions, audit."""

from __future__ import annotations

import json

from groundrail.analyzer.pipeline import AnalysisPipeline
from groundrail.analyzer.runner import UnitAnalysisRunner
from groundrail.core import ids
from groundrail.indexer.snapshot import SourceSnapshotter
from groundrail.indexer.unit_index import UnitIndexBuilder, UnitStore
from groundrail.router.audit import AnswerAuditor
from groundrail.router.context_pack import ContextPackBuilder
from groundrail.router.retrieval import RetrievalIndex, RetrievalIndexBuilder

SEARCH_UNIT = "unit.api.app.services.users.search_users"
SEARCH_ANALYSIS = "analysis.api.app.services.users.search_users"


def _analyze(ws, unit_id, *, ai_confidence=0.8, summary="Searches users."):
    unit = UnitStore(ws.store).get(unit_id)
    start = unit["span"]["start_line"]
    runner = UnitAnalysisRunner(
        run_fn=lambda _p: json.dumps(
            {
                "summary": summary,
                "ai_confidence": ai_confidence,
                "intent": [{"text": "search", "confidence": 0.8, "evidence_lines": [start]}],
                "uncertainties": [],
            }
        )
    )
    return AnalysisPipeline(ws, runner=runner).analyze_unit(unit_id)


def test_retrieval_finds_relevant_unit(indexed_workspace):
    RetrievalIndexBuilder(indexed_workspace).build()
    rows = RetrievalIndex(indexed_workspace.store).search("user search")
    assert rows
    assert any(r["unit_id"] == SEARCH_UNIT for r in rows)


def test_context_pack_includes_evidence_and_rules(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    pack = ContextPackBuilder(indexed_workspace).build(mode="ask", request="how does user search work")
    assert pack["citation_rules"]["required_block"] == "groundrail_citations"
    assert pack["tokens_used"] <= pack["token_budget"]
    assert any(e["unit_id"] == SEARCH_UNIT for e in pack["source_evidence"])
    assert any(a["analysis_id"] == SEARCH_ANALYSIS for a in pack["selected_unit_analyses"])


def test_low_confidence_inferred_excluded_by_default(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT, ai_confidence=0.3)  # -> confidence low
    pack = ContextPackBuilder(indexed_workspace).build(mode="ask", request="user search")
    assert all(a["unit_id"] != SEARCH_UNIT for a in pack["selected_unit_analyses"])

    pack2 = ContextPackBuilder(indexed_workspace).build(
        mode="ask", request="user search", allow_inferred_low=True
    )
    assert any(a["unit_id"] == SEARCH_UNIT for a in pack2["selected_unit_analyses"])


def test_stale_analysis_excluded_and_flagged(workspace):
    SourceSnapshotter(workspace).run()
    UnitIndexBuilder(workspace).build()
    _analyze(workspace, SEARCH_UNIT)

    # Mutate the source so the unit's snippet hash changes, then re-index.
    path = workspace.project_root / "app" / "services" / "users.py"
    text = path.read_text(encoding="utf-8").replace(
        "results = search(query)", "results = search(query)\n    results = list(results)"
    )
    path.write_text(text, encoding="utf-8")
    SourceSnapshotter(workspace).run()
    UnitIndexBuilder(workspace).build()

    pack = ContextPackBuilder(workspace).build(mode="debug", request="user search")
    assert pack["freshness"]["status"] == "stale"
    assert SEARCH_UNIT in pack["freshness"]["stale_items"]
    assert all(a["unit_id"] != SEARCH_UNIT for a in pack["selected_unit_analyses"])


def test_markdown_separates_confirmed_and_inferred(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    builder = ContextPackBuilder(indexed_workspace)
    pack = builder.build(mode="ask", request="user search")
    md = builder.render_markdown(pack)
    assert "AI-inferred analyses (not confirmed)" in md
    assert "citation" in md.lower()  # section name may vary; content must be present


# --- audit -------------------------------------------------------------------
def _answer(claims):
    block = {"claims": claims, "citations": [], "not_confirmed": []}
    return "Here is the answer.\n<groundrail_citations>\n" + json.dumps(block) + "\n</groundrail_citations>"


def test_audit_missing_block_fails(indexed_workspace):
    audit = AnswerAuditor(indexed_workspace).audit("no citations here")
    assert audit["status"] == "failed"
    assert audit["findings"][0]["code"] == "missing_citation_block"


def test_audit_valid_supported_claim_passes(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    answer = _answer([
        {"claim_id": "c1", "text": "search_users handles search", "support": "supported",
         "unit_ids": [SEARCH_UNIT], "analysis_ids": [], "evidence_ids": [], "fact_ids": []}
    ])
    audit = AnswerAuditor(indexed_workspace).audit(answer)
    assert audit["status"] == "ok"


def test_audit_unknown_id_fails(indexed_workspace):
    answer = _answer([
        {"claim_id": "c1", "text": "x", "support": "supported",
         "unit_ids": ["unit.api.does.not.exist"], "analysis_ids": []}
    ])
    audit = AnswerAuditor(indexed_workspace).audit(answer)
    assert audit["status"] == "failed"
    assert any(f["code"] == "unknown_unit_id" for f in audit["findings"])


def test_audit_overclaim_inferred_as_supported_fails(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    answer = _answer([
        {"claim_id": "c1", "text": "x", "support": "supported",
         "unit_ids": [], "analysis_ids": [SEARCH_ANALYSIS]}
    ])
    audit = AnswerAuditor(indexed_workspace).audit(answer)
    assert any(f["code"] == "overclaim" for f in audit["findings"])


def test_audit_inferred_support_ok(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    answer = _answer([
        {"claim_id": "c1", "text": "x", "support": "inferred",
         "unit_ids": [], "analysis_ids": [SEARCH_ANALYSIS]}
    ])
    audit = AnswerAuditor(indexed_workspace).audit(answer)
    assert audit["status"] == "ok"
