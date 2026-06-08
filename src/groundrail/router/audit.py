"""Answer audit.

Parses the ``<groundrail_citations>`` block from a Kiro answer and checks it
against the real artifact ids: cited ids must exist and be fresh, inferred
analyses must not be passed off as fully supported, and stale items must not be
used as support. Fail-closed in strict mode.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..core import vocab
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..analyzer.store import AnalysisStore
from ..indexer.unit_index import UnitStore

_BLOCK_RE = re.compile(
    rf"<{vocab.CITATION_BLOCK_TAG}>\s*(\{{.*?\}})\s*</{vocab.CITATION_BLOCK_TAG}>",
    re.DOTALL,
)

_ALLOWED_SUPPORT = {"supported", "not_confirmed", "inferred", "contradicted"}


class AnswerAuditor:
    def __init__(self, workspace: Workspace) -> None:
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)
        self._build_universe()

    def _build_universe(self) -> None:
        self.unit_ids: set[str] = set()
        self.evidence_ids: set[str] = set()
        self.analysis_state: dict[str, str] = {}
        self.analysis_stale: dict[str, str] = {}

        units_by_id = {}
        for unit in self.units.all():
            self.unit_ids.add(unit["unit_id"])
            units_by_id[unit["unit_id"]] = unit
            for ev in unit.get("evidence", []) or []:
                self.evidence_ids.add(ev["evidence_id"])
        for analysis in self.analyses.all():
            aid = analysis["analysis_id"]
            self.analysis_state[aid] = analysis["state"]
            unit = units_by_id.get(analysis["unit_id"])
            self.analysis_stale[aid] = (
                "stale" if unit and self.analyses.is_stale(analysis, unit) else "fresh"
            )

    def audit(self, answer_text: str) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        match = _BLOCK_RE.search(answer_text)
        if not match:
            findings.append({"severity": "error", "code": "missing_citation_block",
                             "message": f"answer has no <{vocab.CITATION_BLOCK_TAG}> block"})
            return self._result(findings, 0)

        try:
            block = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            findings.append({"severity": "error", "code": "malformed_citation_json",
                             "message": f"citation block is not valid JSON: {exc}"})
            return self._result(findings, 0)

        claims = block.get("claims", [])
        for claim in claims:
            self._audit_claim(claim, findings)
        return self._result(findings, len(claims))

    def _audit_claim(self, claim: dict[str, Any], findings: list[dict[str, Any]]) -> None:
        cid = claim.get("claim_id", "?")
        support = claim.get("support")
        if support not in _ALLOWED_SUPPORT:
            findings.append({"severity": "error", "code": "bad_support_value",
                             "message": f"claim {cid}: unknown support {support!r}"})

        cited_analyses = claim.get("analysis_ids", []) or []
        cited_units = claim.get("unit_ids", []) or []
        cited_evidence = claim.get("evidence_ids", []) or []
        cited_facts = claim.get("fact_ids", []) or []

        for uid in cited_units:
            if uid not in self.unit_ids:
                findings.append({"severity": "error", "code": "unknown_unit_id",
                                 "message": f"claim {cid}: cites unknown unit {uid}"})
        for eid in cited_evidence:
            if eid not in self.evidence_ids:
                findings.append({"severity": "error", "code": "unknown_evidence_id",
                                 "message": f"claim {cid}: cites unknown evidence {eid}"})
        for aid in cited_analyses:
            if aid not in self.analysis_state:
                findings.append({"severity": "error", "code": "unknown_analysis_id",
                                 "message": f"claim {cid}: cites unknown analysis {aid}"})
            elif self.analysis_stale.get(aid) == "stale":
                findings.append({"severity": "error", "code": "stale_support",
                                 "message": f"claim {cid}: cites stale analysis {aid} as support"})

        if support == "supported":
            has_hard = bool(cited_facts) or any(u in self.unit_ids for u in cited_units) or bool(cited_evidence)
            only_inferred = bool(cited_analyses) and all(
                self.analysis_state.get(a) in (vocab.STATUS_INFERRED, vocab.STATUS_PARTIAL)
                for a in cited_analyses
            )
            if not has_hard and only_inferred:
                findings.append({"severity": "error", "code": "overclaim",
                                 "message": f"claim {cid}: marked 'supported' but only cites "
                                            f"inferred analyses; should be 'inferred'"})
            if not has_hard and not cited_analyses:
                findings.append({"severity": "error", "code": "unsupported_claim",
                                 "message": f"claim {cid}: marked 'supported' but cites nothing"})

    def _result(self, findings: list[dict[str, Any]], claim_count: int) -> dict[str, Any]:
        has_error = any(f["severity"] == "error" for f in findings)
        return {
            "status": "failed" if has_error else "ok",
            "claims_checked": claim_count,
            "findings": findings,
        }
