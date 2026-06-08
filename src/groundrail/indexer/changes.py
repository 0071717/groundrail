"""Change detection between the recorded snapshot and the current working tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import envelope, hashing
from ..core.workspace import Workspace
from .snapshot import FILE_INDEX_PATH, load_file_index

CHANGED_PATH = "change/changed-files.json"


class ChangeDetector:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store = workspace.store

    def detect(self, *, command: str = "groundrail changed") -> dict[str, Any]:
        if not self.store.exists(FILE_INDEX_PATH):
            raise FileNotFoundError("no file-index; run `groundrail snapshot` first")

        indexed = {f["path"]: f for f in load_file_index(self.store)}
        current = self._current_hashes()

        added = sorted(set(current) - set(indexed))
        removed = sorted(set(indexed) - set(current))
        modified = sorted(
            path
            for path in set(current) & set(indexed)
            if current[path] != indexed[path]["sha256"]
        )

        envelope_obj = self.store.read_json(FILE_INDEX_PATH)
        artifact = envelope.build_envelope(
            artifact_id="groundrail.change.files",
            artifact_kind="changed_files",
            generator=envelope.make_generator(command, "groundrail.change"),
            source=envelope_obj.get("source", envelope.make_source()),
            data={
                "added": added,
                "removed": removed,
                "modified": modified,
                "changed_count": len(added) + len(removed) + len(modified),
            },
        )
        self.store.write_json(CHANGED_PATH, artifact)
        return artifact

    def _current_hashes(self) -> dict[str, str]:
        config = self.workspace.load_config()
        ignore = config.get("ignore", [])
        result: dict[str, str] = {}
        from .snapshot import _SOURCE_EXTS, _is_ignored  # local import to avoid cycle

        for entry in config.get("repositories", []):
            repo_root = (self.workspace.project_root / entry.get("path", ".")).resolve()
            if not repo_root.exists():
                continue
            for path in repo_root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _SOURCE_EXTS:
                    continue
                rel = path.relative_to(repo_root)
                if _is_ignored(rel.parts, ignore):
                    continue
                try:
                    result[rel.as_posix()] = hashing.sha256_bytes(path.read_bytes())
                except OSError:
                    continue
        return result
