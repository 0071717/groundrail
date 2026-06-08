"""Groundrail CLI entry point and argument parsing."""

from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..core.errors import GroundrailError
from . import commands


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

    return parser


def _unit_dispatch(args):  # pragma: no cover - argparse routes to subfuncs
    return args.func(args)


def _analysis_dispatch(args):  # pragma: no cover
    return args.func(args)


def _audit_dispatch(args):  # pragma: no cover
    return args.func(args)


def _flow_dispatch(args):  # pragma: no cover
    return args.func(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
