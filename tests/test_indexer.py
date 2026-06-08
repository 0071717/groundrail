"""Indexer tests: snapshot, Python unit extraction, ids, complexity, gaps."""

from __future__ import annotations

from groundrail.core import hashing
from groundrail.indexer import python_units
from groundrail.indexer.snapshot import SourceSnapshotter, load_file_index
from groundrail.indexer.unit_index import UnitIndexBuilder, UnitStore
from tests.conftest import USERS_PY


def _units_by_symbol(units):
    return {u["qualified_name"]: u for u in units}


def test_extract_python_units_kinds_and_spans():
    result = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    by_name = _units_by_symbol(result.units)

    assert by_name["search_users"]["kind"] == "python_function"
    assert by_name["UserService"]["kind"] == "python_class"
    assert by_name["UserService.find"]["kind"] == "python_method"
    assert by_name["UserService.__init__"]["kind"] == "python_method"
    # nested function captured with dotted qualified name
    assert by_name["outer.inner"]["kind"] == "python_function"
    # module-level test_ function recognised as a test unit
    assert by_name["test_search_users"]["kind"] == "test_function"


def test_span_snippet_hash_matches_source_slice():
    result = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    unit = _units_by_symbol(result.units)["search_users"]
    span = unit["span"]
    lines = USERS_PY.splitlines()
    snippet = "\n".join(lines[span["start_line"] - 1 : span["end_line"]])
    assert unit["snippet_hash"] == hashing.sha256_text(snippet)
    assert snippet.startswith("def search_users")


def test_imports_only_those_used_in_unit():
    result = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    unit = _units_by_symbol(result.units)["search_users"]
    assert unit["imports"] == ["app.repo"]  # 'os' imported but unused here


def test_call_candidates_and_complexity():
    result = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    unit = _units_by_symbol(result.units)["search_users"]
    targets = {c["target_text"] for c in unit["call_candidates"]}
    assert "search" in targets
    assert unit["complexity"]["branch_count"] >= 1
    assert unit["complexity"]["state"] in ("simple", "moderate", "complex")


def test_unit_ids_are_stable_and_namespaced():
    a = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    b = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c1"
    )
    ids_a = sorted(u["unit_id"] for u in a.units)
    ids_b = sorted(u["unit_id"] for u in b.units)
    assert ids_a == ids_b  # commit change does not move ids
    assert "unit.api.app.services.users.search_users" in ids_a


def test_dunder_method_id_not_truncated():
    result = python_units.extract_file(
        repo="api", file_path="app/services/users.py", source_text=USERS_PY, source_commit="c0"
    )
    ids = {u["unit_id"] for u in result.units}
    assert "unit.api.app.services.users.UserService.__init__" in ids


def test_fastapi_endpoint_and_pydantic_detection(indexed_workspace):
    units = UnitStore(indexed_workspace.store).all()
    by_name = {u["qualified_name"]: u for u in units}
    endpoint = by_name["search_endpoint"]
    assert endpoint["kind"] == "fastapi_endpoint_handler"
    candidates = endpoint["related_candidates"]["endpoint_candidates"]
    assert candidates and candidates[0]["method"] == "GET"
    assert candidates[0]["path"] == "/users/search"
    assert by_name["UserIn"]["kind"] == "pydantic_model"


def test_syntax_error_becomes_capability_gap(tmp_path):
    from groundrail.core.workspace import Workspace

    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.init(repo_name="api")
    SourceSnapshotter(ws).run()
    UnitIndexBuilder(ws).build()
    from groundrail.core.gaps import CapabilityGapRegistry

    gaps = CapabilityGapRegistry(ws.store).load()
    assert any(g["kind"] == "python_syntax_error" for g in gaps)


def test_snapshot_records_files_and_hashes(workspace):
    SourceSnapshotter(workspace).run()
    files = load_file_index(workspace.store)
    paths = {f["path"] for f in files}
    assert "app/services/users.py" in paths
    for f in files:
        assert f["sha256"].startswith("sha256:")
