"""Analyzer tests: prompt boundary, strict validation, confidence, pipeline."""

from __future__ import annotations

import json

import pytest

from groundrail.analyzer import prompt as prompt_mod
from groundrail.analyzer.pipeline import AnalysisPipeline
from groundrail.analyzer.runner import UnitAnalysisRunner
from groundrail.analyzer.store import AnalysisStore
from groundrail.analyzer.validator import compute_confidence, extract_json, parse_and_validate
from groundrail.core.errors import SecretError, ValidationError
from groundrail.indexer.unit_index import UnitStore


def _unit(span=(1, 10), complexity="moderate"):
    return {
        "unit_id": "unit.api.mod.fn",
        "kind": "python_function",
        "symbol": "fn",
        "qualified_name": "fn",
        "file_path": "mod.py",
        "repo": "api",
        "span": {"start_line": span[0], "end_line": span[1], "start_col": 1, "end_col": 1},
        "file_hash": "sha256:f",
        "snippet_hash": "sha256:s",
        "complexity": {"state": complexity, "line_count": 10, "branch_count": 2, "call_count": 1},
        "imports": [],
        "call_candidates": [],
        "related_candidates": {"endpoint_candidates": []},
        "evidence": [{"source_commit": "c0"}],
    }


def _resp(**overrides):
    body = {
        "summary": "Does a thing.",
        "ai_confidence": 0.8,
        "intent": [{"text": "do thing", "confidence": 0.8, "evidence_lines": [2]}],
        "uncertainties": [],
        "ai_notes": [],
    }
    body.update(overrides)
    return json.dumps(body)


def test_prompt_marks_source_untrusted_and_boundaries():
    packet = prompt_mod.build_packet(_unit(), source_text="def fn(): pass")
    assert packet["instructions"]["source_is_untrusted_input"] is True
    text = prompt_mod.render_prompt(packet)
    assert "BEGIN UNTRUSTED SOURCE" in text and "END UNTRUSTED SOURCE" in text
    assert "Never claim anything is 'verified'" in text


def test_extract_json_from_noisy_output():
    raw = "Here is the analysis:\n```json\n" + _resp() + "\n```\nThanks!"
    obj = extract_json(raw)
    assert obj["summary"] == "Does a thing."


def test_valid_analysis_accepted_defaults_to_inferred():
    analysis, report = parse_and_validate(_resp(), _unit(), model="m", prompt_hash="ph")
    assert report.ok
    assert analysis["state"] == "inferred"
    assert analysis["confidence"] == "high"
    assert analysis["review_status"] == "unreviewed"
    assert analysis["analysis_provenance"]["unit_hash"] == "sha256:s"


def test_missing_summary_rejected():
    _, report = parse_and_validate(_resp(summary=""), _unit(), model="m", prompt_hash="ph")
    assert not report.ok


def test_ai_claiming_verified_is_rejected():
    # Simulates a successful prompt injection trying to elevate trust -> fail closed.
    _, report = parse_and_validate(_resp(state="verified"), _unit(), model="m", prompt_hash="ph")
    assert not report.ok
    assert any("verified" in e for e in report.errors)


def test_evidence_line_outside_span_rejected():
    raw = _resp(intent=[{"text": "x", "confidence": 0.7, "evidence_lines": [9999]}])
    _, report = parse_and_validate(raw, _unit(span=(1, 10)), model="m", prompt_hash="ph")
    assert not report.ok
    assert any("outside unit span" in e for e in report.errors)


def test_unknown_note_type_rejected():
    raw = _resp(ai_notes=[{"type": "totally_made_up", "text": "x", "evidence_lines": [2]}])
    _, report = parse_and_validate(raw, _unit(), model="m", prompt_hash="ph")
    assert not report.ok


def test_complex_unit_without_uncertainty_marked_partial():
    analysis, report = parse_and_validate(
        _resp(uncertainties=[]), _unit(complexity="complex"), model="m", prompt_hash="ph"
    )
    assert report.ok
    assert analysis["state"] == "partial"


def test_confidence_bucket_rules():
    assert compute_confidence(ai_confidence=0.9, complexity_state="simple", uncertainty_count=0) == "high"
    assert compute_confidence(ai_confidence=0.4, complexity_state="simple", uncertainty_count=0) == "low"
    assert compute_confidence(ai_confidence=0.9, complexity_state="complex", uncertainty_count=0) == "medium"


def test_pipeline_analyses_unit_with_injected_runner(indexed_workspace):
    unit = UnitStore(indexed_workspace.store).get("unit.api.app.services.users.search_users")
    start = unit["span"]["start_line"]
    runner = UnitAnalysisRunner(
        run_fn=lambda _prompt: _resp(
            intent=[{"text": "search users", "confidence": 0.8, "evidence_lines": [start]}]
        )
    )
    pipeline = AnalysisPipeline(indexed_workspace, runner=runner)
    analysis = pipeline.analyze_unit(unit["unit_id"])
    assert analysis["state"] == "inferred"
    stored = AnalysisStore(indexed_workspace.store).get(unit["unit_id"])
    assert stored["summary"] == "Does a thing."


def test_pipeline_blocks_units_with_secrets(indexed_workspace):
    runner = UnitAnalysisRunner(run_fn=lambda _p: _resp())
    pipeline = AnalysisPipeline(indexed_workspace, runner=runner)
    with pytest.raises(SecretError):
        pipeline.analyze_unit("unit.api.app.secretsmod.connect")
    from groundrail.core.gaps import CapabilityGapRegistry

    assert any(g["kind"] == "secret_in_unit" for g in CapabilityGapRegistry(indexed_workspace.store).load())


def test_pipeline_invalid_output_raises(indexed_workspace):
    runner = UnitAnalysisRunner(run_fn=lambda _p: _resp(state="verified"))
    pipeline = AnalysisPipeline(indexed_workspace, runner=runner)
    with pytest.raises(ValidationError):
        pipeline.analyze_unit("unit.api.app.services.users.search_users")


def test_runner_unconfigured_raises():
    runner = UnitAnalysisRunner(command="")
    assert not runner.configured
    with pytest.raises(Exception):
        runner.run("prompt")
