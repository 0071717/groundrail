"""Deterministic Python unit extraction via the ``ast`` module.

Finds bounded units (functions, async functions, methods, classes) with stable
ids, exact spans, snippet hashes, imports actually used by the unit, call
candidates, and complexity metrics. FastAPI route handlers and Pydantic models
are recognised as specialised kinds; everything else stays generic.

Boundaries are deterministic, so units are ``state: verified`` — but only the
*boundary* is verified, never the behaviour (that is the analyzer's job).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from ..core import evidence as evidence_mod
from ..core import hashing, ids, vocab

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


@dataclass
class ExtractResult:
    units: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)


def extract_file(
    *, repo: str, file_path: str, source_text: str, source_commit: str
) -> ExtractResult:
    """Extract all units from one Python file. Syntax errors become a gap."""
    result = ExtractResult()
    file_hash = hashing.sha256_text(source_text)
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        result.gaps.append(
            {
                "kind": "python_syntax_error",
                "repo": repo,
                "location": f"{file_path}:{exc.lineno or 0}",
                "detail": f"could not parse file: {exc.msg}",
                "severity": "medium",
                "state": "unsupported",
            }
        )
        return result

    lines = source_text.splitlines()
    alias_map = _build_alias_map(tree)

    def visit(node: ast.AST, scope: list[str], in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                unit = _build_callable_unit(
                    child, scope, in_class, repo, file_path, lines,
                    file_hash, source_commit, alias_map,
                )
                result.units.append(unit)
                visit(child, scope + [child.name], in_class=False)
            elif isinstance(child, ast.ClassDef):
                unit = _build_class_unit(
                    child, scope, repo, file_path, lines, file_hash, source_commit, alias_map,
                )
                result.units.append(unit)
                visit(child, scope + [child.name], in_class=True)
            else:
                visit(child, scope, in_class)

    visit(tree, [], in_class=False)
    return result


# --- unit builders -----------------------------------------------------------
def _build_callable_unit(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    scope: list[str],
    in_class: bool,
    repo: str,
    file_path: str,
    lines: list[str],
    file_hash: str,
    source_commit: str,
    alias_map: dict[str, str],
) -> dict[str, Any]:
    qualified = ".".join(scope + [node.name])
    endpoint = _detect_endpoint(node)
    if in_class:
        kind = "python_method"
    elif endpoint is not None:
        kind = "fastapi_endpoint_handler"
    elif not scope and node.name.startswith("test"):
        kind = "test_function"
    else:
        kind = "python_function"

    related = {"endpoint_candidates": [], "test_candidates": []}
    if endpoint is not None:
        related["endpoint_candidates"].append(endpoint)

    return _assemble_unit(
        node=node,
        kind=kind,
        symbol=node.name,
        qualified=qualified,
        repo=repo,
        file_path=file_path,
        lines=lines,
        file_hash=file_hash,
        source_commit=source_commit,
        alias_map=alias_map,
        related=related,
    )


def _build_class_unit(
    node: ast.ClassDef,
    scope: list[str],
    repo: str,
    file_path: str,
    lines: list[str],
    file_hash: str,
    source_commit: str,
    alias_map: dict[str, str],
) -> dict[str, Any]:
    qualified = ".".join(scope + [node.name])
    kind = "pydantic_model" if _is_pydantic(node) else "python_class"
    return _assemble_unit(
        node=node,
        kind=kind,
        symbol=node.name,
        qualified=qualified,
        repo=repo,
        file_path=file_path,
        lines=lines,
        file_hash=file_hash,
        source_commit=source_commit,
        alias_map=alias_map,
        related={"endpoint_candidates": [], "test_candidates": []},
    )


def _assemble_unit(
    *,
    node: ast.AST,
    kind: str,
    symbol: str,
    qualified: str,
    repo: str,
    file_path: str,
    lines: list[str],
    file_hash: str,
    source_commit: str,
    alias_map: dict[str, str],
    related: dict[str, Any],
) -> dict[str, Any]:
    start, end = _span_lines(node)
    snippet = "\n".join(lines[start - 1 : end])
    snippet_hash = hashing.sha256_text(snippet)
    span = evidence_mod.make_span(start, end)
    uid = ids.unit_id(repo, file_path, qualified)

    call_candidates = _call_candidates(node)
    complexity = _complexity(node, start, end, len(call_candidates))
    unit_evidence = evidence_mod.build_evidence(
        evidence_id=ids.evidence_id(uid, "unit_span"),
        evidence_kind="unit_span",
        repo=repo,
        file_path=file_path,
        source_commit=source_commit,
        file_hash=file_hash,
        span=span,
        snippet_hash=snippet_hash,
        extractor_id="groundrail.python.units",
        extractor_kind="python_ast",
    )

    return {
        "unit_id": uid,
        "kind": kind,
        "repo": repo,
        "file_path": file_path,
        "symbol": symbol,
        "qualified_name": qualified,
        "language": "python",
        "span": span,
        "file_hash": file_hash,
        "snippet_hash": snippet_hash,
        "imports": _used_imports(node, alias_map),
        "exports": [],
        "call_candidates": call_candidates,
        "related_candidates": related,
        "complexity": complexity,
        "state": vocab.STATUS_VERIFIED,
        "confidence": vocab.CONFIDENCE_HIGH,
        "evidence": [unit_evidence],
    }


# --- helpers -----------------------------------------------------------------
def _span_lines(node: ast.AST) -> tuple[int, int]:
    start = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", []) or []
    if decorators:
        start = min(start, min(d.lineno for d in decorators))
    end = getattr(node, "end_lineno", start) or start
    return start, end


def _build_alias_map(tree: ast.AST) -> dict[str, str]:
    """Map a bound name -> the module it refers to, for module-level imports."""
    alias_map: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                alias_map[bound] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                bound = alias.asname or alias.name
                alias_map[bound] = module or alias.name
    return alias_map


def _used_imports(node: ast.AST, alias_map: dict[str, str]) -> list[str]:
    used: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in alias_map:
            used.add(alias_map[child.id])
        elif isinstance(child, ast.Attribute):
            root = child
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in alias_map:
                used.add(alias_map[root.id])
    return sorted(used)


def _call_candidates(node: ast.AST) -> list[dict[str, Any]]:
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        try:
            target = ast.unparse(child.func)
        except Exception:  # pragma: no cover - defensive
            continue
        line = getattr(child.func, "lineno", getattr(child, "lineno", 0))
        key = (target, line)
        if key in seen:
            continue
        seen[key] = {
            "target_text": target,
            "span": evidence_mod.make_span(line, line),
            "confidence": vocab.CONFIDENCE_MEDIUM,
            "state": vocab.STATUS_INFERRED,
        }
    return list(seen.values())


def _complexity(node: ast.AST, start: int, end: int, call_count: int) -> dict[str, Any]:
    branch_types = (
        ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler,
        ast.With, ast.AsyncWith, ast.BoolOp, ast.IfExp, ast.comprehension, ast.Assert,
    )
    branch_count = sum(1 for c in ast.walk(node) if isinstance(c, branch_types))
    line_count = end - start + 1
    if line_count > 80 or branch_count > 15 or call_count > 30:
        state = vocab.COMPLEXITY_COMPLEX
    elif line_count <= 20 and branch_count <= 3:
        state = vocab.COMPLEXITY_SIMPLE
    else:
        state = vocab.COMPLEXITY_MODERATE
    return {
        "line_count": line_count,
        "branch_count": branch_count,
        "call_count": call_count,
        "state": state,
    }


def _detect_endpoint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any] | None:
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if isinstance(func, ast.Attribute) and func.attr in _HTTP_METHODS:
            path = ""
            if dec.args and isinstance(dec.args[0], ast.Constant):
                value = dec.args[0].value
                if isinstance(value, str):
                    path = value
            return {
                "method": func.attr.upper(),
                "path": path,
                "confidence": vocab.CONFIDENCE_MEDIUM,
                "state": vocab.STATUS_INFERRED,
            }
    return None


def _is_pydantic(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name == "BaseModel" or name.endswith("BaseModel"):
            return True
    return False
