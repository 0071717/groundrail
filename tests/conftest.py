"""Shared fixtures: a temporary project with known Python sources + a workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundrail.core.workspace import Workspace

USERS_PY = '''\
import os
from app.repo import search


def search_users(query, limit=10):
    if not query:
        return []
    results = search(query)
    return results[:limit]


class UserService:
    def __init__(self, repo):
        self.repo = repo

    def find(self, uid):
        return self.repo.get(uid)


def outer():
    def inner():
        return 1
    return inner()


def test_search_users():
    assert search_users("x") == []
'''

ROUTES_PY = '''\
from fastapi import APIRouter

router = APIRouter()


@router.get("/users/search")
async def search_endpoint(q: str):
    return {"q": q}
'''

MODELS_PY = '''\
from pydantic import BaseModel


class UserIn(BaseModel):
    name: str
    age: int
'''

SECRETS_PY = '''\
def connect():
    password = "supersecretpassword12345"
    return password
'''


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "app" / "api").mkdir(parents=True)
    (tmp_path / "app" / "services" / "users.py").write_text(USERS_PY, encoding="utf-8")
    (tmp_path / "app" / "api" / "routes.py").write_text(ROUTES_PY, encoding="utf-8")
    (tmp_path / "app" / "models.py").write_text(MODELS_PY, encoding="utf-8")
    (tmp_path / "app" / "secretsmod.py").write_text(SECRETS_PY, encoding="utf-8")
    return tmp_path


@pytest.fixture
def workspace(project: Path) -> Workspace:
    ws = Workspace(project)
    ws.init(repo_name="api")
    return ws


@pytest.fixture
def indexed_workspace(workspace: Workspace) -> Workspace:
    from groundrail.indexer.snapshot import SourceSnapshotter
    from groundrail.indexer.unit_index import UnitIndexBuilder

    SourceSnapshotter(workspace).run()
    UnitIndexBuilder(workspace).build()
    return workspace
