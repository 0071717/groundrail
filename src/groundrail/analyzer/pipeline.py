"""Analysis pipeline: secret-scan -> prompt -> run -> validate -> store.

Ties the analyzer pieces together for one unit or a batch. Secret scanning runs
before any prompt is built so secret-bearing units never leave the machine; such
units are recorded as capability gaps instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import secrets
from ..core.errors import SecretError
from ..core.gaps import CapabilityGapRegistry
from ..core.store import ArtifactStore
from ..core.workspace import Workspace
from ..indexer.snapshot import FILE_INDEX_PATH
from ..indexer.unit_index import UnitStore
from . import prompt as prompt_mod
from .runner import UnitAnalysisRunner
from .store import AnalysisStore
from .validator import parse_and_validate

ANALYSIS_REPORT_PATH = "audit/unit-analysis-report.json"


class AnalysisPipeline:
    def __init__(self, workspace: Workspace, *, runner: UnitAnalysisRunner | None = None) -> None:
        self.workspace = workspace
        self.store: ArtifactStore = workspace.store
        self.units = UnitStore(self.store)
        self.analyses = AnalysisStore(self.store)
        self.runner = runner or UnitAnalysisRunner()

    def _source(self) -> dict[str, Any]:
        from ..core import envelope

        if self.store.exists(FILE_INDEX_PATH):
            return self.store.read_json(FILE_INDEX_PATH).get("source", envelope.make_source())
        return envelope.make_source()

    def analyze_unit(self, unit_id: str, *, command: str = "groundrail analyze-unit") -> dict[str, Any]:
        unit = self.units.get(unit_id)
        source_text = self._unit_source(unit)

        hits = secrets.scan(source_text)
        if hits:
            self._record_secret_gap(unit, hits, command)
            raise SecretError(
                f"unit {unit_id} appears to contain secrets "
                f"({hits[0].kind} at line {hits[0].line}); skipped analysis"
            )

        packet = prompt_mod.build_packet(unit, source_text=source_text)
        prompt_text = prompt_mod.render_prompt(packet)
        phash = prompt_mod.prompt_hash(prompt_text)
        raw = self.runner.run(prompt_text)

        analysis, report = parse_and_validate(
            raw, unit, model=self._model_label(), prompt_hash=phash
        )
        if not report.ok:
            from ..core.errors import ValidationError

            raise ValidationError(
                f"AI analysis for {unit_id} failed validation", report.errors
            )
        self.analyses.write(analysis, source=self._source(), command=command)
        return analysis

    def analyze_units(
        self,
        *,
        only_stale: bool = False,
        only_missing: bool = False,
        kind: str | None = None,
        limit: int | None = None,
        command: str = "groundrail analyze-units",
    ) -> dict[str, Any]:
        targets = self.units.all()
        if kind:
            targets = [u for u in targets if u["kind"] == kind]

        selected: list[dict[str, Any]] = []
        for unit in targets:
            existing = self.analyses.try_get(unit["unit_id"])
            is_missing = existing is None
            is_stale = bool(existing is not None and self.analyses.is_stale(existing, unit))

            if only_missing or only_stale:
                # Union semantics: --missing selects missing analyses, --stale selects
                # existing stale analyses, and --changed means both. Do not treat a
                # missing analysis as stale; that made --stale silently process new
                # units and contradicted the CLI help text.
                if not ((only_missing and is_missing) or (only_stale and is_stale)):
                    continue

            selected.append(unit)
        if limit is not None:
            selected = selected[:limit]

        analysed, skipped, failed = [], [], []
        for unit in selected:
            try:
                self.analyze_unit(unit["unit_id"], command=command)
                analysed.append(unit["unit_id"])
            except SecretError:
                skipped.append(unit["unit_id"])
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                failed.append({"unit_id": unit["unit_id"], "error": str(exc)})

        report = {
            "analysed": analysed,
            "skipped_secrets": skipped,
            "failed": failed,
            "selected_count": len(selected),
        }
        self._write_report(report, command)
        return report

    # --- helpers -------------------------------------------------------------
    def _unit_source(self, unit: dict[str, Any]) -> str:
        repo_root = self.workspace.repo_root(unit["repo"])
        text = Path(repo_root / unit["file_path"]).read_text(encoding="utf-8")
        lines = text.splitlines()
        span = unit["span"]
        return "\n".join(lines[span["start_line"] - 1 : span["end_line"]])

    def _model_label(self) -> str:
        import os

        return os.environ.get("GROUNDRAIL_AI_CMD") or os.environ.get(
            "GROUNDRAIL_KIRO_CMD", "configured-ai-command"
        )

    def _record_secret_gap(self, unit: dict[str, Any], hits: list, command: str) -> None:
        registry = CapabilityGapRegistry(self.store)
        registry.extend(registry.load())
        registry.add(
            kind="secret_in_unit",
            repo=unit["repo"],
            location=f"{unit['file_path']}:{hits[0].line}",
            detail=f"possible {hits[0].kind}; unit excluded from AI analysis",
            severity="high",
        )
        registry.write(command=command, source=self._source())

    def _write_report(self, report: dict[str, Any], command: str) -> None:
        from ..core import envelope

        artifact = envelope.build_envelope(
            artifact_id="groundrail.audit.unit_analysis",
            artifact_kind="unit_analysis_report",
            generator=envelope.make_generator(command, "groundrail.analyzer"),
            source=self._source(),
            data=report,
        )
        self.store.write_json(ANALYSIS_REPORT_PATH, artifact)
