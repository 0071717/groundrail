"""AI command runner.

Shells out to a configurable command (``GROUNDRAIL_AI_CMD`` or, failing that,
``GROUNDRAIL_KIRO_CMD``). The command receives the prompt on stdin, or via a
temp file substituted into a ``{prompt_file}`` placeholder. A callable can be
injected for tests so no real model is needed.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from ..core.errors import ConfigError, GroundrailError

AI_CMD_ENV = "GROUNDRAIL_AI_CMD"
KIRO_CMD_ENV = "GROUNDRAIL_KIRO_CMD"

RunFn = Callable[[str], str]


class UnitAnalysisRunner:
    def __init__(self, *, run_fn: RunFn | None = None, command: str | None = None) -> None:
        self._run_fn = run_fn
        self._command = command or os.environ.get(AI_CMD_ENV) or os.environ.get(KIRO_CMD_ENV)

    @property
    def configured(self) -> bool:
        return self._run_fn is not None or bool(self._command)

    def run(self, prompt_text: str) -> str:
        if self._run_fn is not None:
            return self._run_fn(prompt_text)
        if not self._command:
            raise ConfigError(
                f"no AI command configured; set {AI_CMD_ENV} (or {KIRO_CMD_ENV})"
            )
        return self._run_command(prompt_text)

    def _run_command(self, prompt_text: str) -> str:
        if "{prompt_file}" in self._command:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(prompt_text)
                prompt_path = fh.name
            try:
                args = [
                    a.replace("{prompt_file}", prompt_path)
                    for a in shlex.split(self._command)
                ]
                return _exec(args, stdin=None)
            finally:
                Path(prompt_path).unlink(missing_ok=True)
        return _exec(shlex.split(self._command), stdin=prompt_text)


def _exec(args: list[str], *, stdin: str | None) -> str:
    try:
        result = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConfigError(f"AI command not found: {args[0]!r}") from exc
    except subprocess.SubprocessError as exc:
        raise GroundrailError(f"AI command failed: {exc}") from exc
    if result.returncode != 0:
        raise GroundrailError(
            f"AI command exited {result.returncode}: {result.stderr.strip()[:500]}"
        )
    return result.stdout
