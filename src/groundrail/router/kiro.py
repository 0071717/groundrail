"""Kiro runner.

Runs the configured ``GROUNDRAIL_KIRO_CMD`` against a context pack. The command
may use a ``{context_pack}`` placeholder (replaced with the pack file path) or
receive the pack on stdin. Injectable for tests.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Callable

from ..core.errors import ConfigError, GroundrailError

KIRO_CMD_ENV = "GROUNDRAIL_KIRO_CMD"

RunFn = Callable[[str, str], str]


class KiroRunner:
    def __init__(self, *, run_fn: RunFn | None = None, command: str | None = None) -> None:
        self._run_fn = run_fn
        self._command = command or os.environ.get(KIRO_CMD_ENV)

    @property
    def configured(self) -> bool:
        return self._run_fn is not None or bool(self._command)

    def run(self, *, pack_markdown: str, pack_path: str) -> str:
        if self._run_fn is not None:
            return self._run_fn(pack_markdown, pack_path)
        if not self._command:
            raise ConfigError(
                f"Kiro not configured; set {KIRO_CMD_ENV} "
                f"(e.g. 'kiro-cli --prompt-file {{context_pack}}')"
            )
        if "{context_pack}" in self._command:
            args = [a.replace("{context_pack}", pack_path) for a in shlex.split(self._command)]
            return _exec(args, stdin=None)
        return _exec(shlex.split(self._command), stdin=pack_markdown)


def _exec(args: list[str], *, stdin: str | None) -> str:
    try:
        result = subprocess.run(
            args, input=stdin, capture_output=True, text=True, timeout=600, check=False
        )
    except FileNotFoundError as exc:
        raise ConfigError(f"Kiro command not found: {args[0]!r}") from exc
    except subprocess.SubprocessError as exc:
        raise GroundrailError(f"Kiro command failed: {exc}") from exc
    if result.returncode != 0:
        raise GroundrailError(f"Kiro exited {result.returncode}: {result.stderr.strip()[:500]}")
    return result.stdout
