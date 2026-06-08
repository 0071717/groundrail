"""TUI tests: view models, pure rendering, screen composition, and --print CLI."""

from __future__ import annotations

import json

from groundrail.analyzer.pipeline import AnalysisPipeline
from groundrail.analyzer.runner import UnitAnalysisRunner
from groundrail.cli.main import main
from groundrail.indexer.unit_index import UnitStore
from groundrail.router.context_pack import ContextPackBuilder
from groundrail.tui import render, screens
from groundrail.tui.viewmodels import ViewModelBuilder

SEARCH_UNIT = "unit.api.app.services.users.search_users"
TEST_UNIT = "unit.api.app.services.users.test_search_users"


def _analyze(ws, unit_id):
    start = UnitStore(ws.store).get(unit_id)["span"]["start_line"]
    runner = UnitAnalysisRunner(
        run_fn=lambda _p: json.dumps(
            {"summary": "Searches users.", "ai_confidence": 0.8,
             "intent": [{"text": "search", "confidence": 0.8, "evidence_lines": [start]}],
             "uncertainties": []}
        )
    )
    AnalysisPipeline(ws, runner=runner).analyze_unit(unit_id)


# --- view models -------------------------------------------------------------
def test_dashboard_counts(indexed_workspace):
    vm = ViewModelBuilder(indexed_workspace).dashboard()
    assert vm["units"] > 0
    assert vm["analysed"] == 0
    assert any(kind == "python_function" for kind, _ in vm["kinds"])


def test_units_rows_and_detail(indexed_workspace):
    _analyze(indexed_workspace, SEARCH_UNIT)
    builder = ViewModelBuilder(indexed_workspace)
    rows = builder.units_rows()
    assert any(r["unit_id"] == SEARCH_UNIT for r in rows)

    detail = builder.unit_detail(SEARCH_UNIT)
    assert detail["analysis"]["summary"] == "Searches users."
    assert detail["source"]  # source lines loaded
    callers = {c["unit_id"] for c in detail["callers"]}
    assert TEST_UNIT in callers


def test_sessions_rows_after_pack(indexed_workspace):
    ContextPackBuilder(indexed_workspace).build(mode="ask", request="user search")
    builder = ViewModelBuilder(indexed_workspace)
    rows = builder.sessions_rows()
    assert rows
    detail = builder.session_detail(rows[0]["session_id"])
    assert "pack_md" in detail


# --- pure rendering ----------------------------------------------------------
def test_frame_fit_vs_clamped():
    fit = render.frame("T", ["a", "b"], "foot", width=20, height=None)
    assert len(fit) == 2 + 2 + 2  # header(2) + body(2) + footer(2)
    clamped = render.frame("T", ["a", "b"], "foot", width=20, height=10)
    assert len(clamped) == 10  # padded to height
    assert all(len(line) == 20 for line in clamped)


def test_truncate_adds_ellipsis():
    assert render.truncate("hello world", 5) == "hell…"
    assert render.truncate("hi", 5) == "hi"


def test_compose_dashboard_has_title(indexed_workspace):
    builder = ViewModelBuilder(indexed_workspace)
    frame = screens.compose(builder, {**screens.default_ui()}, 80, None)
    assert "Groundrail" in frame[0]
    assert "Dashboard" in frame[0]


def test_render_units_marks_selection(indexed_workspace):
    builder = ViewModelBuilder(indexed_workspace)
    lines = render.render_units(builder.units_rows(), selection=0, width=120)
    body = [l for l in lines if l.startswith(("> ", "  ")) and "unit" not in l[:6]]
    assert any(l.startswith("> ") for l in lines)


# --- CLI --print -------------------------------------------------------------
def test_cli_tui_print_screens(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    _analyze(indexed_workspace, SEARCH_UNIT)

    assert main(["tui", "--print", "dashboard"]) == 0
    assert "Dashboard" in capsys.readouterr().out

    assert main(["tui", "--print", "units"]) == 0
    assert "search_users" in capsys.readouterr().out

    assert main(["tui", "--print", "unit", "--unit", SEARCH_UNIT]) == 0
    out = capsys.readouterr().out
    assert "Searches users." in out
    assert "source:" in out


def test_cli_tui_print_unit_requires_id(indexed_workspace, monkeypatch):
    monkeypatch.chdir(indexed_workspace.project_root)
    rc = main(["tui", "--print", "unit"])
    assert rc == 1  # GroundrailError for missing --unit


def test_cli_tui_print_session(indexed_workspace, monkeypatch, capsys):
    monkeypatch.chdir(indexed_workspace.project_root)
    ContextPackBuilder(indexed_workspace).build(mode="ask", request="user search")
    assert main(["tui", "--print", "session"]) == 0
    assert "context pack" in capsys.readouterr().out.lower()
