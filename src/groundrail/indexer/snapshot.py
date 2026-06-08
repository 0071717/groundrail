"""Source snapshot and file index.

Records what files exist, their hashes, classification, and the git state of each
configured repository. This is Layer 0 — no code understanding, only facts.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..core import envelope, hashing, ids
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from . import gitstate

SNAPSHOT_PATH = "source/snapshot.json"
FILE_INDEX_PATH = "index/file-index.json"
RUN_MANIFEST_PATH = "audit/run-manifest.json"

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
_GENERATED_HINTS = ("generated", ".gen.", "_pb2", ".min.")


def _language_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".py":
        return "python"
    if ext in (".ts", ".tsx"):
        return "typescript"
    if ext in (".js", ".jsx"):
        return "javascript"
    return "other"


def _classify(path: Path) -> str:
    name = path.name.lower()
    if any(hint in name for hint in _GENERATED_HINTS):
        return "generated"
    if name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".test.tsx")):
        return "test"
    if path.suffix.lower() in _SOURCE_EXTS:
        return "source"
    return "other"


def _is_ignored(rel_parts: tuple[str, ...], ignore: list[str]) -> bool:
    for part in rel_parts:
        if part in ignore:
            return True
    rel = "/".join(rel_parts)
    return any(fnmatch.fnmatch(rel, pat) for pat in ignore)


class SourceSnapshotter:
    """Scans configured repositories and writes the snapshot + file index."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store

    def run(self, *, command: str = "groundrail snapshot") -> dict[str, Any]:
        config = self.workspace.load_config()
        ignore = config.get("ignore", [])
        repositories: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        missing: list[str] = []

        for entry in config.get("repositories", []):
            repo = entry.get("repo", "repo")
            repo_root = (self.workspace.project_root / entry.get("path", ".")).resolve()
            if not repo_root.exists():
                missing.append(repo)
                repositories.append({**entry, "exists": False})
                continue

            git = gitstate.read_state(repo_root)
            repo_files = self._scan_repo(repo, repo_root, ignore)
            files.extend(repo_files)
            repositories.append(
                {
                    "repo": repo,
                    "path": entry.get("path", "."),
                    "role": entry.get("role", "primary"),
                    "language": entry.get("language", "python"),
                    "framework": entry.get("framework", ""),
                    "git_branch": git["branch"],
                    "git_commit": git["commit"],
                    "dirty_worktree": git["dirty"],
                    "exists": True,
                }
            )

        manifest_hash = hashing.sha256_text(
            "".join(sorted(f"{f['path']}:{f['sha256']}" for f in files))
        )
        primary = repositories[0] if repositories else {}
        source = envelope.make_source(
            repo=primary.get("repo", "workspace"),
            source_commit=primary.get("git_commit", "unknown"),
            dirty_worktree=bool(primary.get("dirty_worktree", False)),
            file_manifest_hash=manifest_hash,
        )

        snapshot = envelope.build_envelope(
            artifact_id="groundrail.source.snapshot",
            artifact_kind="source_snapshot",
            generator=envelope.make_generator(command, "groundrail.source"),
            source=source,
            data={
                "repositories": repositories,
                "file_count": len(files),
                "missing": missing,
            },
        )
        file_index = envelope.build_envelope(
            artifact_id="groundrail.index.file",
            artifact_kind="file_index",
            generator=envelope.make_generator(command, "groundrail.source"),
            source=source,
            data={"files": files},
        )
        self.store.write_json(SNAPSHOT_PATH, snapshot)
        self.store.write_json(FILE_INDEX_PATH, file_index)
        self._write_manifest(command, source)
        return snapshot

    def _scan_repo(self, repo: str, repo_root: Path, ignore: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(repo_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root)
            if _is_ignored(rel.parts, ignore):
                continue
            if path.suffix.lower() not in _SOURCE_EXTS:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            rel_str = rel.as_posix()
            records.append(
                {
                    "file_id": ids.file_id(repo, rel_str),
                    "repo": repo,
                    "path": rel_str,
                    "language": _language_for(path),
                    "classification": _classify(path),
                    "line_count": text.count("\n") + 1,
                    "size_bytes": len(data),
                    "sha256": hashing.sha256_bytes(data),
                    "generated": _classify(path) == "generated",
                    "ignored": False,
                }
            )
        return records

    def _write_manifest(self, command: str, source: dict[str, Any]) -> None:
        manifest = envelope.build_envelope(
            artifact_id="groundrail.audit.run_manifest",
            artifact_kind="run_manifest",
            generator=envelope.make_generator(command, "groundrail.audit"),
            source=source,
            data={"command": command},
        )
        self.store.write_json(RUN_MANIFEST_PATH, manifest)


def load_file_index(store: ArtifactStore) -> list[dict[str, Any]]:
    if not store.exists(FILE_INDEX_PATH):
        return []
    return store.read_json(FILE_INDEX_PATH).get("data", {}).get("files", [])
