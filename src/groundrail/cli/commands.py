"""Implementations for each CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..analyzer.pipeline import AnalysisPipeline
from ..analyzer.store import AnalysisStore
from ..conductor.agent import parse_agent_result, validate_agent_result
from ..conductor.store import OrchestrationStore
from ..conductor.synthesize import synthesize
from ..conductor.workflows import OrchestratorWorkflow
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
from ..router.retrieval import RetrievalIndex, RetrievalIndexBuilder
from ..router.session import SessionStore


def _ws() -> Workspace:
    return Workspace.find()


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2))


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
    if args.json:
        _emit(snap)
    else:
        print(f"Snapshot recorded: {snap['data']['file_count']} files")
        print(f"  commit: {snap['source']['source_commit']}  dirty: {snap['source']['dirty_worktree']}")
        if snap["data"]["missing"]:
            print(f"  missing repos: {', '.join(snap['data']['missing'])}")
    return 0


def cmd_changed(args: Any) -> int:
    result = ChangeDetector(_ws()).detect()
    if args.json:
        _emit(result)
    else:
        data = result["data"]
        print(f"Changed since snapshot: {data['changed_count']} files")
        for label in ("added", "modified", "removed"):
            for path in data[label]:
                print(f"  {label[0].upper()} {path}")
    return 0


def cmd_refresh(args: Any) -> int:
    ws = _ws()
    SourceSnapshotter(ws).run(command="groundrail refresh")
    UnitIndexBuilder(ws).build(command="groundrail refresh")
    os_count = OpenSearchResourceIndexer(ws).build(command="groundrail refresh")["data"]["resource_count"]
    rows = RetrievalIndexBuilder(ws).build(command="groundrail refresh")
    print(f"Refreshed: snapshot + unit index + OpenSearch resources ({os_count}) + retrieval index ({rows} rows)")
    return 0


def cmd_status(args: Any) -> int:
    ws = _ws(); store = ws.store
    units = UnitStore(store).all(); analyses = AnalysisStore(store).all(); stale = _stale_analyses(ws)
    info = {"workspace": str(ws.path), "snapshot": store.exists(FILE_INDEX_PATH), "files": len(load_file_index(store)) if store.exists(FILE_INDEX_PATH) else 0, "units": len(units), "analyses": len(analyses), "stale_analyses": len(stale), "opensearch_resources": len(load_opensearch_resources(store)), "gaps": len(CapabilityGapRegistry(store).load())}
    if args.json:
        _emit(info)
    else:
        print(f"Workspace: {info['workspace']}")
        print(f"  snapshot: {'yes' if info['snapshot'] else 'no'}  files: {info['files']}")
        print(f"  units: {info['units']}  analyses: {info['analyses']}  stale: {info['stale_analyses']}")
        print(f"  OpenSearch resources: {info['opensearch_resources']}")
        print(f"  capability gaps: {info['gaps']}")
    return 0


def cmd_index_units(args: Any) -> int:
    artifact = UnitIndexBuilder(_ws()).build()
    if args.json: _emit(artifact)
    else: print(f"Indexed {artifact['data']['unit_count']} units -> {UNIT_INDEX_PATH}")
    return 0


def cmd_index_opensearch(args: Any) -> int:
    artifact = OpenSearchResourceIndexer(_ws()).build()
    if args.json: _emit(artifact)
    else: print(f"Indexed {artifact['data']['resource_count']} OpenSearch resource(s) -> {OPENSEARCH_INDEX_PATH}")
    return 0


def cmd_unit_list(args: Any) -> int:
    units = UnitStore(_ws().store).filter(kind=args.kind, path=args.path, complexity=args.complexity)
    if args.json: _emit([_unit_summary(u) for u in units])
    else:
        for u in units:
            s = u["span"]; print(f"{u['unit_id']}  [{u['kind']}]  {u['file_path']}:{s['start_line']}-{s['end_line']}")
        print(f"\n{len(units)} unit(s)")
    return 0


def cmd_unit_show(args: Any) -> int:
    ws = _ws(); unit = UnitStore(ws.store).get(args.unit_id)
    if args.json: _emit(unit); return 0
    s = unit["span"]
    print(f"{unit['unit_id']}")
    print(f"  kind:       {unit['kind']}")
    print(f"  file:       {unit['file_path']}:{s['start_line']}-{s['end_line']}")
    print(f"  qualified:  {unit['qualified_name']}")
    print(f"  complexity: {unit['complexity']['state']} (lines={unit['complexity']['line_count']}, branches={unit['complexity']['branch_count']}, calls={unit['complexity']['call_count']})")
    print(f"  imports:    {', '.join(unit['imports']) or '(none)'}")
    related = unit.get("related_candidates", {})
    for key in ("endpoint_candidates", "api_call_candidates", "query_candidates", "route_candidates", "opensearch_candidates"):
        if related.get(key): print(f"  {key}: {json.dumps(related[key][:5])}")
    if unit["call_candidates"]: print(f"  calls:      {', '.join(c['target_text'] for c in unit['call_candidates'][:10])}")
    analysis = AnalysisStore(ws.store).try_get(args.unit_id)
    print(f"  analysis:   [{analysis['state']}/{analysis['confidence']}] {analysis['summary']}" if analysis else "  analysis:   (none) — run `groundrail analyze-unit`")
    return 0


def cmd_unit_code(args: Any) -> int:
    ws = _ws(); unit = UnitStore(ws.store).get(args.unit_id); span = unit["span"]
    for offset, line in enumerate(_unit_source(ws, unit).splitlines()): print(f"{span['start_line'] + offset:6d}  {line}")
    return 0


def cmd_analyze_unit(args: Any) -> int:
    pipeline = AnalysisPipeline(_ws())
    if not pipeline.runner.configured: raise GroundrailError("no AI command configured; set GROUNDRAIL_AI_CMD (or GROUNDRAIL_KIRO_CMD)")
    analysis = pipeline.analyze_unit(args.unit_id); print(f"Analysed {args.unit_id}: [{analysis['state']}/{analysis['confidence']}] {analysis['summary']}"); return 0


def cmd_analyze_units(args: Any) -> int:
    pipeline = AnalysisPipeline(_ws())
    if not pipeline.runner.configured: raise GroundrailError("no AI command configured; set GROUNDRAIL_AI_CMD (or GROUNDRAIL_KIRO_CMD)")
    report = pipeline.analyze_units(only_stale=args.stale, only_missing=args.missing, kind=args.kind, limit=args.limit)
    print(f"Analysed {len(report['analysed'])}, skipped(secrets) {len(report['skipped_secrets'])}, failed {len(report['failed'])} of {report['selected_count']} selected")
    return 0


def cmd_analysis_show(args: Any) -> int:
    analysis = AnalysisStore(_ws().store).get(args.unit_id)
    if args.json: _emit(analysis); return 0
    print(f"{analysis['analysis_id']}  [{analysis['state']}/{analysis['confidence']}] ai={analysis['ai_confidence']} review={analysis['review_status']}")
    print(f"  {analysis['summary']}")
    for c in analysis.get("intent", []): print(f"  intent: {c['text']}")
    for u in analysis.get("uncertainties", []): print(f"  uncertainty: {u['text']}")
    for n in analysis.get("ai_notes", []): print(f"  note [{n['severity']}] {n['type']}: {n['text']}")
    return 0


def cmd_analysis_validate(args: Any) -> int:
    ws = _ws(); units = {u["unit_id"]: u for u in UnitStore(ws.store).all()}; store = AnalysisStore(ws.store); report = ValidationReport()
    for analysis in store.all():
        if analysis["state"] == vocab.STATUS_VERIFIED: report.error(f"{analysis['analysis_id']}: AI analysis illegally claims verified")
        unit = units.get(analysis["unit_id"])
        if unit and store.is_stale(analysis, unit): report.warn(f"{analysis['analysis_id']}: stale (unit changed since analysis)")
    return _finish_validation(report, args.strict, "analysis validate")


def cmd_search(args: Any) -> int:
    ws = _ws(); RetrievalIndexBuilder(ws).build(); rows = RetrievalIndex(ws.store).search(args.query, limit=args.limit)
    if args.json: _emit(rows)
    else:
        for r in rows: print(f"[{r['state']}/{r['confidence']}] {r['item_type']:13s} {r['title']:24s} {r['path']}  ({r['item_id']})")
        print(f"\n{len(rows)} result(s)")
    return 0


def cmd_prepare(args: Any) -> int:
    ws = _ws(); pack = ContextPackBuilder(ws).build(mode=args.mode, request=" ".join(args.request), allow_inferred_low=args.allow_inferred_low); md_path = ws.store.resolve(f"sessions/{pack['session_id']}/context-pack.md")
    if args.json: _emit(pack)
    else:
        print(f"Context pack: {pack['session_id']} ({pack['mode']})")
        print(f"  selected: {len(pack['source_evidence'])} units, {len(pack['selected_unit_analyses'])} analyses; tokens {pack['tokens_used']}/{pack['token_budget']}")
        print(f"  freshness: {pack['freshness']['status']}")
        print(f"  markdown:  {md_path}")
    return 0


def cmd_ask(args: Any) -> int:
    ws = _ws(); pack = ContextPackBuilder(ws).build(mode=args.mode, request=" ".join(args.question)); sessions = SessionStore(ws.store); sid = pack["session_id"]; md_path = ws.store.resolve(f"sessions/{sid}/context-pack.md"); md = md_path.read_text(encoding="utf-8")
    runner = KiroRunner()
    if not runner.configured:
        print(f"Context pack ready: {sid}"); print("  Kiro not configured (set GROUNDRAIL_KIRO_CMD)."); print(f"  Prompt file: {md_path}"); return 0
    if pack["freshness"]["status"] != "ok": print(f"Warning: context includes stale-excluded items: {pack['freshness']['stale_items']}")
    raw = runner.run(pack_markdown=md, pack_path=str(md_path)); sessions.write_text(sid, "kiro-output.raw.md", raw); audit = AnswerAuditor(ws).audit(raw); sessions.write(sid, "audit.json", audit)
    print(raw); print(f"\n--- audit: {audit['status']} ({audit['claims_checked']} claims) ---")
    for f in audit["findings"]: print(f"  [{f['severity']}] {f['message']}")
    return 0 if audit["status"] == "ok" else 3


def cmd_audit_answer(args: Any) -> int:
    ws = _ws(); sessions = SessionStore(ws.store); sid = args.session if args.session and args.session != "latest" else sessions.latest_id()
    if not sessions.has(sid, "kiro-output.raw.md"): raise NotFoundError(f"session {sid} has no kiro-output.raw.md")
    raw = ws.store.resolve(f"sessions/{sid}/kiro-output.raw.md").read_text(encoding="utf-8"); audit = AnswerAuditor(ws).audit(raw); sessions.write(sid, "audit.json", audit)
    if args.json: _emit(audit)
    else:
        print(f"audit {sid}: {audit['status']} ({audit['claims_checked']} claims)")
        for f in audit["findings"]: print(f"  [{f['severity']}] {f['code']}: {f['message']}")
    return 3 if args.strict and audit["status"] != "ok" else 0


def cmd_tui(args: Any) -> int:
    import shutil, sys
    from ..tui import screens
    from ..tui.viewmodels import ViewModelBuilder
    ws = _ws(); builder = ViewModelBuilder(ws)
    if args.print:
        ui = screens.default_ui(); ui["screen"] = args.print
        if args.print == "unit":
            if not args.unit: raise GroundrailError("tui --print unit requires --unit <unit-id>")
            ui["selected_unit"] = args.unit
        if args.print == "session": ui["selected_session"] = args.session or SessionStore(ws.store).latest_id()
        print("\n".join(screens.compose(builder, ui, shutil.get_terminal_size((100, 40)).columns, None))); return 0
    if not sys.stdout.isatty(): raise GroundrailError("tui requires an interactive terminal; use `groundrail tui --print <screen>`")
    from ..tui.app import run
    run(ws); return 0


def cmd_smart(args: Any) -> int:
    ws = _ws(); sessions = SessionStore(ws.store); sid = sessions.latest_id(); print(f"=== session {sid} ===")
    for name, title in (("context-pack.md", ""), ("kiro-output.raw.md", "=== Kiro answer ===")):
        if sessions.has(sid, name):
            if title: print(title)
            print(ws.store.resolve(f"sessions/{sid}/{name}").read_text(encoding="utf-8"))
    if sessions.has(sid, "audit.json"):
        audit = sessions.read(sid, "audit.json"); print(f"=== audit: {audit['status']} ({audit['claims_checked']} claims) ===")
        for f in audit["findings"]: print(f"  [{f['severity']}] {f['message']}")
    return 0


def cmd_graph_build(args: Any) -> int:
    graph = GraphBuilder(_ws()).build(); edge_count = sum(len(e) for e in graph.out_adj.values())
    _emit({"nodes": len(graph.nodes), "edges": edge_count}) if args.json else print(f"Graph: {len(graph.nodes)} nodes, {edge_count} edges -> graph/")
    return 0


def cmd_flow_unit(args: Any) -> int:
    flow = FlowComposer(_ws()).unit_flow(args.unit_id)
    if args.json: _emit(flow); return 0
    print(f"flow for {args.unit_id}  [{flow['state']}/{flow['confidence']}]"); print("  callees:")
    for c in flow["direct_callees"]: print(f"    -> {c['symbol']} [{c['confidence']}] ({c['unit_id']})")
    print("  callers:")
    for c in flow["direct_callers"]: print(f"    <- {c['symbol']} [{c['confidence']}] ({c['unit_id']})")
    return 0


def cmd_flow_endpoint(args: Any) -> int:
    parts = " ".join(args.spec).split(None, 1)
    if len(parts) != 2: raise GroundrailError('endpoint must look like "GET /users/search"')
    flow = FlowComposer(_ws()).endpoint_flow(parts[0], parts[1])
    if args.json: _emit(flow); return 0
    ep = flow["endpoint"]; print(f"{ep['method']} {ep['path']}  [{flow['state']}/{flow['confidence']}]  root={flow['root_unit']}")
    for n in flow["nodes"]: print(f"  {'  ' * n['distance']}-> {n['symbol']} [{n['state']}/{n['confidence']}] ({n['unit_id']})")
    return 0


def cmd_impact_file(args: Any) -> int: return _print_impact(ImpactEngine(_ws()).impact_file(args.path), args.json)
def cmd_impact_unit(args: Any) -> int: return _print_impact(ImpactEngine(_ws()).impact_unit(args.unit_id), args.json)


def cmd_tests_for(args: Any) -> int:
    result = ImpactEngine(_ws()).tests_for(args.target)
    if args.json: _emit(result); return 0
    if result["coverage_gap"]: print(f"tests-for {args.target}: NO reaching tests (coverage gap)")
    else:
        print(f"tests-for {args.target}: {len(result['tests'])} test(s)")
        for t in result["tests"]: print(f"  {t['symbol']} [d{t['distance']}/{t['confidence']}] ({t['unit_id']})")
    return 0


def _print_impact(report: dict[str, Any], as_json: bool) -> int:
    if as_json: _emit(report); return 0
    print(f"impact of {report['target']} ({report['target_kind']})")
    print(f"  changed units: {len(report['changed_units'])}")
    summary = report["summary"]; print(f"  impacted upstream: {summary.get('total', 0)} ({', '.join(f'{k}={v}' for k, v in summary.items() if k != 'total')})")
    for entry in report["impacted_upstream"][:25]: print(f"    {entry['symbol']} [{entry['category']}/{entry['link_confidence']}] d{entry['distance']} ({entry['file_path']})")
    if report.get("impacted_resources"): print(f"  impacted resources: {', '.join(r['name'] for r in report['impacted_resources'][:10])}")
    if report["likely_tests"]: print(f"  likely tests: {', '.join(t['symbol'] for t in report['likely_tests'])}")
    if report["capability_gaps"]: print(f"  gaps in target: {len(report['capability_gaps'])}")
    return 0


def cmd_validate(args: Any) -> int:
    ws = _ws(); report = ValidationReport()
    for rel in (FILE_INDEX_PATH, UNIT_INDEX_PATH, OPENSEARCH_INDEX_PATH, "source/snapshot.json"):
        if ws.store.exists(rel): report.errors.extend(validate_artifact(ws.store.read_json(rel), label=rel).errors)
    if ws.store.exists(UNIT_INDEX_PATH):
        for unit in UnitStore(ws.store).all(): validate_unit_record(unit, report)
    return _finish_validation(report, args.strict, "validate")


def cmd_verify(args: Any) -> int:
    ws = _ws(); report = ValidationReport(); from ..core import hashing
    for unit_id in _stale_analyses(ws): report.warn(f"analysis for {unit_id} is stale (unit changed)")
    for record in load_file_index(ws.store):
        path = ws.repo_root(record["repo"]) / record["path"]
        if not path.exists(): report.error(f"indexed file missing: {record['path']}"); continue
        if hashing.sha256_bytes(path.read_bytes()) != record["sha256"]: report.warn(f"file changed since snapshot: {record['path']}")
    _write_report(ws, "audit/stale-report.json", "stale_report", report)
    if args.json: _emit(report.as_dict())
    else:
        print(f"verify: {report.as_dict()['status']} ({len(report.errors)} errors, {len(report.warnings)} warnings)")
        for w in report.warnings: print(f"  warn: {w}")
        for e in report.errors: print(f"  error: {e}")
    return 3 if args.strict and not report.ok else 0


def cmd_gaps(args: Any) -> int:
    gaps = CapabilityGapRegistry(_ws().store).load()
    if args.json: _emit(gaps)
    else:
        for g in gaps: print(f"[{g.get('severity')}] {g.get('kind')}: {g.get('detail')} ({g.get('location')})")
        print(f"\n{len(gaps)} gap(s)")
    return 0


def cmd_doctor(args: Any) -> int:
    import os
    try: ws = _ws(); workspace_ok = True; units = len(UnitStore(ws.store).all()); os_resources = len(load_opensearch_resources(ws.store))
    except GroundrailError: workspace_ok = False; units = 0; os_resources = 0
    checks = {"workspace": workspace_ok, "units_indexed": units, "opensearch_resources": os_resources, "ai_command": bool(os.environ.get("GROUNDRAIL_AI_CMD") or os.environ.get("GROUNDRAIL_KIRO_CMD")), "kiro_command": bool(os.environ.get("GROUNDRAIL_KIRO_CMD"))}
    if args.json: _emit(checks)
    else:
        print(f"workspace:     {'ok' if checks['workspace'] else 'MISSING (run init)'}")
        print(f"units indexed: {checks['units_indexed']}")
        print(f"OpenSearch:    {checks['opensearch_resources']} resource(s)")
        print(f"AI command:    {'set' if checks['ai_command'] else 'unset (analysis disabled)'}")
        print(f"Kiro command:  {'set' if checks['kiro_command'] else 'unset (ask = degraded mode)'}")
    return 0


def _unit_summary(unit: dict[str, Any]) -> dict[str, Any]:
    return {"unit_id": unit["unit_id"], "kind": unit["kind"], "file_path": unit["file_path"], "span": unit["span"], "complexity": unit["complexity"]["state"]}


def _unit_source(ws: Workspace, unit: dict[str, Any]) -> str:
    text = (ws.repo_root(unit["repo"]) / unit["file_path"]).read_text(encoding="utf-8"); span = unit["span"]
    return "\n".join(text.splitlines()[span["start_line"] - 1 : span["end_line"]])


def _stale_analyses(ws: Workspace) -> list[str]:
    units = {u["unit_id"]: u for u in UnitStore(ws.store).all()}; store = AnalysisStore(ws.store); stale = []
    for analysis in store.all():
        unit = units.get(analysis["unit_id"])
        if unit and store.is_stale(analysis, unit): stale.append(analysis["unit_id"])
    return stale


def _finish_validation(report: ValidationReport, strict: bool, command: str) -> int:
    result = report.as_dict(); print(f"{command}: {result['status']} ({len(report.errors)} errors, {len(report.warnings)} warnings)")
    for e in report.errors: print(f"  error: {e}")
    for w in report.warnings: print(f"  warn:  {w}")
    return 3 if strict and not report.ok else 0


def _write_report(ws: Workspace, path: str, kind: str, report: ValidationReport) -> None:
    ws.store.write_json(path, envelope.build_envelope(artifact_id=f"groundrail.audit.{kind}", artifact_kind=kind, generator=envelope.make_generator("groundrail verify", "groundrail.audit"), source=envelope.make_source(), data=report.as_dict()))


def cmd_orchestrate(args: Any) -> int:
    ws = _ws(); outcome = OrchestratorWorkflow(ws).run(args.workflow, " ".join(args.request), no_agent=getattr(args, "no_agent", False))
    if args.json: _emit(outcome)
    else:
        finding = outcome.get("finding") or {}; print(f"orchestration: {outcome['orchestration_id']}"); print(f"  workflow:  {args.workflow}"); print(f"  mode:      {outcome['mode']}"); print(f"  verdict:   {finding.get('verdict', 'unknown')}"); print(f"  findings:  {len(finding.get('findings', []))}"); print(f"\nSummary: {finding.get('summary', '')}")
    return 0


def cmd_orchestrations_list(args: Any) -> int:
    plans = OrchestrationStore(_ws()).list_all()
    if args.json: _emit(plans)
    else:
        if not plans: print("no orchestrations yet; run `groundrail orchestrate debug|review|plan <request>`")
        for p in plans: print(f"  {p['orchestration_id']}  {p['workflow']:8s}  {p['status']:10s}  {p['created_at']}  {p['request'][:60]}")
        print(f"\n{len(plans)} orchestration(s)")
    return 0


def cmd_orchestrations_show(args: Any) -> int:
    ws = _ws()
    orch_store = OrchestrationStore(ws)
    orch_id = getattr(args, "orch_id", None) or orch_store.latest_id()
    if not orch_id:
        raise GroundrailError("no orchestrations; run an orchestrate command first")
    record = orch_store.get_orchestration(orch_id)
    events = orch_store.get_events(orch_id)
    findings = orch_store.list_findings(orch_id)
    quarantine = orch_store.list_quarantine(orch_id)
    if args.json:
        _emit({"orchestration": record, "events": events, "findings": findings, "quarantine": quarantine})
    else:
        print(f"orchestration: {record['orchestration_id']}")
        print(f"  workflow: {record['workflow']}")
        print(f"  request:  {record['request']}")
        print(f"  status:   {record['status']}")
        print(f"  created:  {record['created_at']}")
        print(f"\nevents ({len(events)}):")
        for ev in events:
            print(f"  [{ev['ts']}] {ev['event']}")
        print(f"\nfindings ({len(findings)}):")
        for f in findings:
            n = len(f.get("findings", []))
            print(f"  task {f.get('task_id', '?')}: {f.get('verdict', '?')} — {n} item(s)")
        if quarantine:
            print(f"\nquarantine ({len(quarantine)}):")
            for q in quarantine:
                print(f"  task {q['task_id']}: {q['reason']}")
    return 0


def cmd_synthesize(args: Any) -> int:
    ws = _ws()
    orch_store = OrchestrationStore(ws)
    orch_id = getattr(args, "orch_id", None) or orch_store.latest_id()
    if not orch_id:
        raise GroundrailError("no orchestrations to synthesize")
    record = orch_store.get_orchestration(orch_id)
    findings = orch_store.list_findings(orch_id)
    result = synthesize(
        findings,
        orchestration_id=orch_id,
        workflow=record["workflow"],
        request=record["request"],
    )
    orch_store.write_synthesis(orch_id, result)
    if args.json:
        _emit(result)
    else:
        print(f"synthesis: {orch_id}")
        print(f"  workflow:   {result['workflow']}")
        print(f"  confidence: {result['overall_confidence']}")
        print(f"  findings:   {result['finding_count']}")
        print(f"  conflicts:  {result['conflict_count']}")
    return 0


def cmd_conflicts(args: Any) -> int:
    store = OrchestrationStore(_ws()); oid = getattr(args, "orch_id", None) or store.latest_id()
    if not oid: raise GroundrailError("no orchestrations found")
    try: synthesis = store.get_synthesis(oid)
    except GroundrailError as exc: raise GroundrailError(f"no synthesis for {oid}; run `groundrail synthesize` first") from exc
    conflicts = synthesis.get("conflicts", [])
    if args.json: _emit(conflicts)
    else:
        print(f"{len(conflicts)} conflict(s) in {oid}:") if conflicts else print(f"no conflicts in orchestration {oid}")
        for c in conflicts: print(f"  {c['description']}\n    finding ids: {c['finding_ids']}")
    return 0


def cmd_agents_list(args: Any) -> int:
    ws = _ws()
    orch_store = OrchestrationStore(ws)
    show_quarantine = getattr(args, "quarantine", False)
    if show_quarantine:
        items = orch_store.list_agent_quarantine()
        label = "quarantined"
    else:
        items = orch_store.list_agent_findings()
        label = "finding"
    if args.json:
        _emit(items)
    else:
        if not items:
            print(f"no agent {label}s")
        for item in items:
            if show_quarantine:
                print(
                    f"  {item.get('orchestration_id', '?')}  task={item.get('task_id', '?')}  "
                    f"reason={item.get('reason', '?')}"
                )
            else:
                print(
                    f"  {item.get('orchestration_id', '?')}  task={item.get('task_id', '?')}  "
                    f"verdict={item.get('verdict', '?')}  confidence={item.get('confidence', '?')}  "
                    f"findings={item.get('finding_count', 0)}"
                )
        print(f"\n{len(items)} {label}(s)")
    return 0


def cmd_agent_validate(args: Any) -> int:
    path = Path(args.result_file)
    if not path.exists(): raise GroundrailError(f"file not found: {path}")
    result, errors = parse_agent_result(path.read_text(encoding="utf-8"))
    if errors:
        print(f"INVALID: {len(errors)} error(s)"); [print(f"  - {e}") for e in errors]; return 1
    errors2 = validate_agent_result(result)
    if errors2:
        print(f"INVALID: {len(errors2)} error(s)"); [print(f"  - {e}") for e in errors2]; return 1
    print(f"VALID: task_id={result.get('task_id')} verdict={result.get('verdict')}"); return 0
