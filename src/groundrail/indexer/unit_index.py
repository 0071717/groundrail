"""Unit index builder and store.

Reads the file index, runs the Python extractor over source files, and writes the
deterministic unit index plus derived import/call-candidate indexes. The
``UnitStore`` provides lookups for the CLI and downstream components.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import envelope
from ..core.errors import NotFoundError
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from . import python_units
from .snapshot import FILE_INDEX_PATH, load_file_index

UNIT_INDEX_PATH = "index/unit-index.json"
IMPORT_INDEX_PATH = "index/import-index.json"
CALL_CANDIDATES_PATH = "index/call-candidates.json"


class UnitIndexBuilder:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store

    def build(self, *, command: str = "groundrail index units") -> dict[str, Any]:
        if not self.store.exists(FILE_INDEX_PATH):
            raise NotFoundError("no file-index; run `groundrail snapshot` first")

        file_envelope = self.store.read_json(FILE_INDEX_PATH)
        source = file_envelope.get("source", envelope.make_source())
        source_commit = source.get("source_commit", "unknown")

        units: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        for record in load_file_index(self.store):
            if record.get("language") != "python" or record.get("classification") == "generated":
                if record.get("language") in ("typescript", "javascript"):
                    gaps.append(
                        {
                            "kind": "typescript_unsupported",
                            "repo": record.get("repo", ""),
                            "location": record.get("path", ""),
                            "detail": "TypeScript/React extraction not yet implemented (revised roadmap Phase 6)",
                            "severity": "info",
                            "state": "unsupported",
                        }
                    )
                continue
            repo_root = self.workspace.repo_root(record["repo"])
            text = _read(repo_root / record["path"])
            if text is None:
                continue
            extracted = python_units.extract_file(
                repo=record["repo"],
                file_path=record["path"],
                source_text=text,
                source_commit=source_commit,
            )
            units.extend(extracted.units)
            gaps.extend(extracted.gaps)

        artifact = envelope.build_envelope(
            artifact_id="groundrail.index.unit",
            artifact_kind="unit_index",
            generator=envelope.make_generator(command, "groundrail.index.units"),
            source=source,
            data={"units": units, "unit_count": len(units)},
        )
        self.store.write_json(UNIT_INDEX_PATH, artifact)
        self._write_derived(units, source, command)
        if gaps:
            from ..core.gaps import CapabilityGapRegistry

            registry = CapabilityGapRegistry(self.store)
            registry.extend(gaps)
            registry.write(command=command, source=source)
        return artifact

    def _write_derived(self, units: list[dict[str, Any]], source: dict[str, Any], command: str) -> None:
        import_rows = [
            {"unit_id": u["unit_id"], "imports": u["imports"]} for u in units if u["imports"]
        ]
        call_rows = [
            {"unit_id": u["unit_id"], "call_candidates": u["call_candidates"]}
            for u in units
            if u["call_candidates"]
        ]
        self.store.write_json(
            IMPORT_INDEX_PATH,
            envelope.build_envelope(
                artifact_id="groundrail.index.import",
                artifact_kind="import_index",
                generator=envelope.make_generator(command, "groundrail.index.units"),
                source=source,
                data={"imports": import_rows},
            ),
        )
        self.store.write_json(
            CALL_CANDIDATES_PATH,
            envelope.build_envelope(
                artifact_id="groundrail.index.call_candidates",
                artifact_kind="call_candidates",
                generator=envelope.make_generator(command, "groundrail.index.units"),
                source=source,
                data={"calls": call_rows},
            ),
        )


class UnitStore:
    """Read access to the unit index."""

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def all(self) -> list[dict[str, Any]]:
        if not self.store.exists(UNIT_INDEX_PATH):
            return []
        return self.store.read_json(UNIT_INDEX_PATH).get("data", {}).get("units", [])

    def get(self, unit_id: str) -> dict[str, Any]:
        for unit in self.all():
            if unit["unit_id"] == unit_id:
                return unit
        raise NotFoundError(f"unknown unit: {unit_id}")

    def filter(
        self,
        *,
        kind: str | None = None,
        path: str | None = None,
        complexity: str | None = None,
    ) -> list[dict[str, Any]]:
        units = self.all()
        if kind:
            units = [u for u in units if u["kind"] == kind]
        if path:
            units = [u for u in units if path in u["file_path"]]
        if complexity:
            units = [u for u in units if u["complexity"]["state"] == complexity]
        return units


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
