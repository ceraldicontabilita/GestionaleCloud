"""Audit statico ripetibile dell'architettura FastAPI/Drive/Sheets.

Non modifica codice o dati. Produce metriche oggettive utili a impedire che
la revisione architetturale diventi una valutazione soggettiva.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
ROUTERS = APP / "routers"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
LARGE_LIST_RE = re.compile(r"\.to_list\((?:10000|20000|50000|100000)\)")
HARD_DELETE_RE = re.compile(r"\.(?:delete_one|delete_many)\(")
SILENT_EXCEPT_RE = re.compile(
    r"except\s+Exception(?:\s+as\s+\w+)?\s*:\s*(?:#.*\n\s*)?pass\b",
    re.MULTILINE,
)


def _route_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef):
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
            yield func.attr, decorator


def collect() -> dict[str, Any]:
    python_files = sorted(APP.rglob("*.py"))
    router_files = sorted(ROUTERS.rglob("*.py"))
    routes: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    large_queries: list[str] = []
    hard_deletes: list[str] = []
    silent_exceptions: list[str] = []
    large_modules: list[dict[str, Any]] = []

    for path in python_files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        lines = text.splitlines()
        if len(lines) >= 1000:
            large_modules.append({"file": rel, "lines": len(lines)})
        for number, line in enumerate(lines, 1):
            if LARGE_LIST_RE.search(line):
                large_queries.append(f"{rel}:{number}")
            if HARD_DELETE_RE.search(line):
                hard_deletes.append(f"{rel}:{number}")
        for match in SILENT_EXCEPT_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            silent_exceptions.append(f"{rel}:{line}")

    for path in router_files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            parse_errors.append(f"{rel}:{exc.lineno}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for method, decorator in _route_decorators(node):
                keywords = {kw.arg for kw in decorator.keywords if kw.arg}
                route_path = None
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    route_path = decorator.args[0].value
                routes.append({
                    "file": rel,
                    "line": node.lineno,
                    "function": node.name,
                    "method": method.upper(),
                    "path": route_path,
                    "response_model": "response_model" in keywords,
                    "status_code": "status_code" in keywords,
                })

    mutation_routes = [r for r in routes if r["method"] in {"POST", "PUT", "PATCH", "DELETE"}]
    return {
        "python_files": len(python_files),
        "router_files": len(router_files),
        "routes": len(routes),
        "mutation_routes": len(mutation_routes),
        "routes_without_response_model": sum(not r["response_model"] for r in routes),
        "mutation_routes_without_explicit_status": sum(not r["status_code"] for r in mutation_routes),
        "hard_delete_calls": len(hard_deletes),
        "large_to_list_calls": len(large_queries),
        "silent_exception_handlers": len(silent_exceptions),
        "large_modules": sorted(large_modules, key=lambda x: x["lines"], reverse=True),
        "parse_errors": parse_errors,
        "evidence": {
            "hard_delete_calls": hard_deletes,
            "large_to_list_calls": large_queries,
            "silent_exception_handlers": silent_exceptions,
        },
    }


def as_markdown(report: dict[str, Any]) -> str:
    rows = [
        ("File Python", report["python_files"]),
        ("File router", report["router_files"]),
        ("Route HTTP", report["routes"]),
        ("Route mutative", report["mutation_routes"]),
        ("Route senza response_model", report["routes_without_response_model"]),
        ("Mutazioni senza status esplicito", report["mutation_routes_without_explicit_status"]),
        ("Hard delete diretti", report["hard_delete_calls"]),
        ("Query to_list >= 10.000", report["large_to_list_calls"]),
        ("except Exception: pass", report["silent_exception_handlers"]),
    ]
    out = ["# Audit statico architettura", "", "| Metrica | Valore |", "|---|---:|"]
    out.extend(f"| {name} | {value} |" for name, value in rows)
    out.extend(["", "## Moduli oltre 1.000 righe", "", "| File | Righe |", "|---|---:|"])
    out.extend(f"| `{item['file']}` | {item['lines']} |" for item in report["large_modules"])
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    report = collect()
    print(as_markdown(report) if args.markdown else json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
