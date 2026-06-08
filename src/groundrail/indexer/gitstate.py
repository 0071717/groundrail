"""Best-effort git state reader.

Groundrail does not require git, but when present it records the commit and
dirty state so artifacts can be tied to a source revision.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def read_state(repo_root: Path) -> dict[str, object]:
    """Return ``{branch, commit, dirty}`` for ``repo_root`` (defaults if no git)."""
    commit = _run(["git", "rev-parse", "HEAD"], repo_root)
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    status = _run(["git", "status", "--porcelain"], repo_root)
    return {
        "branch": branch or "",
        "commit": commit or "unknown",
        "dirty": bool(status) if status is not None else False,
    }
