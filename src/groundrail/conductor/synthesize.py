"""Synthesizer — merge findings from one orchestration with weakest-link semantics.

Rules:
- Deduplicate by (unit_id, claim text normalized); keep the lower confidence.
- Detect conflicts: a ``supported`` finding and a ``contradicted`` finding for
  the same unit are a conflict that must surface to the developer.
- Overall confidence is the minimum across all findings.
- State is always capped at ``inferred`` — the synthesizer never promotes.
"""

from __future__ import annotations

from typing import Any

from ..core import timeutil, vocab

_CONF_RANK = {
    vocab.CONFIDENCE_HIGH: 3,
    vocab.CONFIDENCE_MEDIUM: 2,
    vocab.CONFIDENCE_LOW: 1,
    vocab.CONFIDENCE_NONE: 0,
}


def _lower_confidence(a: str, b: str) -> str:
    return a if _CONF_RANK.get(a, 0) <= _CONF_RANK.get(b, 0) else b


def _claim_key(finding: dict[str, Any]) -> tuple[str, str]:
    unit_ids = tuple(sorted(finding.get("unit_ids") or []))
    claim = (finding.get("claim") or "").lower().strip()
    return (str(unit_ids), claim[:120])


def _detect_conflicts(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conflict records where two findings contradict each other."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for f in findings:
        key = _claim_key(f)
        by_key.setdefault(key, []).append(f)

    conflicts = []
    for key, group in by_key.items():
        supports = {f.get("support") for f in group}
        # supported + contradicted for the same claim/unit is a conflict
        if "supported" in supports and "contradicted" in supports:
            conflicts.append({
                "conflict_key": str(key),
                "finding_ids": [f.get("finding_id") for f in group],
                "supports": sorted(supports),
                "description": (
                    "findings disagree: one claims 'supported', another 'contradicted' "
                    "for the same unit/claim"
                ),
            })
        # inferred + not_confirmed for the same claim is a softer conflict
        elif "inferred" in supports and "not_confirmed" in supports:
            conflicts.append({
                "conflict_key": str(key),
                "finding_ids": [f.get("finding_id") for f in group],
                "supports": sorted(supports),
                "description": "findings disagree: 'inferred' vs 'not_confirmed'",
            })
    return conflicts


def synthesize(
    findings: list[dict[str, Any]],
    orchestration_id: str,
    workflow: str,
    request: str,
) -> dict[str, Any]:
    """Merge findings with weakest-link semantics and surface conflicts."""
    if not findings:
        return {
            "schema_version": "1",
            "orchestration_id": orchestration_id,
            "workflow": workflow,
            "request": request,
            "synthesized_at": timeutil.now_iso(),
            "state": vocab.STATUS_INFERRED,
            "overall_confidence": vocab.CONFIDENCE_NONE,
            "findings": [],
            "conflicts": [],
            "finding_count": 0,
            "conflict_count": 0,
        }

    # Collect all individual findings from agent result dicts
    flat: list[dict[str, Any]] = []
    for agent_result in findings:
        for finding in agent_result.get("findings", []):
            flat.append(finding)

    # Deduplicate: for same (unit, claim) keep the lower confidence
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for f in flat:
        key = _claim_key(f)
        if key in merged:
            existing = merged[key]
            existing["confidence"] = _lower_confidence(
                existing["confidence"], f.get("confidence", vocab.CONFIDENCE_LOW)
            )
            # accumulate evidence references
            for ref_field in ("evidence", "unit_ids", "analysis_ids", "fact_ids"):
                existing_refs = existing.get(ref_field) or []
                new_refs = f.get(ref_field) or []
                combined = list(dict.fromkeys(existing_refs + new_refs))
                if combined:
                    existing[ref_field] = combined
        else:
            merged[key] = dict(f)

    merged_list = list(merged.values())
    conflicts = _detect_conflicts(flat)

    # Overall confidence = weakest link across merged findings
    if merged_list:
        overall_conf = merged_list[0].get("confidence", vocab.CONFIDENCE_LOW)
        for f in merged_list[1:]:
            overall_conf = _lower_confidence(overall_conf, f.get("confidence", vocab.CONFIDENCE_LOW))
    else:
        overall_conf = vocab.CONFIDENCE_NONE

    return {
        "schema_version": "1",
        "orchestration_id": orchestration_id,
        "workflow": workflow,
        "request": request,
        "synthesized_at": timeutil.now_iso(),
        "state": vocab.STATUS_INFERRED,
        "overall_confidence": overall_conf,
        "findings": merged_list,
        "conflicts": conflicts,
        "finding_count": len(merged_list),
        "conflict_count": len(conflicts),
    }
