"""Child-agent runner and ``<groundrail_agent_result>`` validator.

Design invariants (from AGENTS.md):
- Agents write ONLY to orchestration paths, NEVER to canonical indexes.
- ``state: verified`` is NEVER allowed in agent output.
- ``supported`` findings MUST carry at least one evidence reference.
- Malformed results go to quarantine; the orchestration continues.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any, Callable

from ..core.errors import ConfigError, GroundrailError

AGENT_CMD_ENV = "GROUNDRAIL_AGENT_CMD"
RESULT_TAG = "groundrail_agent_result"

_VALID_STATUSES = frozenset({"completed", "failed", "partial"})
_VALID_VERDICTS = frozenset({"no_issues", "issues_found", "needs_followup", "blocked"})
_VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_VALID_SUPPORTS = frozenset({"supported", "inferred", "not_confirmed", "contradicted", "out_of_scope"})
_VALID_CONFIDENCES = frozenset({"high", "medium", "low"})

# Fields that mark a Groundrail *canonical* artifact — agents may not emit these
# because they would impersonate a unit-index or analysis artifact.
# schema_version is intentionally NOT included: docs/02 requires it in agent results.
_CANONICAL_FIELDS = frozenset({"artifact_kind", "artifact_id"})


def extract_result_block(text: str) -> str | None:
    """Return the JSON body between ``<groundrail_agent_result>`` tags, or None."""
    pattern = rf"<{RESULT_TAG}>(.*?)</{RESULT_TAG}>"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


def validate_agent_result(result: dict[str, Any]) -> list[str]:
    """Return a list of validation errors; empty list means valid."""
    errors: list[str] = []

    # --- top-level required fields ------------------------------------------
    for field in ("schema_version", "task_id", "agent_profile", "status", "verdict", "confidence", "summary"):
        if not result.get(field):
            errors.append(f"missing required field: {field!r}")
    if result.get("schema_version") and result.get("schema_version") != "1":
        errors.append(f"schema_version must be '1', got {result.get('schema_version')!r}")

    if result.get("status") not in _VALID_STATUSES:
        errors.append(f"invalid status {result.get('status')!r}")
    if result.get("verdict") not in _VALID_VERDICTS:
        errors.append(f"invalid verdict {result.get('verdict')!r}")
    if result.get("confidence") not in _VALID_CONFIDENCES:
        errors.append(f"invalid confidence {result.get('confidence')!r}")

    # --- canonical artifact impersonation guard ------------------------------
    forbidden = _CANONICAL_FIELDS & result.keys()
    if forbidden:
        errors.append(
            f"agent result may not contain canonical fields: {sorted(forbidden)}; "
            "agents may not write canonical Groundrail artifacts"
        )

    # --- state: verified is forbidden (agents cannot assert verified) --------
    if result.get("state") == "verified":
        errors.append("agent results may not claim state: verified")

    # --- findings ------------------------------------------------------------
    for i, finding in enumerate(result.get("findings", [])):
        prefix = f"finding[{i}]"
        for fld in ("finding_id", "severity", "title", "claim", "support", "confidence"):
            if not finding.get(fld):
                errors.append(f"{prefix}: missing required field {fld!r}")
        if finding.get("severity") not in _VALID_SEVERITIES:
            errors.append(f"{prefix}: invalid severity {finding.get('severity')!r}")
        if finding.get("support") not in _VALID_SUPPORTS:
            errors.append(f"{prefix}: invalid support {finding.get('support')!r}")
        if finding.get("confidence") not in _VALID_CONFIDENCES:
            errors.append(f"{prefix}: invalid confidence {finding.get('confidence')!r}")

        # supported findings must carry at least one evidence reference
        if finding.get("support") == "supported":
            has_ref = (
                finding.get("evidence")
                or finding.get("unit_ids")
                or finding.get("analysis_ids")
                or finding.get("fact_ids")
            )
            if not has_ref:
                errors.append(
                    f"{prefix}: support=supported requires at least one of "
                    "evidence, unit_ids, analysis_ids, or fact_ids"
                )

    return errors


def parse_agent_result(raw_text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract and validate the agent result block from raw text.

    Returns ``(result_dict, errors)``. If errors is non-empty the result is
    quarantine-worthy; callers must NOT store it in canonical paths.
    """
    block = extract_result_block(raw_text)
    if block is None:
        return None, [f"missing <{RESULT_TAG}> block in agent output"]

    try:
        result = json.loads(block)
    except json.JSONDecodeError as exc:
        return None, [f"malformed JSON in agent result block: {exc}"]

    if not isinstance(result, dict):
        return None, ["agent result block must be a JSON object"]

    errors = validate_agent_result(result)
    if errors:
        return None, errors
    return result, []


RunFn = Callable[[str], str]


class ChildAgentRunner:
    """Dispatches tasks to a child agent and parses/validates structured output.

    The agent command is read from ``GROUNDRAIL_AGENT_CMD``. It receives the
    task prompt on stdin and must include a ``<groundrail_agent_result>`` block
    in its stdout.
    """

    def __init__(
        self,
        *,
        run_fn: RunFn | None = None,
        command: str | None = None,
    ) -> None:
        self._run_fn = run_fn
        self._command = command or os.environ.get(AGENT_CMD_ENV)

    @property
    def configured(self) -> bool:
        return self._run_fn is not None or bool(self._command)

    def run_raw(self, prompt: str) -> str:
        """Execute the agent command and return raw stdout."""
        if self._run_fn is not None:
            return self._run_fn(prompt)
        if not self._command:
            raise ConfigError(
                f"agent not configured; set {AGENT_CMD_ENV} "
                "(e.g. 'kiro-cli --task-file {task_file}')"
            )
        try:
            result = subprocess.run(
                shlex.split(self._command),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ConfigError(f"agent command not found: {self._command!r}") from exc
        except subprocess.SubprocessError as exc:
            raise GroundrailError(f"agent command failed: {exc}") from exc
        if result.returncode != 0:
            raise GroundrailError(
                f"agent exited {result.returncode}: {result.stderr.strip()[:500]}"
            )
        return result.stdout

    def dispatch(
        self,
        *,
        orch_store: Any,
        orch_id: str,
        task_id: str,
        prompt: str,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Run the agent and route the result to findings or quarantine.

        Returns ``(result, errors)``. Callers may inspect errors but should not
        re-raise — the orchestration continues regardless of agent output.
        """
        raw = self.run_raw(prompt)
        result, errors = parse_agent_result(raw)
        if errors:
            orch_store.quarantine_result(orch_id, task_id, errors[0], raw)
        else:
            orch_store.write_finding(orch_id, task_id, result)
        return result, errors
