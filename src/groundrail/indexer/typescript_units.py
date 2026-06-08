"""Best-effort TypeScript/React unit extraction (no external parser).

Finds top-level declarations and relationship candidates useful for React -> API
-> backend impact analysis. Regex-derived frontend facts are always inferred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..core import evidence as evidence_mod
from ..core import hashing, ids, vocab
from .ts_mask import LineMap, mask_source, match_delimiter, statement_end

_P_FUNC = re.compile(r"\b(?P<export>export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>[A-Za-z_$][\w$]*)\s*(?:<[^>{(]*>)?\s*\(")
_P_CLASS = re.compile(r"\b(?P<export>export\s+)?(?:default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)")
_P_CONST = re.compile(r"\b(?P<export>export\s+)?(?:default\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::\s*[^=;]+?)?=\s*")
_P_IMPORT = re.compile(r"\bimport\b([^;]*?)\bfrom\b\s*['\"]([^'\"]+)['\"]", re.S)
_KEYWORD_CALLS = {"if", "for", "while", "switch", "catch", "return", "function", "await", "typeof"}
_CALL_RE = re.compile(r"(?P<name>[A-Za-z_$][\w$.]*)\s*\(")
_JSX_RE = re.compile(r"</[A-Za-z]|<[A-Za-z][\w.]*(?:\s+[\w-]+=|\s*/?>)")
_HTTP_RE = re.compile(r"\b(?:fetch|axios)\b|\.(?:get|post|put|delete|patch)\s*\(")
_URL_RE = re.compile(r"['\"](?P<url>/(?:api/)?[A-Za-z0-9_./{}:-]+)(?:\?[^'\"]*)?['\"]")
_ROUTE_RE = re.compile(r"\b(?:path|to)\s*=\s*['\"](?P<path>/[A-Za-z0-9_./:{}-]*)['\"]")
_QUERY_KEY_RE = re.compile(r"\b(?:useQuery|useMutation|queryKey)\s*\([^\n;]*?(?P<key>\[[^\]]+\]|['\"][^'\"]+['\"])", re.S)


@dataclass
class ExtractResult:
    units: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)


def extract_file(*, repo: str, file_path: str, source_text: str, source_commit: str) -> ExtractResult:
    result = ExtractResult()
    masked = mask_source(source_text)
    lines = source_text.splitlines()
    line_map = LineMap(source_text)
    file_hash = hashing.sha256_text(source_text)
    is_tsx = file_path.endswith((".tsx", ".jsx"))
    import_map = _build_import_map(source_text)
    claimed: list[tuple[int, int]] = []
    for cand in sorted(_find_candidates(masked), key=lambda c: c["start"]):
        if any(lo <= cand["start"] < hi for lo, hi in claimed):
            continue
        body = _resolve_body(masked, cand)
        if body is None:
            continue
        _start, body_end = body
        claimed.append((cand["start"], body_end))
        result.units.append(_build_unit(cand=cand, body_span=(cand["start"], body_end), masked=masked, source_text=source_text, lines=lines, line_map=line_map, repo=repo, file_path=file_path, file_hash=file_hash, source_commit=source_commit, import_map=import_map, is_tsx=is_tsx))
    result.gaps.extend(_dynamic_pattern_gaps(masked, source_text, repo, file_path, line_map))
    return result


def _find_candidates(masked: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _P_FUNC.finditer(masked): out.append({"start": m.start(), "name": m.group("name"), "decl": "function", "params_open": m.end() - 1, "exported": bool(m.group("export"))})
    for m in _P_CLASS.finditer(masked): out.append({"start": m.start(), "name": m.group("name"), "decl": "class", "after": m.end(), "exported": bool(m.group("export"))})
    for m in _P_CONST.finditer(masked): out.append({"start": m.start(), "name": m.group("name"), "decl": "const", "after": m.end(), "exported": bool(m.group("export"))})
    return out


def _resolve_body(masked: str, cand: dict[str, Any]) -> tuple[int, int] | None:
    if cand["decl"] == "function":
        close = match_delimiter(masked, cand["params_open"], "(", ")")
        if close == -1: return None
        brace = masked.find("{", close)
        if brace == -1: return None
        end = match_delimiter(masked, brace, "{", "}")
        return (brace, end) if end != -1 else None
    if cand["decl"] == "class":
        brace = masked.find("{", cand["after"])
        if brace == -1: return None
        end = match_delimiter(masked, brace, "{", "}")
        return (brace, end) if end != -1 else None
    return _resolve_const_body(masked, cand["after"])


def _resolve_const_body(masked: str, after: int) -> tuple[int, int] | None:
    stmt_end = statement_end(masked, after); head = masked[after:stmt_end]
    if "function" in head:
        brace = masked.find("{", after)
        if brace != -1 and brace < stmt_end + 1:
            end = match_delimiter(masked, brace, "{", "}")
            return (brace, end) if end != -1 else None
        return None
    arrow = masked.find("=>", after)
    if arrow == -1: return None
    j = arrow + 2
    while j < len(masked) and masked[j] in " \t\r\n": j += 1
    if j >= len(masked): return None
    if masked[j] == "{":
        end = match_delimiter(masked, j, "{", "}")
        return (j, end) if end != -1 else None
    if masked[j] == "(":
        end = match_delimiter(masked, j, "(", ")")
        return (j, end) if end != -1 else None
    return (arrow, statement_end(masked, arrow))


def _build_unit(*, cand: dict[str, Any], body_span: tuple[int, int], masked: str, source_text: str, lines: list[str], line_map: LineMap, repo: str, file_path: str, file_hash: str, source_commit: str, import_map: dict[str, str], is_tsx: bool) -> dict[str, Any]:
    start_off, end_off = body_span
    start_line = line_map.line_of(start_off); end_line = line_map.line_of(end_off)
    snippet = "\n".join(lines[start_line - 1 : end_line]); snippet_hash = hashing.sha256_text(snippet)
    span = evidence_mod.make_span(start_line, end_line); name = cand["name"]
    body_masked = masked[start_off:end_off]; body_source = source_text[start_off:end_off]
    kind = _classify(name, body_masked, is_tsx); uid = ids.unit_id(repo, file_path, name)
    call_candidates = _call_candidates(body_masked, start_off, line_map); complexity = _complexity(body_masked, start_line, end_line, len(call_candidates))
    unit_evidence = evidence_mod.build_evidence(evidence_id=ids.evidence_id(uid, "unit_span"), evidence_kind="unit_span", repo=repo, file_path=file_path, source_commit=source_commit, file_hash=file_hash, span=span, snippet_hash=snippet_hash, extractor_id="groundrail.typescript.units", extractor_kind="typescript_regex")
    return {"unit_id": uid, "kind": kind, "repo": repo, "file_path": file_path, "symbol": name, "qualified_name": name, "language": "typescript", "span": span, "file_hash": file_hash, "snippet_hash": snippet_hash, "imports": _used_imports(body_masked, import_map), "exports": [name] if cand["exported"] else [], "call_candidates": call_candidates, "related_candidates": _related_candidates(body_source, start_off, line_map, kind), "complexity": complexity, "state": vocab.STATUS_INFERRED, "confidence": vocab.CONFIDENCE_MEDIUM, "evidence": [unit_evidence]}


def _classify(name: str, body_masked: str, is_tsx: bool) -> str:
    if re.match(r"use[A-Z0-9]", name): return "react_hook"
    has_jsx = bool(_JSX_RE.search(body_masked))
    if name[:1].isupper() and (has_jsx or is_tsx): return "react_component"
    if not has_jsx and _HTTP_RE.search(body_masked): return "api_client_function"
    return "typescript_function"


def _related_candidates(body_source: str, base_off: int, line_map: LineMap, kind: str) -> dict[str, Any]:
    api_calls = []
    for m in _URL_RE.finditer(body_source):
        raw = m.group("url")
        path = "/" + raw.removeprefix("/").removeprefix("api/")
        api_calls.append({"method": _method_near(body_source, m.start()), "path": path, "raw_path": raw, "span": evidence_mod.make_span(line_map.line_of(base_off + m.start()), line_map.line_of(base_off + m.start())), "state": vocab.STATUS_INFERRED, "confidence": vocab.CONFIDENCE_LOW})
    routes = [{"path": m.group("path"), "span": evidence_mod.make_span(line_map.line_of(base_off + m.start()), line_map.line_of(base_off + m.start())), "state": vocab.STATUS_INFERRED, "confidence": vocab.CONFIDENCE_LOW} for m in _ROUTE_RE.finditer(body_source)]
    queries = [{"key": re.sub(r"\s+", " ", m.group("key")).strip(), "span": evidence_mod.make_span(line_map.line_of(base_off + m.start()), line_map.line_of(base_off + m.start())), "state": vocab.STATUS_INFERRED, "confidence": vocab.CONFIDENCE_LOW} for m in _QUERY_KEY_RE.finditer(body_source)]
    return {"endpoint_candidates": [], "test_candidates": [], "api_call_candidates": api_calls, "route_candidates": routes, "query_candidates": queries, "opensearch_candidates": []}


def _method_near(text: str, pos: int) -> str:
    window = text[max(0, pos - 80): pos + 80].lower()
    for method in ("post", "put", "delete", "patch", "get"):
        if f".{method}" in window or f"method: '{method}'" in window or f'method: "{method}"' in window:
            return method.upper()
    return "GET"


def _call_candidates(body_masked: str, base_off: int, line_map: LineMap) -> list[dict[str, Any]]:
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for m in _CALL_RE.finditer(body_masked):
        name = m.group("name"); root = name.split(".")[0]
        if root in _KEYWORD_CALLS or not root: continue
        line = line_map.line_of(base_off + m.start()); key = (name, line)
        if key in seen: continue
        seen[key] = {"target_text": name, "span": evidence_mod.make_span(line, line), "confidence": vocab.CONFIDENCE_LOW, "state": vocab.STATUS_INFERRED}
    return list(seen.values())


def _complexity(body_masked: str, start_line: int, end_line: int, call_count: int) -> dict[str, Any]:
    branch_count = len(re.findall(r"\b(?:if|for|while|switch|catch)\b", body_masked)) + body_masked.count("&&") + body_masked.count("||") + body_masked.count("?")
    line_count = end_line - start_line + 1
    state = vocab.COMPLEXITY_COMPLEX if line_count > 80 or branch_count > 15 or call_count > 30 else vocab.COMPLEXITY_SIMPLE if line_count <= 20 and branch_count <= 3 else vocab.COMPLEXITY_MODERATE
    return {"line_count": line_count, "branch_count": branch_count, "call_count": call_count, "state": state}


def _build_import_map(source: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for clause, module in _P_IMPORT.findall(source):
        clause = clause.strip(); ns = re.search(r"\*\s+as\s+([A-Za-z_$][\w$]*)", clause)
        if ns: mapping[ns.group(1)] = module
        braces = re.search(r"\{([^}]*)\}", clause)
        if braces:
            for part in braces.group(1).split(","):
                part = part.strip()
                if part: mapping[part.split(" as ")[-1].strip()] = module
        default = re.match(r"([A-Za-z_$][\w$]*)", clause)
        if default and "{" not in clause[: default.end()]: mapping[default.group(1)] = module
    return mapping


def _used_imports(body_masked: str, import_map: dict[str, str]) -> list[str]:
    return sorted({import_map[token] for token in re.findall(r"[A-Za-z_$][\w$]*", body_masked) if token in import_map})


def _dynamic_pattern_gaps(masked: str, source: str, repo: str, file_path: str, line_map: LineMap) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    checks = ((re.compile(r"\bReact\.lazy\s*\("), "react_lazy", "React.lazy dynamic component not bounded"), (re.compile(r"(?<![\w.$])import\s*\("), "dynamic_import", "dynamic import() not resolved"), (re.compile(r"\bexport\s+default\s+[A-Za-z_$][\w$]*\s*\("), "hoc_default_export", "default export wraps a call (likely HOC); component boundary uncertain"))
    seen: set[tuple[str, int]] = set()
    for pattern, kind, detail in checks:
        for m in pattern.finditer(masked):
            line = line_map.line_of(m.start())
            if (kind, line) in seen: continue
            seen.add((kind, line)); gaps.append({"kind": kind, "repo": repo, "location": f"{file_path}:{line}", "detail": detail, "severity": "info", "state": "unsupported"})
    return gaps
