"""Time helpers. All timestamps are UTC ISO-8601 with a trailing ``Z``."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string, e.g. ``2026-06-08T00:00:00Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_iso(value: object) -> bool:
    """Best-effort check that ``value`` looks like our ISO-8601 timestamp format."""
    if not isinstance(value, str) or not value:
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(candidate)
        return True
    except ValueError:
        return False
