"""The Groundrail workspace: the ``.groundrail/`` directory and its config.

Per the docs/09 review, ``init`` creates a *lean* layout — only the directories
the implemented components use — rather than the full 15-directory tree. More
directories appear as later layers are implemented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import timeutil
from .errors import WorkspaceError
from .store import ArtifactStore

WORKSPACE_DIRNAME = ".groundrail"

# Lean layout for the implemented components (indexer / analyzer / router).
LEAN_DIRS = (
    "source",
    "index",
    "analysis/units",
    "cache",
    "sessions",
    "audit",
    "gaps",
)

CONFIG_PATH = "config.json"
GITIGNORE_PATH = ".gitignore"

# Privacy: AI analyses compress private business logic; this directory should
# never be committed. We drop a self-ignore file on init (see docs/09 §8).
_GITIGNORE_BODY = (
    "# Groundrail generates local, evidence + AI artifacts here.\n"
    "# These may contain compressed semantic detail about private code.\n"
    "# Do not commit this directory.\n"
    "*\n"
)


class Workspace:
    """Locates and initialises a ``.groundrail`` workspace."""

    def __init__(self, root: Path) -> None:
        self.project_root = Path(root).resolve()
        self.path = self.project_root / WORKSPACE_DIRNAME
        self.store = ArtifactStore(self.path)

    # --- discovery -----------------------------------------------------------
    @classmethod
    def find(cls, start: Path | None = None) -> "Workspace":
        """Walk upward from ``start`` to find an existing workspace."""
        current = Path(start or Path.cwd()).resolve()
        for candidate in (current, *current.parents):
            if (candidate / WORKSPACE_DIRNAME).is_dir():
                return cls(candidate)
        raise WorkspaceError(
            "no .groundrail workspace found; run `groundrail init` first"
        )

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    # --- lifecycle -----------------------------------------------------------
    def init(self, *, repo_name: str | None = None, force: bool = False) -> dict[str, Any]:
        """Create the lean workspace layout, config, and self-ignore file."""
        if self.path.exists() and not force:
            existing = self.load_config()
            return existing
        for rel in LEAN_DIRS:
            (self.path / rel).mkdir(parents=True, exist_ok=True)
        (self.path / GITIGNORE_PATH).write_text(_GITIGNORE_BODY, encoding="utf-8")

        name = repo_name or self.project_root.name
        config = {
            "version": "0.1.0",
            "created_at": timeutil.now_iso(),
            "repositories": [
                {
                    "repo": name,
                    "path": ".",
                    "role": "primary",
                    "language": "python",
                    "framework": "",
                }
            ],
            "ignore": [
                ".git",
                ".groundrail",
                "__pycache__",
                ".venv",
                "venv",
                "node_modules",
                "dist",
                "build",
                ".pytest_cache",
            ],
            "context_pack": {"token_budget": 6000},
        }
        self.store.write_json(CONFIG_PATH, config)
        return config

    def load_config(self) -> dict[str, Any]:
        if not self.store.exists(CONFIG_PATH):
            raise WorkspaceError("workspace config missing; re-run `groundrail init`")
        return self.store.read_json(CONFIG_PATH)

    def repo_root(self, repo: str) -> Path:
        for entry in self.load_config().get("repositories", []):
            if entry.get("repo") == repo:
                return (self.project_root / entry.get("path", ".")).resolve()
        raise WorkspaceError(f"unknown repo: {repo!r}")

    def primary_repo(self) -> dict[str, Any]:
        repos = self.load_config().get("repositories", [])
        if not repos:
            raise WorkspaceError("no repositories configured")
        return repos[0]
