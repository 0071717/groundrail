"""Parse and strictly validate AI unit-analysis output.

The model returns a JSON object; this module extracts it, rejects illegal output
(notably any attempt to claim ``verified``), checks evidence lines fall within
the unit span, and normalises everything into a full analysis artifact with a
Groundrail-computed confidence bucket and provenance.
"""

from __future__ import annotations

import json
from typing import Any

from ..core import evidence as evidence_mod
from ..core import ids, timeutil, vocab
from ..core.validation import ValidationReport

_CLAIM_LIST_FIELDS = (
    "intent", "inputs", "outputs", "side_effects",
    "state_access", "calls", "errors", "behavioral_notes",
)


def extract_json(raw: str) -> dict[str, Any]:
    """Pull the first balanced top-level JSON object out of model output."""
    raw = raw.strip()
    start = raw.find("{")
    if start == -1:
        raise ValueError("no JSON object found in AI output")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])
    raise ValueError("unbalanced JSON object in AI output")


def compute_confidence(*, ai_confidence: float, complexity_state: str, uncertainty_count: int) -> str:
    """Derive Groundrail's confidence bucket from model self-score + signals.

    Per docs/09: an ``ai_confidence`` below 0.5 is forced to ``low`` rather than
    trusting the model's optimism; complexity and many uncertainties also pull it
    down.
    """
    if ai_confidence < 0.5:
        return vocab.CONFIDENCE_LOW
    score = ai_confidence
    if complexity_state == vocab.COMPLEXITY_COMPLEX:
        score -= 0.2
    if uncertainty_count >= 3:
        score -= 0.1
    if score >= 0.8:
        return vocab.CONFIDENCE_HIGH
    if score >= 0.55:
        return vocab.CONFIDENCE_MEDIUM
    return vocab.CONFIDENCE_LOW


def parse_and_validate(
    raw: str, unit: dict[str, Any], *, model: str, prompt_hash: str
) -> tuple[dict[str, Any], ValidationReport]:
    """Return ``(analysis, report)``. ``report.ok`` is False if output is invalid."""
    report = ValidationReport()
    try:
        payload = extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        report.error(f"AI output is not valid JSON: {exc}")
        return {}, report

    # Fail-closed: the model must never assert verified state.
    if payload.get("state") == vocab.STATUS_VERIFIED:
        report.error("AI analysis illegally claims state 'verified'")

    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        report.error("AI analysis missing required 'summary'")

    ai_confidence = payload.get("ai_confidence", 0.6)
    if not isinstance(ai_confidence, (int, float)) or not 0.0 <= float(ai_confidence) <= 1.0:
        report.error(f"ai_confidence must be a number in [0,1], got {ai_confidence!r}")
        ai_confidence = 0.5
    ai_confidence = float(ai_confidence)

    span = unit["span"]
    _check_evidence_lines(payload, span, report)
    ai_notes = _normalise_notes(payload.get("ai_notes", []), span, report)

    complexity = unit.get("complexity", {})
    uncertainties = payload.get("uncertainties", []) or []
    confidence = compute_confidence(
        ai_confidence=ai_confidence,
        complexity_state=complexity.get("state", vocab.COMPLEXITY_MODERATE),
        uncertainty_count=len(uncertainties),
    )

    # Large/complex units with no stated uncertainty are suspicious -> partial.
    state = vocab.STATUS_INFERRED
    if complexity.get("state") == vocab.COMPLEXITY_COMPLEX and not uncertainties:
        state = vocab.STATUS_PARTIAL

    analysis = _assemble(
        unit=unit,
        payload=payload,
        state=state,
        confidence=confidence,
        ai_confidence=ai_confidence,
        ai_notes=ai_notes,
        uncertainties=uncertainties,
        model=model,
        prompt_hash=prompt_hash,
    )
    return analysis, report


