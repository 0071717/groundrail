"""JSON / JSONL storage with atomic, guarded writes.

This is the only place that touches artifact files on disk. Writes go to a temp
file and are atomically renamed so a crash never leaves a half-written artifact.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from .errors import GroundrailError


class ArtifactStore:
    """Reads and writes JSON and JSONL artifacts under a root directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- paths ---------------------------------------------------------------
    def resolve(self, relative: str | Path) -> Path:
        return self.root / relative

    # --- JSON ----------------------------------------------------------------
    def read_json(self, path: str | Path) -> Any:
        full = self.resolve(path)
        try:
            with full.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError as exc:
            raise GroundrailError(f"artifact not found: {full}") from exc
        except json.JSONDecodeError as exc:
            raise GroundrailError(f"malformed JSON in {full}: {exc}") from exc

    def write_json(self, path: str | Path, obj: Any) -> Path:
        full = self.resolve(path)
        _atomic_write(full, json.dumps(obj, indent=2, sort_keys=False) + "\n")
        return full

    def exists(self, path: str | Path) -> bool:
        return self.resolve(path).exists()

    # --- JSONL ---------------------------------------------------------------
    def read_jsonl(self, path: str | Path) -> list[Any]:
        return list(self.iter_jsonl(path))

    def iter_jsonl(self, path: str | Path) -> Iterator[Any]:
        full = self.resolve(path)
        if not full.exists():
            return
        with full.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GroundrailError(
                        f"malformed JSONL in {full} line {line_no}: {exc}"
                    ) from exc

    def write_jsonl(self, path: str | Path, rows: Iterable[Any]) -> Path:
        full = self.resolve(path)
        body = "".join(json.dumps(row, sort_keys=False) + "\n" for row in rows)
        _atomic_write(full, body)
        return full

    def append_jsonl(self, path: str | Path, row: Any) -> Path:
        full = self.resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        with full.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=False) + "\n")
        return full


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
