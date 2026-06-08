"""The strict validator.

Validates whole artifacts (envelope + payload) and individual records against
the global vocabulary. In strict mode, callers turn any returned problem into a
fail-closed error.
"""

from __future__ import annotations

from typing import Any

from . import envelope as envelope_mod
from . import vocab
from .evidence import validate_evidence


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def extend_errors(self, prefix: str, errors: list[str]) -> None:
        for err in errors:
            self.errors.append(f"{prefix}: {err}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "failed",
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_status(value: Any, report: ValidationReport, label: str) -> None:
    if value not in vocab.STATUSES:
        report.error(f"{label}: unknown status {value!r}")


def validate_confidence(value: Any, report: ValidationReport, label: str) -> None:
    if value not in vocab.CONFIDENCES:
        report.error(f"{label}: unknown confidence {value!r}")


def validate_review_status(value: Any, report: ValidationReport, label: str) -> None:
    if value not in vocab.REVIEW_STATUSES:
        report.error(f"{label}: unknown review_status {value!r}")


def validate_artifact(obj: Any, *, label: str = "artifact") -> ValidationReport:
    """Validate a full artifact envelope (not its domain payload)."""
    report = ValidationReport()
    report.extend_errors(label, envelope_mod.validate_envelope(obj))
    return report


def validate_unit_record(unit: dict[str, Any], report: ValidationReport) -> None:
    label = f"unit {unit.get('unit_id', '?')}"
    if unit.get("kind") not in vocab.UNIT_KINDS:
        report.error(f"{label}: unknown unit kind {unit.get('kind')!r}")
    validate_status(unit.get("state"), report, label)
    validate_confidence(unit.get("confidence"), report, label)
    span = unit.get("span")
    if not isinstance(span, dict) or "start_line" not in span or "end_line" not in span:
        report.error(f"{label}: missing or malformed span")
    for ev in unit.get("evidence", []) or []:
        report.extend_errors(f"{label} evidence", validate_evidence(ev))
