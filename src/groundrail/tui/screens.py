"""Pure screen composition: pick a screen, fetch its view model, render a frame.

Shared by the interactive curses app and the ``tui --print`` mode, so both show
exactly the same output and this layer stays fully testable.
"""

from __future__ import annotations

from typing import Any

from . import render
from .viewmodels import ViewModelBuilder

_TITLES = {
    "dashboard": "Dashboard",
    "units": "Units",
    "unit": "Unit detail",
    "sessions": "Sessions",
    "session": "Session detail",
    "gaps": "Capability gaps",
}


def default_ui() -> dict[str, Any]:
    return {"screen": "dashboard", "selection": 0, "scroll": 0,
            "selected_unit": None, "selected_session": None}


def row_count(builder: ViewModelBuilder, screen: str) -> int:
    if screen == "units":
        return len(builder.units_rows())
    if screen == "sessions":
        return len(builder.sessions_rows())
    if screen == "gaps":
        return len(builder.gaps_rows())
    return 0


def body_lines(builder: ViewModelBuilder, ui: dict[str, Any], width: int) -> list[str]:
    screen = ui["screen"]
    if screen == "dashboard":
        return render.render_dashboard(builder.dashboard(), width)
    if screen == "units":
        return render.render_units(builder.units_rows(), ui["selection"], width)
    if screen == "unit":
        return render.render_unit_detail(builder.unit_detail(ui["selected_unit"]), width)
    if screen == "sessions":
        return render.render_sessions(builder.sessions_rows(), ui["selection"], width)
    if screen == "session":
        return render.render_session_detail(builder.session_detail(ui["selected_session"]), width)
    if screen == "gaps":
        return render.render_gaps(builder.gaps_rows(), ui["selection"], width)
    return ["unknown screen"]


def compose(builder: ViewModelBuilder, ui: dict[str, Any], width: int, height: int | None) -> list[str]:
    body = body_lines(builder, ui, width)
    scroll = ui.get("scroll", 0)
    if scroll:
        body = body[scroll:]
    title = _TITLES.get(ui["screen"], ui["screen"])
    return render.frame(title, body, render.footer_for(ui["screen"]), width, height)