def _check_evidence_lines(payload: dict[str, Any], span: dict[str, int], report: ValidationReport) -> None:
    lo, hi = span["start_line"], span["end_line"]
    for field in _CLAIM_LIST_FIELDS + ("uncertainties",):
        for item in payload.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            for line in item.get("evidence_lines", []) or []:
                if isinstance(line, int) and not (lo <= line <= hi):
                    report.error(
                        f"{field}: evidence line {line} outside unit span {lo}-{hi}"
                    )


def _normalise_notes(notes: Any, span: dict[str, int], report: ValidationReport) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(notes, list):
        return result
    for idx, note in enumerate(notes):
        if not isinstance(note, dict):
            continue
        note_type = note.get("type")
        if note_type not in vocab.NOTE_TYPES:
            report.error(f"ai_note[{idx}]: unknown type {note_type!r}")
            continue
        result.append(
            {
                "note_id": f"note.{idx}",
                "type": note_type,
                "severity": note.get("severity", "low"),
                "importance": note.get("importance", "low"),
                "confidence": float(note.get("confidence", 0.5)),
                "text": note.get("text", ""),
                "evidence_lines": [
                    l for l in note.get("evidence_lines", []) or []
                    if isinstance(l, int) and span["start_line"] <= l <= span["end_line"]
                ],
                "review_status": vocab.REVIEW_UNREVIEWED,
                "created_by": {"agent": "groundrail-unit-analyser", "model": ""},
            }
        )
    return result


def _claim_list(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(payload.get(field, []) or []):
        if isinstance(item, dict) and item.get("text"):
            out.append(
                {
                    "claim_id": f"claim.{field}.{i:03d}",
                    "text": item["text"],
                    "support": "inferred_from_span",
                    "confidence": float(item.get("confidence", 0.6)),
                    "evidence_lines": [l for l in item.get("evidence_lines", []) or [] if isinstance(l, int)],
                    "review_status": vocab.REVIEW_UNREVIEWED,
                }
            )
    return out


def _assemble(
    *,
    unit: dict[str, Any],
    payload: dict[str, Any],
    state: str,
    confidence: str,
    ai_confidence: float,
    ai_notes: list[dict[str, Any]],
    uncertainties: list[Any],
    model: str,
    prompt_hash: str,
) -> dict[str, Any]:
    uid = unit["unit_id"]
    return {
        "analysis_id": ids.analysis_id(uid),
        "unit_id": uid,
        "kind": "unit_analysis",
        "state": state,
        "confidence": confidence,
        "ai_confidence": ai_confidence,
        "review_status": vocab.REVIEW_UNREVIEWED,
        "review": None,
        "summary": payload.get("summary", ""),
        "intent": _claim_list(payload, "intent"),
        "inputs": _claim_list(payload, "inputs"),
        "outputs": _claim_list(payload, "outputs"),
        "side_effects": _claim_list(payload, "side_effects"),
        "state_access": _claim_list(payload, "state_access"),
        "calls": _claim_list(payload, "calls"),
        "errors": _claim_list(payload, "errors"),
        "behavioral_notes": _claim_list(payload, "behavioral_notes"),
        "uncertainties": [
            {
                "text": u.get("text", ""),
                "reason": u.get("reason", ""),
                "evidence_lines": [l for l in u.get("evidence_lines", []) or [] if isinstance(l, int)],
            }
            for u in uncertainties
            if isinstance(u, dict)
        ],
        "complexity": unit.get("complexity", {}),
        "ai_notes": ai_notes,
        "evidence": [],
        "analysis_provenance": evidence_mod.build_provenance(
            model=model,
            prompt_hash=prompt_hash,
            source_commit=_unit_commit(unit),
            unit_hash=unit["snippet_hash"],
            created_at=timeutil.now_iso(),
        ),
    }


def _unit_commit(unit: dict[str, Any]) -> str:
    for ev in unit.get("evidence", []) or []:
        if ev.get("source_commit"):
            return ev["source_commit"]
    return "unknown"
