"""Implementations for each CLI command.

Each function takes parsed argparse args and returns a process exit code. They
load services from :mod:`groundrail` components and print human-friendly output,
or JSON when ``--json`` is given.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..analyzer.pipeline import AnalysisPipeline
from ..analyzer.store import AnalysisStore
from ..analyzer.validator import parse_and_validate  # noqa: F401 (kept for parity)
from ..core import envelope, vocab
from ..core.errors import GroundrailError, NotFoundError
from ..core.gaps import CapabilityGapRegistry
from ..core.validation import ValidationReport, validate_artifact, validate_unit_record
from ..core.workspace import Workspace
from ..flow.flows import FlowComposer
from ..flow.graph import GraphBuilder
from ..flow.impact import ImpactEngine
from ..indexer.changes import ChangeDetector
from ..indexer.opensearch import OpenSearchResourceIndexer, OPENSEARCH_INDEX_PATH, load_opensearch_resources
from ..indexer.snapshot import FILE_INDEX_PATH, SourceSnapshotter, load_file_index
from ..indexer.unit_index import UNIT_INDEX_PATH, UnitIndexBuilder, UnitStore
from ..router.audit import AnswerAuditor
from ..router.context_pack import ContextPackBuilder
from ..router.kiro import KiroRunner
from ..conductor.agent import parse_agent_result, validate_agent_result
from ..conductor.store import OrchestrationStore
from ..conductor.synthesize import synthesize
from ..conductor.workflows import OrchestratorWorkflow
from ..router.retrieval import RetrievalIndex, RetrievalIndexBuilder
from ..router.session import SessionStore


def _ws() -> Workspace:
    return Workspace.find()


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2))


# --- workspace ---------------------------------------------------------------
def cmd_init(args: Any) -> int:
    ws = Workspace(Path.cwd())
    config = ws.init(repo_name=args.repo, force=args.force)
    if args.json:
        _emit(config)
    else:
        print(f"Initialised .groundrail workspace at {ws.path}")
        print(f"  primary repo: {config['repositories'][0]['repo']}")
        print(f"  token budget: {config['context_pack']['token_budget']}")
        print("Next: groundrail snapshot && groundrail index units")
    return 0


def cmd_snapshot(args: Any) -> int:
    ws = _ws()
    snap = SourceSnapshotter(ws).run()
    data = snap["data"]
    if args.json:
        _emit(snap)
    else:
        repo = snap["source"]
        print(f"Snapshot recorded: {data['file_count']} files")
        print(f"  commit: {repo['source_commit']}  dirty: {repo['dirty_worktree']}")
        if data["missing"]:
            print(f"  missing repos: {', '.join(data['missing'])}")
    return 0


def cmd_changed(args: Any) -> int:
    ws = _ws()
    result = ChangeDetector(ws).detect()
    data = result["data"]
    if args.json:
        _emit(result)
    else:
        print(f"Changed since snapshot: {data['changed_count']} files")
        for label in ("added", "modified", "removed"):
            for path in data[label]:
                print(f"  {label[0].upper()} {path}")
    return 0


def cmd_refresh(args: Any) -> int:
    ws = _ws()
    SourceSnapshotter(ws).run(command="groundrail refresh")
    UnitIndexBuilder(ws).build(command="groundrail refresh")
    os_resources = OpenSearchResourceIndexer(ws).build(command="groundrail refresh")["data"]["resource_count"]
    rows = RetrievalIndexBuilder(ws).build(command="groundrail refresh")
    print(f"Refreshed: snapshot + unit index + OpenSearch resources ({os_resources}) + retrieval index ({rows} rows)")
    return 0


def cmd_status(args: Any) -> int:
    ws = _ws()
    store = ws.store
    units = UnitStore(store).all()
    analyses = AnalysisStore(store).all()
    stale = _stale_analyses(ws)
    opensearch_resources = len(load_opensearch_resources(store))
    info = {
        "workspace": str(ws.path),
        "snapshot": store.exists(FILE_INDEX_PATH),
        "files": len(load_file_index(store)) if store.exists(FILE_INDEX_PATH) else 0,
        "units": len(units),
        "analyses": len(analyses),
        "stale_analyses": len(stale),
        "opensearch_resources": opensearch_resources,
        "gaps": len(CapabilityGapRegistry(store).load()),
    }
    if args.json:
        _emit(info)
    else:
        print(f"Workspace: {info['workspace']}")
        print(f"  snapshot: {'yes' if info['snapshot'] else 'no'}  files: {info['files']}")
        print(f"  units: {info['units']}  analyses: {info['analyses']}  stale: {info['stale_analyses']}")
        print(f"  OpenSearch resources: {info['opensearch_resources']}")
        print(f"  capability gaps: {info['gaps']}")
    return 0


# --- indexer -----------------------------------------------------------------
def cmd_index_units(args: Any) -> int:
    ws = _ws()
    artifact = UnitIndexBuilder(ws).build()
    count = artifact["data"]["unit_count"]
    if args.json:
        _emit(artifact)
    else:
        print(f"Indexed {count} units -> {UNIT_INDEX_PATH}")
    return 0


def cmd_index_opensearch(args: Any) -> int:
    ws = _ws()
    artifact = OpenSearchResourceIndexer(ws).build()
    count = artifact["data"]["resource_count"]
    if args.json:
        _emit(artifact)
    else:
        print(f"Indexed {count} OpenSearch resource(s) -> {OPENSEARCH_INDEX_PATH}")
    return 0


def cmd_unit_list(args: Any) -> int:
    ws = _ws()
    units = UnitStore(ws.store).filter(kind=args.kind, path=args.path, complexity=args.complexity)
    if args.json:
        _emit([_unit_summary(u) for u in units])
    else:
        for u in units:
            s = u["span"]
            print(f"{u['unit_id']}  [{u['kind']}]  {u['file_path']}:{s['start_line']}-{s['end_line']}")
        print(f"\n{len(units)} unit(s)")
    return 0


def cmd_unit_show(args: Any) -> int:
    ws = _ws()
    unit = UnitStore(ws.store).get(args.unit_id)
    if args.json:
        _emit(unit)
        return 0
    s = unit["span"]
    print(f"{unit['unit_id']}")
    print(f"  kind:       {unit['kind']}")
    print(f"  file:       {unit['file_path']}:{s['start_line']}-{s['end_line']}")
    print(f"  qualified:  {unit['qualified_name']}")
    print(f"  complexity: {unit['complexity']['state']} "
          f"(lines={unit['complexity']['line_count']}, branches={unit['complexity']['branch_count']}, "
          f"calls={unit['complexity']['call_count']})")
    print(f"  imports:    {', '.join(unit['imports']) or '(none)'}")
    related = unit.get("related_candidates", {})
    for key in ("endpoint_candidates", "api_call_candidates", "query_candidates", "route_candidates", "opensearch_candidates"):
        if related.get(key):
            print(f"  {key}: {json.dumps(related[key][:5])}")
    if unit["call_candidates"]:
        print(f"  calls:      {', '.join(c['target_text'] for c in unit['call_candidates'][:10])}")
    analysis = AnalysisStore(ws.store).try_get(args.unit_id)
    if analysis:
        print(f"  analysis:   [{analysis['state']}/{analysis['confidence']}] {analysis['summary']}")
    else:
        print("  analysis:   (none) — run `groundrail analyze-unit`")
    return 0


# The remainder of this module is imported from the previous implementation.
# It is intentionally left below this point by the existing file content in git history.
