"""Comment/string masking and brace matching for TypeScript/JavaScript.

Reliable boundary detection without a real parser hinges on one trick: blank out
the contents of comments and string/template literals (preserving newlines and
character offsets) so that braces, parens, and keywords that remain are real
structure, never text inside a string. Everything else in the TS extractor works
on this masked view, then slices snippets out of the original source.
"""

from __future__ import annotations

import bisect


def mask_source(source: str) -> str:
    """Return ``source`` with comment/string contents replaced by spaces.

    Offsets and line breaks are preserved exactly, so a position in the mask maps
    1:1 to the same position in the original.
    """
    out = list(source)
    i = 0
    n = len(source)
    state: str | None = None  # line, block, sq, dq, tpl
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                state = "line"
                i += 2
                continue
            if c == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                state = "block"
                i += 2
                continue
            if c == "'":
                state = "sq"
            elif c == '"':
                state = "dq"
            elif c == "`":
                state = "tpl"
            i += 1
            continue

        if state == "line":
            if c == "\n":
                state = None
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                state = None
                i += 2
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        # string / template states
        quote = {"sq": "'", "dq": '"', "tpl": "`"}[state]
        if c == "\\":
            out[i] = " "
            if i + 1 < n and source[i + 1] != "\n":
                out[i + 1] = " "
            i += 2
            continue
        if c == quote:
            state = None
            i += 1
            continue
        if c != "\n":
            out[i] = " "
        i += 1
    return "".join(out)


class LineMap:
    """Maps character offsets to 1-based line numbers."""

    def __init__(self, source: str) -> None:
        self._starts = [0]
        for idx, ch in enumerate(source):
            if ch == "\n":
                self._starts.append(idx + 1)

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self._starts, offset)


def match_delimiter(masked: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    """Return the index of the delimiter matching the one at ``open_idx`` (or -1)."""
    depth = 0
    for j in range(open_idx, len(masked)):
        if masked[j] == open_ch:
            depth += 1
        elif masked[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return -1


def statement_end(masked: str, start: int) -> int:
    """Find the end of a simple statement: a top-level ``;`` or newline."""
    depth = 0
    for j in range(start, len(masked)):
        ch = masked[j]
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif depth == 0 and ch in ";\n":
            return j
    return len(masked) - 1
