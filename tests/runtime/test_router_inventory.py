"""Inventario strutturale dei router FastAPI.

RST-0007: ogni modulo che dichiara operazioni HTTP/WebSocket su un APIRouter
deve essere raggiungibile dalla app root (direttamente o attraverso HR/Lotti/Menu).
I moduli contenitore che si limitano a include_router sono coperti dal normale
grafo import e dal test dei moduli orfani.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute, APIWebSocketRoute

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"

_PATH_DECORATORS = {
    "get", "post", "put", "patch", "delete", "options", "head",
    "trace", "websocket",
}
_ROUTE_BUILDERS = {"add_api_route", "add_api_websocket_route"}


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _router_modules_with_operations() -> set[str]:
    modules: set[str] = set()
    for path in APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        declares_router = False
        declares_operation = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute)
                    else ""
                )
                if name == "APIRouter":
                    declares_router = True
                if name in _ROUTE_BUILDERS:
                    declares_operation = True

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    call = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if (
                        isinstance(call, ast.Attribute)
                        and call.attr in _PATH_DECORATORS
                    ):
                        declares_operation = True

        if declares_router and declares_operation:
            modules.add(_module_name(path))
    return modules


def _reachable_endpoint_ids() -> set[int]:
    # Importare l'app non esegue il lifespan: nessuna connessione DB o job parte.
    from app.main import app

    endpoints: set[int] = set()
    visited: set[int] = set()

    def walk(router_app) -> None:
        ident = id(router_app)
        if ident in visited:
            return
        visited.add(ident)

        for route in getattr(router_app, "routes", ()):
            if isinstance(route, (APIRoute, APIWebSocketRoute)):
                endpoint = getattr(route, "endpoint", None)
                if endpoint is not None:
                    endpoints.add(id(endpoint))
            child = getattr(route, "app", None)
            if child is not None and child is not router_app and hasattr(child, "routes"):
                walk(child)

    walk(app)
    return endpoints


def _mounted_router_modules(candidates: set[str]) -> set[str]:
    reachable = _reachable_endpoint_ids()
    mounted: set[str] = set()

    # app.main ha già importato tutti i router effettivamente registrati.
    # Non importiamo moduli ulteriori solo per censirli, evitando side effect.
    for module_name in candidates:
        module = sys.modules.get(module_name)
        if module is None:
            continue

        endpoint_ids: set[int] = set()
        for value in vars(module).values():
            if not isinstance(value, APIRouter):
                continue
            endpoint_ids.update(
                id(route.endpoint)
                for route in getattr(value, "routes", ())
                if isinstance(route, (APIRoute, APIWebSocketRoute))
                and getattr(route, "endpoint", None) is not None
            )

        if endpoint_ids & reachable:
            mounted.add(module_name)

    return mounted


def test_router_con_operazioni_sono_raggiungibili_dalla_app_pubblicata() -> None:
    dichiarati = _router_modules_with_operations()
    montati = _mounted_router_modules(dichiarati)
    non_montati = sorted(dichiarati - montati)

    assert not non_montati, (
        "Moduli APIRouter con operazioni ma non raggiungibili dalla app root "
        "(diretta o tramite HR/Lotti/Menu). Se il modulo e' morto, eliminarlo; "
        "se e' vivo, montarlo esplicitamente.\n- "
        + "\n- ".join(non_montati)
    )
