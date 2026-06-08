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

    # workspace
    p = add("init", commands.cmd_init, "create a .groundrail workspace")
    p.add_argument("--repo", help="name for the primary repository")
    p.add_argument("--force", action="store_true", help="overwrite existing config")
    p.add_argument("--json", action="store_true")

    p = add("snapshot", commands.cmd_snapshot, "record source snapshot + file index")
    p.add_argument("--json", action="store_true")

    p = add("changed", commands.cmd_changed, "show files changed since snapshot")
    p.add_argument("--json", action="store_true")

    add("refresh", commands.cmd_refresh, "snapshot + index units + retrieval in one step")

    p = add("status", commands.cmd_status, "summarise workspace state")
    p.add_argument("--json", action="store_true")

    # indexer
    p = add("index", commands.cmd_index_units, "build the deterministic unit index")
    isub = p.add_subparsers(dest="index_target", required=True)
    iu = isub.add_parser("units", help="index code units")
    iu.set_defaults(func=commands.cmd_index_units)
    iu.add_argument("--json", action="store_true")

    p = add("unit", _unit_dispatch, "inspect indexed units")
    usub = p.add_subparsers(dest="unit_action", required=True)
    ul = usub.add_parser("list", help="list units")
    ul.set_defaults(func=commands.cmd_unit_list)
    ul.add_argument("--kind")
    ul.add_argument("--path")
    ul.add_argument("--complexity", choices=["simple", "moderate", "complex"])
    ul.add_argument("--json", action="store_true")
    us = usub.add_parser("show", help="show a unit")
    us.set_defaults(func=commands.cmd_unit_show)
    us.add_argument("unit_id")
    us.add_argument("--json", action="store_true")
    uc = usub.add_parser("code", help="print a unit's source span")
    uc.set_defaults(func=commands.cmd_unit_code)
    uc.add_argument("unit_id")

    # analyzer
    p = add("analyze-unit", commands.cmd_analyze_unit, "run AI analysis on one unit")
    p.add_argument("unit_id")

    p = add("analyze-units", commands.cmd_analyze_units, "analyse many units")
    p.add_argument("--stale", action="store_true", help="only re-analyse stale units")
    p.add_argument("--missing", action="store_true", help="only analyse units without analysis")
    p.add_argument("--changed", action="store_true", help="alias for --stale --missing")
    p.add_argument("--kind")
    p.add_argument("--limit", type=int)

    p = add("analysis", _analysis_dispatch, "inspect/validate AI analyses")
    asub = p.add_subparsers(dest="analysis_action", required=True)
    ash = asub.add_parser("show", help="show analysis for a unit")
    ash.set_defaults(func=commands.cmd_analysis_show)
    ash.add_argument("unit_id")
    ash.add_argument("--json", action="store_true")
    av = asub.add_parser("validate", help="validate all analyses")
    av.set_defaults(func=commands.cmd_analysis_validate)
    av.add_argument("--strict", action="store_true")

    # human review / confirmation
    p = add("review", _review_dispatch, "review, confirm, reject, and stale-check AI knowledge")
    rsub = p.add_subparsers(dest="review_action", required=True)
    rl = rsub.add_parser("list", help="list reviewable analyses, claims, notes, and uncertainties")
    rl.set_defaults(func=layer_commands.cmd_review_list)
    rl.add_argument("--limit", type=int, default=50)
    rl.add_argument("--json", action="store_true")
    rs = rsub.add_parser("show", help="show one review item")
    rs.set_defaults(func=layer_commands.cmd_review_show)
    rs.add_argument("item_id")
    rs.add_argument("--json", action="store_true")
    for action, func in [("confirm", layer_commands.cmd_review_confirm), ("reject", layer_commands.cmd_review_reject)]:
        rp = rsub.add_parser(action, help=f"{action} a review item")
        rp.set_defaults(func=func)
        rp.add_argument("item_id")
        rp.add_argument("--reviewer", default="developer")
        rp.add_argument("--note", default="")
        rp.add_argument("--json", action="store_true")
    rst = rsub.add_parser("stale", help="list stale developer confirmations")
    rst.set_defaults(func=layer_commands.cmd_review_stale)
    rst.add_argument("--json", action="store_true")

    p = add("notes", _notes_dispatch, "inspect and review AI notes/uncertainties")
    nsub = p.add_subparsers(dest="notes_action", required=True)
    nl = nsub.add_parser("list", help="list AI notes and uncertainties")
    nl.set_defaults(func=layer_commands.cmd_notes_list)
    nl.add_argument("--limit", type=int, default=50)
    nl.add_argument("--json", action="store_true")
    ns = nsub.add_parser("show", help="show one note")
    ns.set_defaults(func=layer_commands.cmd_notes_show)
    ns.add_argument("item_id")
    ns.add_argument("--json", action="store_true")
    for action, func in [("confirm", layer_commands.cmd_notes_confirm), ("reject", layer_commands.cmd_notes_reject)]:
        np = nsub.add_parser(action, help=f"{action} a note")
        np.set_defaults(func=func)
        np.add_argument("item_id")
        np.add_argument("--reviewer", default="developer")
        np.add_argument("--note", default="")
        np.add_argument("--json", action="store_true")

    # promotion / knowledge
    p = add("promote", _promote_dispatch, "promote confirmed non-stale claims into knowledge")
    psub = p.add_subparsers(dest="promote_action", required=True)
    pc = psub.add_parser("list-candidates", help="list conservative promotion candidates")
    pc.set_defaults(func=layer_commands.cmd_promote_candidates)
    pc.add_argument("--json", action="store_true")
    pp = psub.add_parser("claim", help="promote one confirmed claim")
    pp.set_defaults(func=layer_commands.cmd_promote_claim)
    pp.add_argument("item_id")
    pp.add_argument("--promoted-by", default="developer")
    pp.add_argument("--json", action="store_true")

    p = add("knowledge", _knowledge_dispatch, "inspect promoted knowledge facts")
    ksub = p.add_subparsers(dest="knowledge_action", required=True)
    kl = ksub.add_parser("list", help="list knowledge facts")
    kl.set_defaults(func=layer_commands.cmd_knowledge_list)
    kl.add_argument("--json", action="store_true")
    ks = ksub.add_parser("show", help="show a knowledge fact")
    ks.set_defaults(func=layer_commands.cmd_knowledge_show)
    ks.add_argument("fact_id")
    ks.add_argument("--json", action="store_true")

    # router
    p = add("search", commands.cmd_search, "search the retrieval index")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")

    p = add("prepare", commands.cmd_prepare, "build a context pack (no Kiro call)")
    p.add_argument("mode", choices=sorted(["ask", "debug", "review", "plan", "implement"]))
    p.add_argument("request", nargs="+")
    p.add_argument("--allow-inferred-low", action="store_true", dest="allow_inferred_low")
    p.add_argument("--json", action="store_true")

    p = add("ctx", _ctx_dispatch, "inspect context-pack selection decisions")
    csub = p.add_subparsers(dest="ctx_action", required=True)
    ce = csub.add_parser("explain", help="show selection-explain for a session")
    ce.set_defaults(func=layer_commands.cmd_ctx_explain)
    ce.add_argument("session", nargs="?", default="latest")
    ce.add_argument("--json", action="store_true")

    p = add("ask", commands.cmd_ask, "build a context pack and run Kiro")
    p.add_argument("question", nargs="+")
    p.add_argument("--mode", default="ask",
                   choices=sorted(["ask", "debug", "review", "plan", "implement"]))

    p = add("audit", _audit_dispatch, "audit a Kiro answer")
    ausub = p.add_subparsers(dest="audit_action", required=True)
    aa = ausub.add_parser("answer", help="audit a session's answer")
    aa.set_defaults(func=commands.cmd_audit_answer)
    aa.add_argument("session", nargs="?", default="latest")
    aa.add_argument("--strict", action="store_true")
    aa.add_argument("--json", action="store_true")

    add("smart", commands.cmd_smart, "print the latest session (pack + answer + audit)")

    p = add("tui", commands.cmd_tui, "interactive cockpit (or --print for a text snapshot)")
    p.add_argument("--print", choices=["dashboard", "units", "sessions", "gaps", "unit", "session"],
                   help="render one screen as text and exit (no TTY needed)")
    p.add_argument("--unit", help="unit id for --print unit")
    p.add_argument("--session", help="session id for --print session")

    # flow / impact
    p = add("graph", _flow_dispatch, "build the call graph")
    gsub = p.add_subparsers(dest="graph_action", required=True)
    gb = gsub.add_parser("build", help="build nodes + edges")
    gb.set_defaults(func=commands.cmd_graph_build)
    gb.add_argument("--json", action="store_true")

    p = add("flow", _flow_dispatch, "show unit or endpoint flow")
    fsub = p.add_subparsers(dest="flow_action", required=True)
    fu = fsub.add_parser("unit", help="flow around a unit")
    fu.set_defaults(func=commands.cmd_flow_unit)
    fu.add_argument("unit_id")
    fu.add_argument("--json", action="store_true")
    fe = fsub.add_parser("endpoint", help='flow from an endpoint, e.g. "GET /users/search"')
    fe.set_defaults(func=commands.cmd_flow_endpoint)
    fe.add_argument("spec", nargs="+")
    fe.add_argument("--json", action="store_true")

    p = add("impact", _flow_dispatch, "show impact of a change")
    imsub = p.add_subparsers(dest="impact_action", required=True)
    imf = imsub.add_parser("file", help="impact of changing a file")
    imf.set_defaults(func=commands.cmd_impact_file)
    imf.add_argument("path")
    imf.add_argument("--json", action="store_true")
    imu = imsub.add_parser("unit", help="impact of changing a unit")
    imu.set_defaults(func=commands.cmd_impact_unit)
    imu.add_argument("unit_id")
    imu.add_argument("--json", action="store_true")

    p = add("tests-for", commands.cmd_tests_for, "find tests that reach a unit or file")
    p.add_argument("target")
    p.add_argument("--json", action="store_true")

    # conductor / orchestration
    p = add("orchestrate", _orchestrate_dispatch, "run a conductor workflow")
    osub = p.add_subparsers(dest="workflow", required=True)
    for wf, help_text in [
        ("debug", "investigate a bug or issue"),
        ("review", "review code changes"),
        ("plan", "plan an implementation"),
    ]:
        op = osub.add_parser(wf, help=help_text)
        op.set_defaults(func=commands.cmd_orchestrate)
        op.add_argument("request", nargs="+", help="request or question")
        op.add_argument("--no-agent", action="store_true", dest="no_agent",
                        help="skip child agent; generate plan from context pack only")
        op.add_argument("--json", action="store_true")

    p = add("orchestrations", _orchestrations_dispatch, "list or inspect orchestrations")
    orsub = p.add_subparsers(dest="orchestrations_action", required=True)
    orl = orsub.add_parser("list", help="list past orchestrations")
    orl.set_defaults(func=commands.cmd_orchestrations_list)
    orl.add_argument("--json", action="store_true")
    orsh = orsub.add_parser("show", help="show an orchestration (default: latest)")
    orsh.set_defaults(func=commands.cmd_orchestrations_show)
    orsh.add_argument("orch_id", nargs="?", default=None)
    orsh.add_argument("--json", action="store_true")

    p = add("synthesize", commands.cmd_synthesize, "synthesize findings for an orchestration")
    p.add_argument("orch_id", nargs="?", default=None,
                   help="orchestration id (default: latest)")
    p.add_argument("--json", action="store_true")

    p = add("conflicts", commands.cmd_conflicts, "show synthesis conflicts")
    p.add_argument("orch_id", nargs="?", default=None)
    p.add_argument("--json", action="store_true")

    p = add("agent-validate", commands.cmd_agent_validate, "validate an agent result file")
    p.add_argument("result_file", help="path to a file containing a groundrail_agent_result block")

    # evidence kernel
    p = add("validate", commands.cmd_validate, "validate artifact envelopes and records")
    p.add_argument("--strict", action="store_true")

    p = add("verify", commands.cmd_verify, "verify source freshness")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--json", action="store_true")

    p = add("gaps", commands.cmd_gaps, "list capability gaps")
    p.add_argument("--json", action="store_true")

    p = add("doctor", commands.cmd_doctor, "diagnose workspace + configuration")
    p.add_argument("--json", action="store_true")

    p = add("map", layer_commands.cmd_map, "show the implemented end-to-end Groundrail layer map")
    p.add_argument("--json", action="store_true")

    p = add("eval", _eval_dispatch, "run built-in trust regression checks")
    esub = p.add_subparsers(dest="eval_action", required=True)
    er = esub.add_parser("run", help="run the built-in evaluation checks")
    er.set_defaults(func=layer_commands.cmd_eval_run)
    er.add_argument("--strict", action="store_true")
    er.add_argument("--json", action="store_true")

    return parser


