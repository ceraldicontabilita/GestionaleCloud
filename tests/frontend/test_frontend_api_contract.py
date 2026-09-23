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
from fastapi.routing import APIRoute

from app.router_registry import register_all_routers


def _tutte_le_route(app):
    """Endpoint con il percorso FINALE, su ogni versione di FastAPI.

    Fino alla 0.120 ``include_router`` appiattiva tutto in ``app.routes`` come
    APIRoute gia' prefissate. Dalla 0.121 inserisce un ``_IncludedRouter`` e le
    rotte restano annidate: cercare solo le APIRoute di primo livello ne trova
    ZERO, e questo test passerebbe a vuoto senza sollevare errori.

    I contesti del router incluso portano il percorso gia' prefissato, quindi
    non vanno ricomposti a mano (le rotte originali hanno il path SENZA
    prefisso: usarle produrrebbe un confronto su percorsi inesistenti).
    """
    trovate = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            trovate.append(r)
            continue
        contesti = getattr(r, "effective_route_contexts", None)
        if callable(contesti):
            trovate.extend(contesti())
    return trovate


ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src"
CALL = re.compile(
    r"\bapi\.(get|post|put|delete|patch)\(\s*([`\"'])"
    r"(?P<path>/api/[^`\"']*)\2",
    re.IGNORECASE,
)


# Qualunque chiamata del client con un percorso letterale assoluto. Il client
# ha ``baseURL: ''``: un percorso che non comincia con /api finisce nella SPA
# (405 sui POST, pagina HTML sui GET) e il regex ``CALL`` qui sopra non lo
# vedeva nemmeno, perche' pretendeva gia' il prefisso.
QUALSIASI = re.compile(
    r"\bapi\.(get|post|put|delete|patch)\(\s*([`\"'])(?P<path>/[^`\"']*)\2",
    re.IGNORECASE,
)

# I lavori del pannello Riparazioni sono URL in una tabella, non chiamate
# letterali: stesso controllo, letto dalla tabella.
RIPARAZIONI = ROOT / "components" / "PannelloRiparazioni.jsx"
VOCE_RIPARAZIONE = re.compile(r"\b(esegui|stato):\s*'(?P<path>/[^']*)'")


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


def _route_montate():
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
    return routes


def test_nessuna_chiamata_del_client_fuori_da_api():
    fuori = []
    for path in ROOT.rglob("*.*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"} or ".test." in path.name:
            continue
        for match in QUALSIASI.finditer(path.read_text(encoding="utf-8")):
            if not match.group("path").startswith("/api/"):
                fuori.append(f"{path.relative_to(ROOT)}: {match.group(1).upper()} {match.group('path')}")
    assert not fuori, "Chiamate senza prefisso /api (finiscono nella SPA):\n" + "\n".join(fuori)


def test_riparazioni_puntano_a_route_montate():
    routes = _route_montate()
    voci = [(m.group(1), m.group("path")) for m in VOCE_RIPARAZIONE.finditer(RIPARAZIONI.read_text(encoding="utf-8"))]
    assert voci, "Nessun lavoro letto dal pannello Riparazioni: regex da aggiornare"
    mancanti = []
    for chiave, path in voci:
        metodo = "POST" if chiave == "esegui" else "GET"
        normalizzato = _normalizza(path)
        if not any(metodo == m and _route_match(normalizzato, e) for m, e in routes):
            mancanti.append(f"{metodo} {path}")
    assert not mancanti, "Riparazioni senza route montata:\n" + "\n".join(mancanti)


def test_ogni_chiamata_frontend_literalmente_risolta_ha_route_backend():
    routes = _route_montate()

    mancanti = []
    for source, method, path in _calls_frontend():
        if path == "/api/ws/notifications":  # WebSocket, non Axios/HTTP.
            continue
        if not any(method == m and _route_match(path, endpoint) for m, endpoint in routes):
            mancanti.append(f"{source}: {method} {path}")

    assert not mancanti, "Chiamate frontend senza route montata:\n" + "\n".join(mancanti)
