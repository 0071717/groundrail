"""Capability-gap registry.

When Groundrail recognises a pattern but lacks an extractor/adapter/rule for it,
it records an explicit gap instead of silently skipping. Gaps surface in CLI
output so the system stays honest about what it does not know.
"""

from __future__ import annotations

from typing import Any

from . import envelope
from .store import ArtifactStore

GAPS_PATH = "gaps/capability-gaps.json"


class CapabilityGapRegistry:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self._gaps: list[dict[str, Any]] = []
        self._keys: set[tuple[str, str, str, str]] = set()

    def add(self, *, kind: str, repo: str, location: str, detail: str, severity: str = "info") -> None:
        self._add_record(
            {
                "kind": kind,
                "repo": repo,
                "location": location,
                "detail": detail,
                "severity": severity,
                "state": "unsupported",
            }
        )

    def extend(self, gaps: list[dict[str, Any]]) -> None:
        for gap in gaps:
            if isinstance(gap, dict):
                self._add_record(gap)

    @property
    def gaps(self) -> list[dict[str, Any]]:
        return list(self._gaps)

    def write(self, *, command: str, source: dict[str, Any]) -> dict[str, Any]:
        artifact = envelope.build_envelope(
            artifact_id="groundrail.gaps.capability",
            artifact_kind="capability_gaps",
            generator=envelope.make_generator(command, "groundrail.gaps"),
            source=source,
            data={"gaps": self._gaps, "count": len(self._gaps)},
        )
        self.store.write_json(GAPS_PATH, artifact)
        return artifact

    def load(self) -> list[dict[str, Any]]:
        if not self.store.exists(GAPS_PATH):
            return []
        return self.store.read_json(GAPS_PATH).get("data", {}).get("gaps", [])

    def _add_record(self, gap: dict[str, Any]) -> None:
        normalised = {
            "kind": str(gap.get("kind", "unknown")),
            "repo": str(gap.get("repo", "")),
            "location": str(gap.get("location", "")),
            "detail": str(gap.get("detail", "")),
            "severity": str(gap.get("severity", "info")),
            "state": str(gap.get("state", "unsupported")),
        }
        key = (
            normalised["kind"],
            normalised["repo"],
            normalised["location"],
            normalised["detail"],
        )
        if key in self._keys:
            return
        self._keys.add(key)
        self._gaps.append(normalised)
