"""End-to-end CLI tests through ``main()`` against a temp project."""

from __future__ import annotations

import os

import pytest

from groundrail.cli.main import main


@pytest.fixture
def in_project(project, monkeypatch):
    monkeypatch.chdir(project)
    # ensure Kiro/AI commands are not inherited from the real environment
    monkeypatch.delenv("GROUNDRAIL_KIRO_CMD", raising=False)
    monkeypatch.delenv("GROUNDRAIL_AI_CMD", raising=False)
    return project


def test_full_deterministic_flow(in_project, capsys):
    assert main(["init", "--repo", "api"]) == 0
    assert main(["snapshot"]) == 0
    assert main(["index", "units"]) == 0
    capsys.readouterr()

    assert main(["unit", "list"]) == 0
    out = capsys.readouterr().out
    assert "unit.api.app.services.users.search_users" in out

    assert main(["unit", "show", "unit.api.app.services.users.search_users"]) == 0
    assert "python_function" in capsys.readouterr().out

    assert main(["search", "user search"]) == 0
    assert "search_users" in capsys.readouterr().out

    assert main(["prepare", "ask", "how", "does", "user", "search", "work"]) == 0
    assert "Context pack" in capsys.readouterr().out

    assert main(["validate", "--strict"]) == 0
    assert "validate: ok" in capsys.readouterr().out


def test_status_and_doctor(in_project, capsys):
    main(["init", "--repo", "api"])
    main(["snapshot"])
    main(["index", "units"])
    capsys.readouterr()

    assert main(["status"]) == 0
    assert "units:" in capsys.readouterr().out

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "AI command:" in out
    assert "unset" in out  # no AI command configured in test env


def test_ask_degraded_mode_without_kiro(in_project, capsys):
    main(["init", "--repo", "api"])
    main(["snapshot"])
    main(["index", "units"])
    capsys.readouterr()

    rc = main(["ask", "how", "does", "search", "work"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Kiro not configured" in out


def test_unknown_unit_returns_error_code(in_project):
    main(["init", "--repo", "api"])
    main(["snapshot"])
    main(["index", "units"])
    rc = main(["unit", "show", "unit.api.nope"])
    assert rc == 6  # NotFoundError exit code


def test_init_writes_self_ignore(in_project):
    main(["init", "--repo", "api"])
    gitignore = in_project / ".groundrail" / ".gitignore"
    assert gitignore.exists()
    assert "*" in gitignore.read_text(encoding="utf-8")
