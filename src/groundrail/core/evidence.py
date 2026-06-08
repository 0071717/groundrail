"""Evidence and provenance builders.

Every source-backed record carries an evidence object pointing at an exact span,
plus the hashes needed to detect staleness later.
"""

from __future__ import annotations

from typing import Any

from . import timeutil, vocab
from .errors import ValidationError


def make_span(start_line: int, end_line: int, start_col: int = 1, end_col: int = 1) -> dict[str, int]:
    return {
        "start_line": start_line,
        "end_line": end_line,
        "start_col": start_col,
        "end_col": end_col,
    }


def build_evidence(
    *,
    evidence_id: str,
    evidence_kind: str,
    repo: str,
    file_path: str,
    source_commit: str,
    file_hash: str,
    span: dict[str, int],
    snippet_hash: str,
    extractor_id: str,
    extractor_kind: str,
    extractor_version: str = "0.1.0",
) -> dict[str, Any]:
    if evidence_kind not in vocab.EVIDENCE_KINDS:
        raise ValidationError(f"unknown evidence_kind: {evidence_kind!r}")
    return {
        "evidence_id": evidence_id,
        "evidence_kind": evidence_kind,
        "repo": repo,
        "file_path": file_path,
        "source_commit": source_commit,
        "file_hash": file_hash,
        "span": span,
        "snippet_hash": snippet_hash,
        "extractor": {
            "id": extractor_id,
            "version": extractor_version,
            "kind": extractor_kind,
        },
    }


def build_provenance(
    *,
    model: str,
    prompt_hash: str,
    source_commit: str,
    unit_hash: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "created_at": created_at or timeutil.now_iso(),
        "model": model,
        "prompt_hash": prompt_hash,
        "source_commit": source_commit,
        "unit_hash": unit_hash,
    }


_REQUIRED_EVIDENCE_FIELDS = (
    "evidence_id",
    "evidence_kind",
    "repo",
    "file_path",
    "source_commit",
    "file_hash",
    "span",
    "snippet_hash",
    "extractor",
)


def validate_evidence(obj: Any) -> list[str]:
    """Return problems with an evidence object; empty list means valid."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["evidence is not a JSON object"]
    for field in _REQUIRED_EVIDENCE_FIELDS:
        if field not in obj:
            errors.append(f"missing evidence field: {field}")
    kind = obj.get("evidence_kind")
    if kind is not None and kind not in vocab.EVIDENCE_KINDS:
        errors.append(f"unknown evidence_kind: {kind!r}")
    span = obj.get("span")
    if isinstance(span, dict):
        for field in ("start_line", "end_line"):
            if not isinstance(span.get(field), int):
                errors.append(f"evidence span.{field} must be an integer")
    elif "span" in obj:
        errors.append("evidence span must be an object")
    return errors
