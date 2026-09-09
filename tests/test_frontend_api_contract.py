"""Contratto minimo tra bottoni/pagine React e route FastAPI montate.

Un pulsante che invoca un URL non montato restituisce un 404 solo dopo che
l'operatore ha compilato un modulo. Questo test intercetta le chiamate Axios
letterali del frontend (escluse le fixture dei test), normalizza parametri e
query dinamiche e pretende almeno una route backend con stesso metodo/path.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI

from app.router_registry import register_all_routers
from scripts.genera_mappa import _tutte_le_route


ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
CALL = re.compile(
    r"\bapi\.(get|post|put|delete|patch)\(\s*([`\"'])"
    r"(?P<path>/api/[^`\"']*)\2",
    re.IGNORECASE,
)


def _normalizza(path: str) -> str | None:
    """Riduce URL template a segmenti senza perdere la forma della route."""
    path = path.split("?", 1)[0]
    # Un template lasciato a meta (es. ternario non risolvibile staticamente)
    # non e' una prova di URL: va coperto dal test dedicato del componente.
    if "${" in path and "}" not in path:
        return None
    path = re.sub(r"\$\{(?:encodeURIComponent\()?[^}]+\}?\)?", ":x", path)
    # Le query opzionali sono spesso interpolate senza il '?' letterale
    # (``/endpoint${params}``): dopo la sostituzione rimane un suffisso :x
    # che non appartiene al path.
    path = re.sub(r"(?<!/):x$", "", path)
    path = re.sub(r"\{[^}]+\}", ":x", path)
    path = re.sub(r"/\d+(?=/|$)", "/:x", path)
    return path.rstrip("/") or "/"


def _route_match(frontend_path: str, backend_path: str) -> bool:
    front = frontend_path.strip("/").split("/")
    back = backend_path.rstrip("/").strip("/").split("/")
    if len(front) != len(back):
        return False
    return all(
        f == ":x" or b.startswith("{") and b.endswith("}") or f == b
        for f, b in zip(front, back)
    )


def _calls_frontend():
    for path in ROOT.rglob("*.*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"} or ".test." in path.name:
            continue
        source = path.read_text(encoding="utf-8")
        for match in CALL.finditer(source):
            normalized = _normalizza(match.group("path"))
            if normalized:
                yield path.relative_to(ROOT), match.group(1).upper(), normalized


def test_ogni_chiamata_frontend_literalmente_risolta_ha_route_backend():
    app = FastAPI()
    register_all_routers(app)
    routes = [
        (method, route.path)
        for route in _tutte_le_route(app)
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    ]
    # Sono montate direttamente dall'app principale, non dal router registry.
    routes.append(("GET", "/api/health"))

    mancanti = []
    for source, method, path in _calls_frontend():
        if path == "/api/ws/notifications":  # WebSocket, non Axios/HTTP.
            continue
        if not any(method == m and _route_match(path, endpoint) for m, endpoint in routes):
            mancanti.append(f"{source}: {method} {path}")

    assert not mancanti, "Chiamate frontend senza route montata:\n" + "\n".join(mancanti)
