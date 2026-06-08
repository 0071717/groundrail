"""Session store: each ask/prepare run gets its own session directory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.errors import NotFoundError
from ..core.store import ArtifactStore

LATEST_POINTER = "sessions/latest.json"


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"session-{stamp}"


class SessionStore:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def dir_for(self, session_id: str) -> str:
        return f"sessions/{session_id}"

    def create(self) -> str:
        session_id = new_session_id()
        (self.store.resolve(self.dir_for(session_id))).mkdir(parents=True, exist_ok=True)
        self.store.write_json(LATEST_POINTER, {"session_id": session_id})
        return session_id

    def latest_id(self) -> str:
        if not self.store.exists(LATEST_POINTER):
            raise NotFoundError("no sessions yet; run `groundrail prepare` or `ask`")
        return self.store.read_json(LATEST_POINTER)["session_id"]

    def write(self, session_id: str, name: str, obj: Any) -> Path:
        return self.store.write_json(f"{self.dir_for(session_id)}/{name}", obj)

    def write_text(self, session_id: str, name: str, text: str) -> Path:
        path = self.store.resolve(f"{self.dir_for(session_id)}/{name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, session_id: str, name: str) -> Any:
        return self.store.read_json(f"{self.dir_for(session_id)}/{name}")

    def has(self, session_id: str, name: str) -> bool:
        return self.store.exists(f"{self.dir_for(session_id)}/{name}")