def _normalise_args(args: argparse.Namespace) -> None:
    """Apply cross-flag semantics after argparse has parsed the command line."""
    if getattr(args, "command", None) == "analyze-units" and getattr(args, "changed", False):
        args.stale = True
        args.missing = True


def _unit_dispatch(args):  # pragma: no cover - argparse routes to subfuncs
    return args.func(args)


def _analysis_dispatch(args):  # pragma: no cover
    return args.func(args)


def _review_dispatch(args):  # pragma: no cover
    return args.func(args)


def _notes_dispatch(args):  # pragma: no cover
    return args.func(args)


def _promote_dispatch(args):  # pragma: no cover
    return args.func(args)


def _knowledge_dispatch(args):  # pragma: no cover
    return args.func(args)


def _ctx_dispatch(args):  # pragma: no cover
    return args.func(args)


def _audit_dispatch(args):  # pragma: no cover
    return args.func(args)


def _flow_dispatch(args):  # pragma: no cover
    return args.func(args)


def _orchestrate_dispatch(args):  # pragma: no cover
    return args.func(args)


def _orchestrations_dispatch(args):  # pragma: no cover
    return args.func(args)


def _eval_dispatch(args):  # pragma: no cover
    return args.func(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _normalise_args(args)
    try:
        return args.func(args)
    except GroundrailError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if getattr(exc, "errors", None):
            for err in exc.errors:
                print(f"  - {err}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:  # pragma: no cover
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
