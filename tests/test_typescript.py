"""TypeScript/React extractor tests: masking, boundaries, classification, gaps."""

from __future__ import annotations

from pathlib import Path

from groundrail.core import hashing
from groundrail.core.workspace import Workspace
from groundrail.indexer import typescript_units
from groundrail.indexer.snapshot import SourceSnapshotter
from groundrail.indexer.ts_mask import mask_source, match_delimiter
from groundrail.indexer.unit_index import UnitIndexBuilder, UnitStore

USERLIST_TSX = '''\
import React, { useState } from 'react';
import { fetchUsers } from '../api/users';

export function UserList({ initial }: Props) {
  const [users, setUsers] = useState(initial);
  if (!users) {
    return null;
  }
  return (
    <ul>
      {users.map((u) => (
        <li key={u.id}>{u.name}</li>
      ))}
    </ul>
  );
}

export const UserBadge = ({ name }: { name: string }) => {
  return <span className="badge">{name}</span>;
};

export function useUsers(query: string) {
  const [data, setData] = useState(null);
  return data;
}

export async function loadUsers(query: string) {
  const res = await fetch(`/api/users?q=${query}`);
  return res.json();
}

const helper = (x: number) => x * 2;

const Lazy = React.lazy(() => import('./Heavy'));
'''


def _extract():
    return typescript_units.extract_file(
        repo="web", file_path="src/features/UserList.tsx",
        source_text=USERLIST_TSX, source_commit="c0",
    )


def _by_name(units):
    return {u["symbol"]: u for u in units}


def test_mask_blanks_strings_and_comments_preserving_offsets():
    src = 'const a = "hello {"; // brace } in comment\nconst b = 1;'
    masked = mask_source(src)
    assert len(masked) == len(src)
    # the brace inside the string/comment must be gone from the mask
    assert "{" not in masked
    assert "}" not in masked
    assert "const b = 1;" in masked


def test_brace_matching_ignores_braces_in_strings():
    src = 'function f() { const s = "}"; return 1; }'
    masked = mask_source(src)
    open_idx = masked.index("{")
    close_idx = match_delimiter(masked, open_idx, "{", "}")
    assert src[close_idx] == "}"
    assert close_idx == len(src) - 1  # the real closing brace, not the one in the string


def test_classification_of_components_hooks_api_and_functions():
    units = _by_name(_extract().units)
    assert units["UserList"]["kind"] == "react_component"
    assert units["UserBadge"]["kind"] == "react_component"
    assert units["useUsers"]["kind"] == "react_hook"
    assert units["loadUsers"]["kind"] == "api_client_function"
    assert units["helper"]["kind"] == "typescript_function"


def test_ts_units_are_inferred_not_verified():
    # Regex boundaries must never masquerade as verified truth (docs/04, docs/09).
    for unit in _extract().units:
        assert unit["state"] == "inferred"
        assert unit["confidence"] == "medium"


def test_used_imports_resolved_from_import_map():
    units = _by_name(_extract().units)
    assert units["UserList"]["imports"] == ["react"]


def test_snippet_hash_matches_source_slice():
    units = _by_name(_extract().units)
    unit = units["UserList"]
    span = unit["span"]
    snippet = "\n".join(USERLIST_TSX.splitlines()[span["start_line"] - 1 : span["end_line"]])
    assert unit["snippet_hash"] == hashing.sha256_text(snippet)
    assert snippet.strip().endswith("}")


def test_call_candidates_found():
    units = _by_name(_extract().units)
    targets = {c["target_text"] for c in units["loadUsers"]["call_candidates"]}
    assert "fetch" in targets


def test_dynamic_pattern_gaps_emitted():
    gaps = {g["kind"] for g in _extract().gaps}
    assert "react_lazy" in gaps
    assert "dynamic_import" in gaps


def test_unit_ids_stable_across_commit():
    a = sorted(u["unit_id"] for u in _extract().units)
    b = typescript_units.extract_file(
        repo="web", file_path="src/features/UserList.tsx",
        source_text=USERLIST_TSX, source_commit="c9",
    ).units
    assert a == sorted(u["unit_id"] for u in b)
    assert "unit.web.features.UserList.UserList" in a


def test_integration_through_unit_index(tmp_path: Path):
    (tmp_path / "src" / "features").mkdir(parents=True)
    (tmp_path / "src" / "features" / "UserList.tsx").write_text(USERLIST_TSX, encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.init(repo_name="web")
    SourceSnapshotter(ws).run()
    UnitIndexBuilder(ws).build()

    units = {u["symbol"]: u for u in UnitStore(ws.store).all()}
    assert units["UserList"]["kind"] == "react_component"
    assert units["useUsers"]["kind"] == "react_hook"
    from groundrail.core.gaps import CapabilityGapRegistry

    gap_kinds = {g["kind"] for g in CapabilityGapRegistry(ws.store).load()}
    assert "react_lazy" in gap_kinds
