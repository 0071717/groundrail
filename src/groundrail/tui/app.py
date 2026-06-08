"""Interactive curses cockpit.

A thin event loop: it owns UI state (current screen, selection, scroll) and
delegates all data + layout to :mod:`screens`. No trust logic lives here. The
curses runtime is exercised manually, not in CI, so it is excluded from coverage.
"""

from __future__ import annotations

from ..core.workspace import Workspace
from . import screens
from .viewmodels import SCREENS, ViewModelBuilder


def run(workspace: Workspace) -> None:  # pragma: no cover - requires a real TTY
    import curses

    curses.wrapper(lambda stdscr: _loop(stdscr, workspace))


def _loop(stdscr, workspace: Workspace):  # pragma: no cover
    import curses

    curses.curs_set(0)
    stdscr.keypad(True)
    builder = ViewModelBuilder(workspace)
    ui = screens.default_ui()

    while True:
        height, width = stdscr.getmaxyx()
        frame = screens.compose(builder, ui, width, height)
        stdscr.erase()
        for y, line in enumerate(frame[:height]):
            try:
                stdscr.addstr(y, 0, line[: width - 1])
            except curses.error:
                pass
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break
        if not _handle_key(key, ui, builder):
            builder = ViewModelBuilder(workspace)


def _handle_key(key, ui, builder) -> bool:  # pragma: no cover
    import curses

    screen = ui["screen"]
    if ord("1") <= key <= ord("9"):
        idx = key - ord("1")
        if idx < len(SCREENS):
            ui.update(screen=SCREENS[idx], selection=0, scroll=0)
            return True
    if key == ord("\t"):
        idx = (SCREENS.index(screen) if screen in SCREENS else 0)
        ui.update(screen=SCREENS[(idx + 1) % len(SCREENS)], selection=0, scroll=0)
        return True
    if key == ord("r"):
        ui["scroll"] = 0
        return False  # signal caller to rebuild
    if key == 27:  # esc -> back to list
        ui.update(screen="units" if screen == "unit" else "sessions" if screen == "session" else screen,
                  scroll=0)
        return True

    is_detail = screen in ("unit", "session", "dashboard", "map", "eval")
    if key in (curses.KEY_DOWN, ord("j")):
        if is_detail:
            ui["scroll"] += 1
        else:
            ui["selection"] = min(ui["selection"] + 1, max(0, screens.row_count(builder, screen) - 1))
        return True
    if key in (curses.KEY_UP, ord("k")):
        if is_detail:
            ui["scroll"] = max(0, ui["scroll"] - 1)
        else:
            ui["selection"] = max(0, ui["selection"] - 1)
        return True
    if key in (curses.KEY_ENTER, 10, 13):
        _enter(ui, builder)
        return True
    return True


def _enter(ui, builder):  # pragma: no cover
    if ui["screen"] == "units":
        rows = builder.units_rows()
        if rows:
            ui.update(screen="unit", selected_unit=rows[ui["selection"]]["unit_id"], scroll=0)
    elif ui["screen"] == "sessions":
        rows = builder.sessions_rows()
        if rows:
            ui.update(screen="session", selected_session=rows[ui["selection"]]["session_id"], scroll=0)
