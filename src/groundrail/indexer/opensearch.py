"""OpenSearch schema/config indexing.

Groundrail cannot verify runtime data-layer behaviour from static config alone,
but it can identify index/mapping artifacts and make them visible to flows and
impact reports as explicit inferred resources.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..core import envelope, hashing, ids, vocab
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from .snapshot import FILE_INDEX_PATH, load_file_index

OPENSEARCH_INDEX_PATH = "index/opensearch-resources.json"
_INDEX_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,}$")


class OpenSearchResourceIndexer:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store

    def build(self, *, command: str = "groundrail index opensearch") -> dict[str, Any]:
        source = self.store.read_json(FILE_INDEX_PATH).get("source", envelope.make_source()) if self.store.exists(FILE_INDEX_PATH) else envelope.make_source()
        resources: list[dict[str, Any]] = []
        for record in load_file_index(self.store):
            if record.get("classification") != "opensearch_schema":
                continue
            repo_root = self.workspace.repo_root(record["repo"])
            path = repo_root / record["path"]
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            resources.extend(self._extract(record, path, text, source.get("source_commit", "unknown")))
        artifact = envelope.build_envelope(
            artifact_id="groundrail.index.opensearch_resources",
            artifact_kind="opensearch_resource_index",
            generator=envelope.make_generator(command, "groundrail.index.opensearch"),
            source=source,
            data={"resources": resources, "resource_count": len(resources)},
        )
        self.store.write_json(OPENSEARCH_INDEX_PATH, artifact)
        return artifact

    def _extract(self, record: dict[str, Any], path: Path, text: str, source_commit: str) -> list[dict[str, Any]]:
        names = set(_names_from_path(record["path"]))
        if path.suffix.lower() == ".json":
            try:
                obj = json.loads(text)
                names.update(_names_from_json(obj))
            except json.JSONDecodeError:
                pass
        for m in re.finditer(r"(?:index|index_name|indexName|alias)\s*[:=]\s*['\"]([^'\"]+)['\"]", text):
            if _INDEX_NAME_RE.match(m.group(1)):
                names.add(m.group(1))
        file_hash = hashing.sha256_text(text)
        return [
            {
                "resource_id": _resource_id(record["repo"], name),
                "resource_type": "opensearch_index_or_alias",
                "repo": record["repo"],
                "name": name,
                "file_path": record["path"],
                "file_hash": file_hash,
                "source_commit": source_commit,
                "state": vocab.STATUS_INFERRED,
                "confidence": vocab.CONFIDENCE_MEDIUM,
                "evidence": [
                    {
                        "evidence_id": f"ev.opensearch.{record['repo']}.{name}",
                        "evidence_kind": "config_value",
                        "repo": record["repo"],
                        "file_path": record["path"],
                        "source_commit": source_commit,
                        "file_hash": file_hash,
                        "span": {"start_line": 1, "end_line": max(1, text.count("\n") + 1), "start_col": 1, "end_col": 1},
                        "snippet_hash": file_hash,
                        "extractor": {"id": "groundrail.opensearch.resources", "kind": "config_regex_json"},
                    }
                ],
            }
            for name in sorted(names)
        ]


def load_opensearch_resources(store: ArtifactStore) -> list[dict[str, Any]]:
    if not store.exists(OPENSEARCH_INDEX_PATH):
        return []
    return store.read_json(OPENSEARCH_INDEX_PATH).get("data", {}).get("resources", [])


def _resource_id(repo: str, name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    return f"resource.{repo}.opensearch.{safe}"


def _names_from_path(path: str) -> set[str]:
    stem = Path(path).stem
    parts = re.split(r"[/.]", path.lower())
    names = {stem} if _INDEX_NAME_RE.match(stem) else set()
    for marker in ("indices", "indexes", "mappings", "templates"):
        if marker in parts:
            i = parts.index(marker)
            if i + 1 < len(parts):
                cand = re.sub(r"\.(json|yaml|yml)$", "", parts[i + 1])
                if _INDEX_NAME_RE.match(cand):
                    names.add(cand)
    return names


def _names_from_json(obj: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("index", "index_name", "indexName", "alias") and isinstance(value, str) and _INDEX_NAME_RE.match(value):
                names.add(value)
            if key in ("index_patterns", "aliases"):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and _INDEX_NAME_RE.match(item.replace("*", "")):
                            names.add(item)
                elif isinstance(value, dict):
                    names.update(k for k in value if _INDEX_NAME_RE.match(k))
            names.update(_names_from_json(value))
    elif isinstance(obj, list):
        for item in obj:
            names.update(_names_from_json(item))
    return names
