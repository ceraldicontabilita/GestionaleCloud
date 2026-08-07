"""Guardia statica sui contratti API usati direttamente dal frontend.

L'E2E di apertura esercita solo le chiamate iniziali. Questo test copre anche
azioni e pulsanti che usano URL statici, impedendo di lasciare nel bundle una
chiamata verso un endpoint non montato. Gli URL con segmenti dinamici sono
verificati dai test specifici delle rispettive pagine.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI

from app.router_registry import register_all_routers
from tests.route_table import elenco_route


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _route_backend_statiche() -> set[str]:
    app = FastAPI()
    register_all_routers(app)
    routes = {route.path.rstrip("/") for route in elenco_route(app)}
    # Registrata direttamente in app/main.py, fuori dal router registry.
    routes.add("/api/health")
    return routes


def _url_api_statici_frontend() -> list[tuple[Path, str]]:
    riferimenti: list[tuple[Path, str]] = []
    for file in FRONTEND.rglob("*"):
        if file.suffix not in {".js", ".jsx", ".ts", ".tsx"} or ".test." in file.name:
            continue
        source = file.read_text(encoding="utf-8", errors="ignore")
        for raw in re.findall(r"['\"`](/api/[^'\"`\s]+)['\"`]", source):
            if "$" in raw:
                continue
            riferimenti.append((file, raw.split("?", 1)[0].rstrip("/")))
    return riferimenti


def test_url_api_statici_frontend_sono_montati_nel_backend():
    routes = _route_backend_statiche()
    mancanti = [
        f"{file.relative_to(ROOT)} -> {url}"
        for file, url in _url_api_statici_frontend()
        if url not in routes
    ]
    assert not mancanti, "Endpoint frontend non montati:\n" + "\n".join(sorted(mancanti))
