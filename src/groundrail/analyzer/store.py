"""Storage for AI unit analyses, with stale detection against the unit index."""

from __future__ import annotations

from typing import Any

from ..core import envelope
from ..core.errors import NotFoundError
from ..core.store import ArtifactStore


def analysis_path(unit_id: str) -> str:
    return f"analysis/units/{unit_id}.json"


class AnalysisStore:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def write(self, analysis: dict[str, Any], *, source: dict[str, Any], command: str) -> str:
        artifact = envelope.build_envelope(
            artifact_id=analysis["analysis_id"],
            artifact_kind="unit_analysis",
            generator=envelope.make_generator(command, "groundrail.analyzer"),
            source=source,
            data=analysis,
        )
        path = analysis_path(analysis["unit_id"])
        self.store.write_json(path, artifact)
        return path

    def get(self, unit_id: str) -> dict[str, Any]:
        path = analysis_path(unit_id)
        if not self.store.exists(path):
            raise NotFoundError(f"no analysis for unit: {unit_id}")
        return self.store.read_json(path)["data"]

    def try_get(self, unit_id: str) -> dict[str, Any] | None:
        try:
            return self.get(unit_id)
        except NotFoundError:
            return None

    def all(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        units_dir = self.store.resolve("analysis/units")
        if not units_dir.is_dir():
            return out
        for path in sorted(units_dir.glob("*.json")):
            out.append(self.store.read_json(path.relative_to(self.store.root))["data"])
        return out

    def is_stale(self, analysis: dict[str, Any], unit: dict[str, Any]) -> bool:
        """An analysis is stale if its unit hash no longer matches the index."""
        recorded = analysis.get("analysis_provenance", {}).get("unit_hash")
        return recorded != unit.get("snippet_hash")
