"""Secret scanning.

Per the docs/09 security review, secret detection must run *before* prompt
construction — source sent to an AI command leaves the local machine, so a unit
containing a secret must be blocked from analysis, not merely redacted later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Conservative, low-false-positive patterns. The goal is to refuse obviously
# secret-bearing units, not to be a full secret scanner.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("generic_secret_assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key)\b\s*[:=]\s*"
        r"['\"][A-Za-z0-9_\-./+=]{16,}['\"]"
    )),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
)


@dataclass(frozen=True)
class SecretHit:
    kind: str
    line: int


def scan(text: str) -> list[SecretHit]:
    """Return secret hits (kind + 1-based line number) found in ``text``."""
    hits: list[SecretHit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            if pattern.search(line):
                hits.append(SecretHit(kind=kind, line=line_no))
    return hits


def has_secret(text: str) -> bool:
    return bool(scan(text))
