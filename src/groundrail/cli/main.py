"""Groundrail CLI entry point and argument parsing."""

from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..core.errors import GroundrailError
from . import commands, layer_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundrail",
        description="Local evidence and context-routing framework for AI-assisted code work.",
    )
    parser.add_argument("--version", action="version", version=f"groundrail {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        return p

    p = add("init", commands.cmd_init, "create a .groundrail workspace"); p.add_argument("--repo"); p.add_argument("--force", action="store_true"); p.add_argument("--json", action="store_true")
    p = add("snapshot", commands.cmd_snapshot, "record source snapshot + file index"); p.add_argument("--json", action="store_true")
    p = add("changed", commands.cmd_changed, "show files changed since snapshot"); p.add_argument("--json", action="store_true")
    add("refresh", commands.cmd_refresh, "snapshot + index units + OpenSearch resources + retrieval")
    p = add("status", commands.cmd_status, "summarise workspace state"); p.add_argument("--json", action="store_true")

    p = add("index", commands.cmd_index_units, "build deterministic indexes")
    isub = p.add_subparsers(dest="index_target", required=True)
    iu = isub.add_parser("units", help="index code units"); iu.set_defaults(func=commands.cmd_index_units); iu.add_argument("--json", action="store_true")
    io = isub.add_parser("opensearch", help="index OpenSearch mappings/templates/resources"); io.set_defaults(func=commands.cmd_index_opensearch); io.add_argument("--json", action="store_true")

    p = add("unit", _unit_dispatch, "inspect indexed units")
    usub = p.add_subparsers(dest="unit_action", required=True)
    ul = usub.add_parser("list"); ul.set_defaults(func=commands.cmd_unit_list); ul.add_argument("--kind"); ul.add_argument("--path"); ul.add_argument("--complexity", choices=["simple", "moderate", "complex"]); ul.add_argument("--json", action="store_true")
    us = usub.add_parser("show"); us.set_defaults(func=commands.cmd_unit_show); us.add_argument("unit_id"); us.add_argument("--json", action="store_true")
    uc = usub.add_parser("code"); uc.set_defaults(func=commands.cmd_unit_code); uc.add_argument("unit_id")

    p = add("analyze-unit", commands.cmd_analyze_unit, "run AI analysis on one unit"); p.add_argument("unit_id")
    p = add("analyze-units", commands.cmd_analyze_units, "analyse many units"); p.add_argument("--stale", action="store_true"); p.add_argument("--missing", action="store_true"); p.add_argument("--changed", action="store_true"); p.add_argument("--kind"); p.add_argument("--limit", type=int)
    p = add("analysis", _analysis_dispatch, "inspect/validate AI analyses"); asub = p.add_subparsers(dest="analysis_action", required=True)
    ash = asub.add_parser("show"); ash.set_defaults(func=commands.cmd_analysis_show); ash.add_argument("unit_id"); ash.add_argument("--json", action="store_true")
    av = asub.add_parser("validate"); av.set_defaults(func=commands.cmd_analysis_validate); av.add_argument("--strict", action="store_true")

    p = add("review", _review_dispatch, "review, confirm, reject AI knowledge"); rsub = p.add_subparsers(dest="review_action", required=True)
    rl = rsub.add_parser("list"); rl.set_defaults(func=layer_commands.cmd_review_list); rl.add_argument("--limit", type=int, default=50); rl.add_argument("--json", action="store_true")
    rs = rsub.add_parser("show"); rs.set_defaults(func=layer_commands.cmd_review_show); rs.add_argument("item_id"); rs.add_argument("--json", action="store_true")
    for action, func in [("confirm", layer_commands.cmd_review_confirm), ("reject", layer_commands.cmd_review_reject)]:
        rp = rsub.add_parser(action); rp.set_defaults(func=func); rp.add_argument("item_id"); rp.add_argument("--reviewer", default="developer"); rp.add_argument("--note", default=""); rp.add_argument("--json", action="store_true")
    rst = rsub.add_parser("stale"); rst.set_defaults(func=layer_commands.cmd_review_stale); rst.add_argument("--json", action="store_true")

    p = add("notes", _notes_dispatch, "inspect/review AI notes"); nsub = p.add_subparsers(dest="notes_action", required=True)
    nl = nsub.add_parser("list"); nl.set_defaults(func=layer_commands.cmd_notes_list); nl.add_argument("--limit", type=int, default=50); nl.add_argument("--json", action="store_true")
    ns = nsub.add_parser("show"); ns.set_defaults(func=layer_commands.cmd_notes_show); ns.add_argument("item_id"); ns.add_argument("--json", action="store_true")
    for action, func in [("confirm", layer_commands.cmd_notes_confirm), ("reject", layer_commands.cmd_notes_reject)]:
        np = nsub.add_parser(action); np.set_defaults(func=func); np.add_argument("item_id"); np.add_argument("--reviewer", default="developer"); np.add_argument("--note", default=""); np.add_argument("--json", action="store_true")

    p = add("promote", _promote_dispatch, "promote confirmed non-stale claims"); psub = p.add_subparsers(dest="promote_action", required=True)
    pc = psub.add_parser("list-candidates"); pc.set_defaults(func=layer_commands.cmd_promote_candidates); pc.add_argument("--json", action="store_true")
    pp = psub.add_parser("claim"); pp.set_defaults(func=layer_commands.cmd_promote_claim); pp.add_argument("item_id"); pp.add_argument("--promoted-by", default="developer"); pp.add_argument("--json", action="store_true")
    p = add("knowledge", _knowledge_dispatch, "inspect promoted knowledge"); ksub = p.add_subparsers(dest="knowledge_action", required=True)
    kl = ksub.add_parser("list"); kl.set_defaults(func=layer_commands.cmd_knowledge_list); kl.add_argument("--json", action="store_true")
    ks = ksub.add_parser("show"); ks.set_defaults(func=layer_commands.cmd_knowledge_show); ks.add_argument("fact_id"); ks.add_argument("--json", action="store_true")

    p = add("search", commands.cmd_search, "search retrieval index"); p.add_argument("query"); p.add_argument("--limit", type=int, default=20); p.add_argument("--json", action="store_true")
    p = add("prepare", commands.cmd_prepare, "build context pack"); p.add_argument("mode", choices=sorted(["ask", "debug", "review", "plan", "implement"])); p.add_argument("request", nargs="+"); p.add_argument("--allow-inferred-low", action="store_true", dest="allow_inferred_low"); p.add_argument("--json", action="store_true")
    p = add("ctx", _ctx_dispatch, "inspect context selection"); csub = p.add_subparsers(dest="ctx_action", required=True); ce = csub.add_parser("explain"); ce.set_defaults(func=layer_commands.cmd_ctx_explain); ce.add_argument("session", nargs="?", default="latest"); ce.add_argument("--json", action="store_true")
    p = add("ask", commands.cmd_ask, "build context pack and run Kiro"); p.add_argument("question", nargs="+"); p.add_argument("--mode", default="ask", choices=sorted(["ask", "debug", "review", "plan", "implement"]))
    p = add("audit", _audit_dispatch, "audit a Kiro answer"); ausub = p.add_subparsers(dest="audit_action", required=True); aa = ausub.add_parser("answer"); aa.set_defaults(func=commands.cmd_audit_answer); aa.add_argument("session", nargs="?", default="latest"); aa.add_argument("--strict", action="store_true"); aa.add_argument("--json", action="store_true")
    add("smart", commands.cmd_smart, "print latest session")
    p = add("tui", commands.cmd_tui, "interactive cockpit"); p.add_argument("--print", choices=["dashboard", "units", "review", "knowledge", "sessions", "gaps", "map", "eval", "unit", "session"]); p.add_argument("--unit"); p.add_argument("--session")

    p = add("graph", _flow_dispatch, "build call/cross-layer graph"); gsub = p.add_subparsers(dest="graph_action", required=True); gb = gsub.add_parser("build"); gb.set_defaults(func=commands.cmd_graph_build); gb.add_argument("--json", action="store_true")
    p = add("flow", _flow_dispatch, "show flow"); fsub = p.add_subparsers(dest="flow_action", required=True)
    fu = fsub.add_parser("unit"); fu.set_defaults(func=commands.cmd_flow_unit); fu.add_argument("unit_id"); fu.add_argument("--json", action="store_true")
    fe = fsub.add_parser("endpoint"); fe.set_defaults(func=commands.cmd_flow_endpoint); fe.add_argument("spec", nargs="+"); fe.add_argument("--json", action="store_true")
    p = add("impact", _flow_dispatch, "show impact"); imsub = p.add_subparsers(dest="impact_action", required=True)
    imf = imsub.add_parser("file"); imf.set_defaults(func=commands.cmd_impact_file); imf.add_argument("path"); imf.add_argument("--json", action="store_true")
    imu = imsub.add_parser("unit"); imu.set_defaults(func=commands.cmd_impact_unit); imu.add_argument("unit_id"); imu.add_argument("--json", action="store_true")
    p = add("tests-for", commands.cmd_tests_for, "find likely tests"); p.add_argument("target"); p.add_argument("--json", action="store_true")

    p = add("orchestrate", _orchestrate_dispatch, "run conductor workflow"); osub = p.add_subparsers(dest="workflow", required=True)
    for wf in ("debug", "review", "plan"):
        op = osub.add_parser(wf); op.set_defaults(func=commands.cmd_orchestrate); op.add_argument("request", nargs="+"); op.add_argument("--no-agent", action="store_true", dest="no_agent"); op.add_argument("--json", action="store_true")
    p = add("orchestrations", _orchestrations_dispatch, "list/show orchestrations"); orsub = p.add_subparsers(dest="orchestrations_action", required=True)
    orl = orsub.add_parser("list"); orl.set_defaults(func=commands.cmd_orchestrations_list); orl.add_argument("--json", action="store_true")
    orsh = orsub.add_parser("show"); orsh.set_defaults(func=commands.cmd_orchestrations_show); orsh.add_argument("orch_id", nargs="?", default=None); orsh.add_argument("--json", action="store_true")
    p = add("synthesize", commands.cmd_synthesize, "synthesize findings"); p.add_argument("orch_id", nargs="?", default=None); p.add_argument("--json", action="store_true")
    p = add("conflicts", commands.cmd_conflicts, "show conflicts"); p.add_argument("orch_id", nargs="?", default=None); p.add_argument("--json", action="store_true")
    p = add("agents", _agents_dispatch, "list or validate agent findings"); agsub = p.add_subparsers(dest="agents_action", required=True)
    agl = agsub.add_parser("list"); agl.set_defaults(func=commands.cmd_agents_list); agl.add_argument("--quarantine", action="store_true"); agl.add_argument("--json", action="store_true")
    agv = agsub.add_parser("validate"); agv.set_defaults(func=commands.cmd_agent_validate); agv.add_argument("result_file")

    p = add("validate", commands.cmd_validate, "validate artifacts"); p.add_argument("--strict", action="store_true")
    p = add("verify", commands.cmd_verify, "verify freshness"); p.add_argument("--strict", action="store_true"); p.add_argument("--json", action="store_true")
    p = add("gaps", commands.cmd_gaps, "list gaps"); p.add_argument("--json", action="store_true")
    p = add("doctor", commands.cmd_doctor, "diagnose workspace"); p.add_argument("--json", action="store_true")
    p = add("map", layer_commands.cmd_map, "show layer map"); p.add_argument("--json", action="store_true")
    p = add("eval", _eval_dispatch, "run eval checks"); esub = p.add_subparsers(dest="eval_action", required=True); er = esub.add_parser("run"); er.set_defaults(func=layer_commands.cmd_eval_run); er.add_argument("--strict", action="store_true"); er.add_argument("--json", action="store_true")
    return parser


def _normalise_args(args: argparse.Namespace) -> None:
    if getattr(args, "command", None) == "analyze-units" and getattr(args, "changed", False): args.stale = True; args.missing = True


def _unit_dispatch(args): return args.func(args)
def _analysis_dispatch(args): return args.func(args)
def _review_dispatch(args): return args.func(args)
def _notes_dispatch(args): return args.func(args)
def _promote_dispatch(args): return args.func(args)
def _knowledge_dispatch(args): return args.func(args)
def _ctx_dispatch(args): return args.func(args)
def _audit_dispatch(args): return args.func(args)
def _flow_dispatch(args): return args.func(args)
def _orchestrate_dispatch(args): return args.func(args)
def _orchestrations_dispatch(args): return args.func(args)
def _agents_dispatch(args): return args.func(args)
def _eval_dispatch(args): return args.func(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(argv); _normalise_args(args)
    try: return args.func(args)
    except GroundrailError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if getattr(exc, "errors", None):
            for err in exc.errors: print(f"  - {err}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError: return 0


if __name__ == "__main__":
    raise SystemExit(main())
