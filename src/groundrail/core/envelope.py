"""The artifact envelope — the metadata wrapper every canonical artifact carries.

The payload lives under ``data``; the envelope records what produced it, against
which source commit, and its validation state. This mirrors the formal envelope
contract in ``docs/02_CONTRACTS_AND_ARTIFACTS.md`` (the per-artifact examples in
that doc show payload shapes which we nest under ``data``).
"""

from __future__ import annotations

from typing import Any

from . import timeutil

SCHEMA_VERSION = "1"
GENERATOR_VERSION = "0.1.0"

REQUIRED_ENVELOPE_FIELDS = (
    "schema_version",
    "artifact_id",
    "artifact_kind",
    "generated_at",
    "generator",
    "source",
    "validation",
    "data",
)

REQUIRED_GENERATOR_FIELDS = ("id", "version", "command")
REQUIRED_SOURCE_FIELDS = (
    "repo",
    "source_commit",
    "dirty_worktree",
    "file_manifest_hash",
)
REQUIRED_VALIDATION_FIELDS = (
    "status",
    "validated_at",
    "validator",
    "errors",
    "warnings",
)


def make_generator(command: str, generator_id: str = "groundrail") -> dict[str, Any]:
    return {"id": generator_id, "version": GENERATOR_VERSION, "command": command}


def make_source(
    repo: str = "workspace",
    source_commit: str = "unknown",
    dirty_worktree: bool = False,
    file_manifest_hash: str = "",
) -> dict[str, Any]:
    return {
        "repo": repo,
        "source_commit": source_commit,
        "dirty_worktree": dirty_worktree,
        "file_manifest_hash": file_manifest_hash,
    }


def make_validation(status: str = "ok", validator: str = "groundrail.validate") -> dict[str, Any]:
    return {
        "status": status,
        "validated_at": timeutil.now_iso(),
        "validator": validator,
        "errors": [],
        "warnings": [],
    }


def build_envelope(
    *,
    artifact_id: str,
    artifact_kind: str,
    generator: dict[str, Any],
    source: dict[str, Any],
    data: dict[str, Any],
    validation: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a complete artifact object (envelope + ``data`` payload)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "generated_at": generated_at or timeutil.now_iso(),
        "generator": generator,
        "source": source,
        "validation": validation or make_validation(),
        "data": data,
    }


def validate_envelope(obj: Any) -> list[str]:
    """Return a list of human-readable problems with an artifact's envelope.

    An empty list means the envelope shape is valid (it does not check payload).
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["artifact is not a JSON object"]

    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in obj:
            errors.append(f"missing envelope field: {field}")

    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {obj.get('schema_version')!r} (expected {SCHEMA_VERSION!r})"
        )

    if not timeutil.is_iso(obj.get("generated_at")):
        errors.append("generated_at is not a valid ISO-8601 timestamp")

    generator = obj.get("generator")
    if isinstance(generator, dict):
        for field in REQUIRED_GENERATOR_FIELDS:
            if field not in generator:
                errors.append(f"missing generator field: {field}")
    elif "generator" in obj:
        errors.append("generator must be an object")

    source = obj.get("source")
    if isinstance(source, dict):
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in source:
                errors.append(f"missing source field: {field}")
    elif "source" in obj:
        errors.append("source must be an object")

    validation = obj.get("validation")
    if isinstance(validation, dict):
        for field in REQUIRED_VALIDATION_FIELDS:
            if field not in validation:
                errors.append(f"missing validation field: {field}")
    elif "validation" in obj:
        errors.append("validation must be an object")

    if "data" in obj and not isinstance(obj["data"], dict):
        errors.append("data must be an object")

    return errors
