"""Core trust-contract tests: vocab, envelope, evidence, hashing, secrets."""

from __future__ import annotations

from groundrail.core import envelope, evidence, hashing, secrets, vocab
from groundrail.core.validation import (
    ValidationReport,
    validate_confidence,
    validate_review_status,
    validate_status,
)


def test_vocab_sets_are_closed():
    assert "verified" in vocab.STATUSES
    assert "high" in vocab.CONFIDENCES
    assert "dev_confirmed" in vocab.REVIEW_STATUSES
    # business_rules deliberately replaced by behavioral_notes (docs/09)
    assert "behavioral_note" in vocab.REVIEW_SCOPES
    assert "business_rule" not in vocab.REVIEW_SCOPES


def test_status_validation_rejects_unknown():
    report = ValidationReport()
    validate_status("verified", report, "x")
    validate_status("definitely", report, "x")
    validate_confidence("high", report, "x")
    validate_review_status("unreviewed", report, "x")
    assert any("definitely" in e for e in report.errors)
    assert len(report.errors) == 1


def test_envelope_roundtrip_valid():
    art = envelope.build_envelope(
        artifact_id="a",
        artifact_kind="k",
        generator=envelope.make_generator("groundrail test"),
        source=envelope.make_source(),
        data={"x": 1},
    )
    assert envelope.validate_envelope(art) == []


def test_envelope_missing_field_detected():
    art = envelope.build_envelope(
        artifact_id="a",
        artifact_kind="k",
        generator=envelope.make_generator("groundrail test"),
        source=envelope.make_source(),
        data={},
    )
    del art["generated_at"]
    errors = envelope.validate_envelope(art)
    assert any("generated_at" in e for e in errors)


def test_envelope_rejects_non_object():
    assert envelope.validate_envelope([1, 2, 3])


def test_evidence_builder_and_validation():
    ev = evidence.build_evidence(
        evidence_id="ev.1",
        evidence_kind="unit_span",
        repo="api",
        file_path="a.py",
        source_commit="abc",
        file_hash=hashing.sha256_text("x"),
        span=evidence.make_span(1, 5),
        snippet_hash=hashing.sha256_text("y"),
        extractor_id="t",
        extractor_kind="python_ast",
    )
    assert evidence.validate_evidence(ev) == []


def test_evidence_unknown_kind_rejected():
    report = evidence.validate_evidence(
        {"evidence_kind": "made_up", "span": {"start_line": 1, "end_line": 2}}
    )
    assert any("evidence_kind" in e for e in report)


def test_hashing_is_deterministic_and_prefixed():
    a = hashing.sha256_text("hello")
    b = hashing.sha256_text("hello")
    assert a == b and a.startswith("sha256:")
    assert hashing.sha256_text("hello") != hashing.sha256_text("world")


def test_secret_scanner_flags_aws_and_assignments():
    assert secrets.has_secret("key = AKIAIOSFODNN7EXAMPLE")
    assert secrets.has_secret('password = "supersecretpassword12345"')
    assert not secrets.has_secret("x = 1\ny = 'short'")
