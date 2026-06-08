"""Typed errors for Groundrail.

Commands catch :class:`GroundrailError` and turn it into a clean non-zero exit
with a readable message, rather than a traceback.
"""

from __future__ import annotations


class GroundrailError(Exception):
    """Base class for all expected Groundrail failures."""

    exit_code = 1


class WorkspaceError(GroundrailError):
    """Raised when the ``.groundrail`` workspace is missing or unusable."""


class ConfigError(GroundrailError):
    """Raised for missing or invalid configuration (including env vars)."""

    exit_code = 2


class ValidationError(GroundrailError):
    """Raised when an artifact fails strict validation."""

    exit_code = 3

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class StaleError(GroundrailError):
    """Raised when source-backed evidence no longer matches current source."""

    exit_code = 4


class SecretError(GroundrailError):
    """Raised when a unit selected for AI analysis appears to contain secrets."""

    exit_code = 5


class NotFoundError(GroundrailError):
    """Raised when a requested unit/analysis/session id does not exist."""

    exit_code = 6
