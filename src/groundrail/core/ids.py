"""Stable, deterministic id construction.

Unit ids are derived from repo + module path + qualified symbol so they are
reproducible across runs. They intentionally change when a symbol is renamed or
moved — confirmations are bound to a specific id and should not silently follow
a rename (see the unit-id-stability discussion in docs/09).
"""

from __future__ import annotations

import re

_SAFE = re.compile(r"[^A-Za-z0-9_.]+")


def module_path_from_file(file_path: str) -> str:
    """Convert ``app/services/users.py`` -> ``app.services.users``."""
    path = file_path.replace("\\", "/")
    if path.endswith(".py"):
        path = path[:-3]
    elif path.endswith((".ts", ".tsx", ".js", ".jsx")):
        path = path.rsplit(".", 1)[0]
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _clean(text: str) -> str:
    # Replace unsafe characters only. Do NOT strip underscores: dunder names like
    # ``__init__`` are valid identifiers and must survive intact.
    return _SAFE.sub("_", text)


def unit_id(repo: str, file_path: str, qualified_symbol: str) -> str:
    """Build a stable unit id: ``unit.<repo>.<module>.<qualified_symbol>``."""
    module = module_path_from_file(file_path)
    body = ".".join(p for p in (module, qualified_symbol) if p)
    return f"unit.{_clean(repo)}.{_clean(body)}"


def analysis_id(unit_identifier: str) -> str:
    """Derive the analysis id for a unit: ``analysis.<unit-body>``."""
    body = unit_identifier[len("unit.") :] if unit_identifier.startswith("unit.") else unit_identifier
    return f"analysis.{body}"


def file_id(repo: str, file_path: str) -> str:
    module = module_path_from_file(file_path)
    suffix = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    return f"file.{_clean(repo)}.{_clean(module)}.{_clean(suffix)}" if suffix else f"file.{_clean(repo)}.{_clean(module)}"


def evidence_id(unit_identifier: str, kind: str) -> str:
    body = unit_identifier[len("unit.") :] if unit_identifier.startswith("unit.") else unit_identifier
    return f"ev.{body}.{_clean(kind)}"
