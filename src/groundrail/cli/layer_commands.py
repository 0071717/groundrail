"""CLI handlers for review, knowledge, map, ctx, and evaluation layers."""

from __future__ import annotations

import json
from typing import Any

from ..core.errors import GroundrailError
from ..core.workspace import Workspace
from ..evaluation import EvaluationRunner
from ..knowledge import KnowledgeStore
from ..layers import LayerMapBuilder
from ..review import ReviewStore
from ..router.session import SessionStore


def _ws() -> Workspace:
    return Workspace.find()


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2))


# --- review ------------------------------------------------------------------
def cmd_review_list(args: Any) -> int:
    items = ReviewStore(_ws().store).queue()
    if args.json:
        _emit(items)
    else:
        if not items:
            print("no review items; run `groundrail analyze-units --missing` first")
        for item in items[: args.limit]:
            print(f"{item['item_id']}  [{item['state']}/{item['confidence']}/{item['review_status']}] {item['scope']}")
            print(f"  {item['text'][:160]}")
        print(f"\n{len(items)} review item(s)")
    return 0


def cmd_review_show(args: Any) -> int:
    item = ReviewStore(_ws().store).get_item(args.item_id)
    if args.json:
        _emit(item)
    else:
        print(f"{item['item_id']}")
        print(f"  unit:    {item['unit_id']}")
        print(f"  scope:   {item['scope']}")
        print(f"  state:   {item['state']}/{item['confidence']}")
        print(f"  review:  {item['review_status']}")
        print(f"  stale:   {item['stale']}")
        print(f"\n{item['text']}")
    return 0


def cmd_review_confirm(args: Any) -> int:
    record = ReviewStore(_ws().store).confirm(args.item_id, reviewer=args.reviewer, note=args.note or "")
    if args.json:
        _emit(record)
    else:
        print(f"confirmed {record['item_id']} -> {record['review_id']}")
    return 0


def cmd_review_reject(args: Any) -> int:
    record = ReviewStore(_ws().store).reject(args.item_id, reviewer=args.reviewer, note=args.note or "")
    if args.json:
        _emit(record)
    else:
        print(f"rejected {record['item_id']} -> {record['review_id']}")
    return 0


def cmd_review_stale(args: Any) -> int:
    result = ReviewStore(_ws().store).stale_confirmations()
    if args.json:
        _emit(result)
    else:
        print(f"stale confirmations: {result['status']} ({result['count']})")
        for item in result["items"]:
            print(f"  {item['item_id']} ({item['scope']})")
    return 0


# --- notes -------------------------------------------------------------------
def cmd_notes_list(args: Any) -> int:
    notes = [i for i in ReviewStore(_ws().store).queue() if i["scope"] in ("ai_note", "uncertainty")]
    if args.json:
        _emit(notes)
    else:
        for item in notes[: args.limit]:
            print(f"{item['item_id']}  [{item['review_status']}] {item['text'][:160]}")
        print(f"\n{len(notes)} note/uncertainty item(s)")
    return 0


def cmd_notes_show(args: Any) -> int:
    return cmd_review_show(args)


def cmd_notes_confirm(args: Any) -> int:
    return cmd_review_confirm(args)


def cmd_notes_reject(args: Any) -> int:
    return cmd_review_reject(args)


# --- promotion / knowledge ----------------------------------------------------
def cmd_promote_candidates(args: Any) -> int:
    rows = KnowledgeStore(_ws().store).candidates()
    if args.json:
        _emit(rows)
    else:
        if not rows:
            print("no promotable claims; confirm review items first")
        for row in rows:
            print(f"{row['item_id']}  eligible={row['eligible']} reason={row['reason']}")
            print(f"  {row['text'][:160]}")
        print(f"\n{len(rows)} promotion candidate(s)")
    return 0


def cmd_promote_claim(args: Any) -> int:
    fact = KnowledgeStore(_ws().store).promote(args.item_id, promoted_by=args.promoted_by)
    if args.json:
        _emit(fact)
    else:
        print(f"promoted {args.item_id} -> {fact['fact_id']}")
    return 0


def cmd_knowledge_list(args: Any) -> int:
    facts = KnowledgeStore(_ws().store).all()
    if args.json:
        _emit(facts)
    else:
        for fact in facts:
            print(f"{fact['fact_id']} [{fact['review_status']}/{fact['confidence']}] {fact['text'][:160]}")
        print(f"\n{len(facts)} fact(s)")
    return 0


def cmd_knowledge_show(args: Any) -> int:
    fact = KnowledgeStore(_ws().store).get(args.fact_id)
    if args.json:
        _emit(fact)
    else:
        print(f"{fact['fact_id']}")
        print(f"  source item: {fact['source_item_id']}")
        print(f"  unit:        {fact['unit_id']}")
        print(f"  state:       {fact['state']}/{fact['confidence']}/{fact['review_status']}")
        print(f"\n{fact['text']}")
    return 0


# --- context explanation ------------------------------------------------------
def cmd_ctx_explain(args: Any) -> int:
    ws = _ws()
    sessions = SessionStore(ws.store)
    sid = args.session if args.session and args.session != "latest" else sessions.latest_id()
    if not sid:
        raise GroundrailError("no sessions found; run `groundrail prepare` first")
    data = sessions.read(sid, "selection-explain.json")
    if args.json:
        _emit(data)
    else:
        print(f"context selection: {sid}")
        for decision in data.get("decisions", []):
            print(f"  {decision.get('decision')}: {decision.get('item_id')} — {decision.get('reason')}")
    return 0


# --- layer map / eval ---------------------------------------------------------
def cmd_map(args: Any) -> int:
    result = LayerMapBuilder(_ws()).build(write=True)
    if args.json:
        _emit(result)
    else:
        print("Groundrail layer map")
        for layer in result["layers"]:
            ready = "ready" if layer["workspace_ready"] else "not-yet-generated"
            print(f"- {layer['layer']}: implemented, {ready}")
            print(f"  commands: {', '.join(layer['commands'])}")
            for artifact in layer["artifacts"]:
                mark = "yes" if artifact["exists"] else "no"
                print(f"    artifact {artifact['path']}: {mark}")
        print("\nflow:")
        for edge in result["flow_edges"]:
            print(f"  {edge['from']} -> {edge['to']}")
    return 0


def cmd_eval_run(args: Any) -> int:
    result = EvaluationRunner(_ws()).run()
    if args.json:
        _emit(result)
    else:
        print(f"eval: {result['status']} ({result['failures']} failures, {result['warnings']} warnings)")
        for check in result["checks"]:
            print(f"  [{check['status']}] {check['name']}: {check['detail']}")
    if args.strict and result["status"] == "fail":
        return 3
    return 0
