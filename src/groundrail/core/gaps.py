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

    def add(self, *, kind: str, repo: str, location: str, detail: str, severity: str = "info") -> None:
        self._gaps.append(
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
        self._gaps.extend(gaps)

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
