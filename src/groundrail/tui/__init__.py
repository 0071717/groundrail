"""TUI: a read-only cockpit over Groundrail's services.

The TUI never computes trust. It reads service outputs and renders them. Data
lives in :mod:`viewmodels` (plain data, fully testable) and layout lives in
:mod:`render` (pure string functions). :mod:`app` is a thin curses event loop
that blits rendered frames — it holds no business logic.
"""
