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
    """Compose a titled, footed frame.

    With an integer ``height`` the body is clamped/padded to fill the screen
    (interactive curses). With ``height is None`` the frame fits the body exactly
    (non-interactive ``--print``).
    """
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
        f"  files indexed : {vm['files']}",
        f"  units         : {vm['units']}   analysed: {vm['analysed']}   "
        f"unanalysed: {vm['unanalysed']}   stale: {vm['stale']}",
        f"  capability gaps: {vm['gaps']}     sessions: {len(vm['sessions'])}",
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
        flag = "*" if review == "dev_confirmed" else ""
        span = r["span"]
        lines.append(
            f"{_marker(i == selection)}{r['symbol']:22s} {r['kind']:22s} "
            f"[{a:8s}]{flag:1s} {r['file_path']}:{span['start_line']}"
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


def render_sessions(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} session(s)   (enter: detail)", ""]
    for i, r in enumerate(rows):
        lines.append(
            f"{_marker(i == selection)}{r['session_id']}  [{r.get('mode','')}]  "
            f"audit={r.get('audit','-') or '-'}  {truncate(r.get('request',''), 40)}"
        )
    return lines


def render_session_detail(detail: dict[str, Any], width: int) -> list[str]:
    lines = [f"  session {detail['session_id']}", ""]
    if "pack_md" in detail:
        lines.append("  -- context pack --")
        lines.extend("  " + l for l in detail["pack_md"].splitlines())
        lines.append("")
    if "answer" in detail:
        lines.append("  -- kiro answer --")
        lines.extend("  " + l for l in detail["answer"].splitlines())
        lines.append("")
    if "audit" in detail:
        audit = detail["audit"]
        lines.append(f"  -- audit: {audit['status']} ({audit.get('claims_checked', 0)} claims) --")
        for f in audit.get("findings", []):
            lines.append(f"    [{f['severity']}] {f['message']}")
    return lines


def render_gaps(rows: list[dict[str, Any]], selection: int, width: int) -> list[str]:
    lines = [f"  {len(rows)} capability gap(s)", ""]
    for i, g in enumerate(rows):
        lines.append(
            f"{_marker(i == selection)}[{g.get('severity','info')}] {g.get('kind','')}: "
            f"{g.get('detail','')} ({g.get('location','')})"
        )
    return lines


def footer_for(screen: str) -> str:
    common = "tab/1-4: screens   q: quit   r: refresh"
    if screen in ("unit", "session"):
        return "esc: back   " + common
    return common
