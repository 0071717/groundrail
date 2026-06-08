"""Pure text rendering for the TUI.

Every function takes plain data + a width/height and returns a list of strings.
No curses, no I/O — so frames can be snapshot-tested and the same code powers the
``tui --print`` non-interactive mode.
"""

from __future__ import annotations

from typing import Any

CONF_GLYPH = {"high": "+++", "medium": "++ ", "low": "+  ", "none": "   "}


def truncate(text: str, width: int) -> str:
    text = text.replace("\t", "    ")
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"


def frame(title: str, body: list[str], footer: str, width: int, height: int | None) -> list[str]:
    """Compose a titled, footed frame."""
    bar = truncate(f" Groundrail │ {title}", width).ljust(width)
    sep = "─" * width
    if height is not None:
        inner_height = max(1, height - 4)
        body = body[:inner_height]
        while len(body) < inner_height:
            body.append("")
    lines = [bar, sep]
    lines.extend(truncate(b, width).ljust(width) for b in body)
    lines.append(sep)
    lines.append(truncate(footer, width).ljust(width))
    return lines


def _marker(selected: bool) -> str:
    return "> " if selected else "  "


# --- screens -----------------------------------------------------------------
def render_dashboard(vm: dict[str, Any], width: int) -> list[str]:
    lines = [
        "",
        "  trust boundary:",
        f"    files={vm['files']}  units={vm['units']}  analysed={vm['analysed']}  "
        f"unanalysed={vm['unanalysed']}  stale={vm['stale']}",
        f"    review_items={vm['review_items']}  confirmed={vm['confirmed_items']}  "
        f"knowledge_facts={vm['knowledge_facts']}",
        f"    layers_ready={vm['layers_ready']}/{vm['layers_total']}  "
        f"gaps={vm['gaps']}  eval={vm['eval_status']}",
        "",
        "  unit kinds:",
    ]
    for kind, count in vm["kinds"][:10]:
        lines.append(f"    {kind:28s} {count}")
    lines.append("")
    latest = vm["latest_session"]
    if latest:
        lines.append("  latest session:")
        lines.append(f"    {latest['session_id']}  [{latest.get('mode','')}] "
                     f"audit={latest.get('audit','-')}")
        lines.append(f"    request: {latest.get('request','')}")
    else:
        lines.append("  latest session: (none) - run `groundrail ask`")
    return lines


def render_units(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} unit(s)   (enter: detail, j/k: move)", ""]
    for i, r in enumerate(rows):
        a = r.get("analysis_state") or "-"
        review = r.get("review_status") or ""
        flag = "✓" if review == "dev_confirmed" else "!" if review == "dev_rejected" else " "
        span = r["span"]
        lines.append(
            f"{_marker(i == selection)}{flag} {r['symbol']:22s} {r['kind']:22s} "
            f"[{a:8s}] {r['file_path']}:{span['start_line']}"
        )
    return lines


def render_unit_detail(detail: dict[str, Any], width: int) -> list[str]:
    u = detail["unit"]
    a = detail["analysis"]
    span = u["span"]
    lines = [
        f"  {u['unit_id']}",
        f"  {u['kind']}  {u['file_path']}:{span['start_line']}-{span['end_line']}  "
        f"[{u['state']}/{u['confidence']}]",
        "",
    ]
    if a:
        lines.append(f"  analysis [{a['state']}/{a['confidence']}] review={a['review_status']}")
        lines.append(f"    {a['summary']}")
        for claim in a.get("intent", [])[:3]:
            lines.append(f"    claim {claim['claim_id']} [{claim.get('review_status','')}] {claim['text']}")
        for unc in a.get("uncertainties", [])[:3]:
            lines.append(f"    ? {unc['text']}")
        for note in a.get("ai_notes", [])[:3]:
            lines.append(f"    ! [{note['severity']}] {note['type']}: {note['text']}")
    else:
        lines.append("  analysis: (none)")
    lines.append("")
    if detail["callers"]:
        lines.append("  callers: " + ", ".join(c["symbol"] for c in detail["callers"][:8]))
    if detail["callees"]:
        lines.append("  callees: " + ", ".join(c["symbol"] for c in detail["callees"][:8]))
    lines.append("")
    lines.append("  source:")
    base = span["start_line"]
    for offset, src in enumerate(detail["source"]):
        lines.append(f"  {base + offset:5d}  {src}")
    return lines


def render_review(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} review item(s)   ✓ confirmed  ! rejected", ""]
    for i, r in enumerate(rows):
        status = r.get("review_status", "")
        flag = "✓" if status == "dev_confirmed" else "!" if status == "dev_rejected" else " "
        stale = " stale" if r.get("stale") else ""
        lines.append(f"{_marker(i == selection)}{flag} {r['scope']:16s} [{r['state']}/{r['confidence']}/{status}]{stale}")
        lines.append(f"    {truncate(r['item_id'], max(20, width - 8))}")
        lines.append(f"    {truncate(r.get('text',''), max(20, width - 8))}")
    return lines


def render_knowledge(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} promoted fact(s)", ""]
    for i, f in enumerate(rows):
        lines.append(
            f"{_marker(i == selection)}{f['fact_id']} [{f['state']}/{f['confidence']}/{f['review_status']}]"
        )
        lines.append(f"    {truncate(f.get('text',''), max(20, width - 8))}")
        lines.append(f"    from {truncate(f.get('source_item_id',''), max(20, width - 10))}")
    return lines


def render_sessions(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} session(s)   (enter: detail)", ""]
    for i, r in enumerate(rows):
        lines.append(
            f"{_marker(i == selection)}{r['session_id']}  [{r.get('mode','')}]  "
            f"audit={r.get('audit','-') or '-'} facts={r.get('facts',0)} analyses={r.get('analyses',0)}  "
            f"{truncate(r.get('request',''), 40)}"
        )
    return lines


def render_session_detail(detail: dict[str, Any], width: int) -> list[str]:
    lines = [f"  session {detail['session_id']}", ""]
    if "audit" in detail:
        audit = detail["audit"]
        lines.append(f"  audit: {audit['status']} ({audit.get('claims_checked', 0)} claims)")
        for f in audit.get("findings", []):
            lines.append(f"    [{f['severity']}] {f['message']}")
        lines.append("")
    if "pack_md" in detail:
        lines.append("  -- context pack --")
        lines.extend("  " + l for l in detail["pack_md"].splitlines())
        lines.append("")
    if "answer" in detail:
        lines.append("  -- kiro answer --")
        lines.extend("  " + l for l in detail["answer"].splitlines())
        lines.append("")
    return lines


def render_gaps(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} capability gap(s)", ""]
    for i, g in enumerate(rows):
        lines.append(
            f"{_marker(i == selection)}[{g.get('severity','info')}] {g.get('kind','')}: "
            f"{g.get('detail','')} ({g.get('location','')})"
        )
    return lines


def render_layer_map(vm: dict[str, Any], selection: int, width: int) -> list[str]:
    layers = vm.get("layers", [])
    lines = [f"  {len(layers)} implemented layer(s)", ""]
    for i, layer in enumerate(layers):
        ready = "ready" if layer.get("workspace_ready") else "not-yet-generated"
        lines.append(f"{_marker(i == selection)}{layer['layer']:24s} {ready}")
        lines.append(f"    {truncate(layer.get('goal',''), max(20, width - 8))}")
    lines.append("")
    lines.append("  flow:")
    for edge in vm.get("flow_edges", [])[:12]:
        lines.append(f"    {edge['from']} -> {edge['to']}")
    return lines


def render_eval(vm: dict[str, Any], selection: int, width: int) -> list[str]:
    checks = vm.get("checks", [])
    lines = [f"  eval status: {vm.get('status', 'not_run')}", ""]
    if not checks:
        lines.append("  no eval report yet; run `groundrail eval run`")
        return lines
    for i, check in enumerate(checks):
        lines.append(f"{_marker(i == selection)}[{check.get('status')}] {check.get('name')}")
        lines.append(f"    {truncate(check.get('detail',''), max(20, width - 8))}")
    return lines


def footer_for(screen: str) -> str:
    common = "tab/1-8: screens   q: quit   r: refresh"
    if screen in ("unit", "session"):
        return "esc: back   " + common
    return common
