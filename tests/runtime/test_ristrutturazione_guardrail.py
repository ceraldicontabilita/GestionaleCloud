"""Guardrail permanenti della ristrutturazione.

Questi test non descrivono il passato: impediscono che durante la bonifica
rientrino route duplicate, nuove sotto-app FastAPI o scritture ERP sulle
vecchie collezioni di giacenza.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.router_registry import register_all_routers

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def _routes(app: FastAPI):
    trovate = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            trovate.append(route)
            continue
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            trovate.extend(contexts())
    return trovate


def _forma_path(path: str) -> str:
    """Normalizza solo i nomi dei parametri, non slash o path statici."""
    return re.sub(r"\{[^}/]+\}", "{param}", path)


def test_nessuna_route_fastapi_duplicata_stesso_metodo_e_forma():
    app = FastAPI()
    register_all_routers(app)

    viste = defaultdict(list)
    for route in _routes(app):
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            viste[(method, _forma_path(route.path))].append(
                f"{route.path} -> {getattr(route, 'name', '?')}"
            )

    duplicate = {
        chiave: valori for chiave, valori in viste.items() if len(valori) > 1
    }
    assert not duplicate, (
        "Route FastAPI duplicate per metodo+forma. Una route dinamica con un "
        "nome parametro diverso e' comunque lo stesso endpoint:\n"
        + "\n".join(
            f"{method} {path}: " + " | ".join(valori)
            for (method, path), valori in sorted(duplicate.items())
        )
    )


# Fase transitoria: queste sono le tre sotto-app gia' esistenti che il piano
# deve eliminare. Il test impedisce di crearne una quarta nel frattempo.
FASTAPI_SECONDARIE_AMMESSE_TEMPORANEAMENTE = {
    "app/hr/main.py",
    "app/lotti/server.py",
    "app/menu/server.py",
}


def test_nessuna_nuova_istanza_fastapi_fuori_dal_main():
    offenders = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "app/main.py" or rel in FASTAPI_SECONDARIE_AMMESSE_TEMPORANEAMENTE:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            nome = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else ""
            )
            if nome == "FastAPI":
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "Nuove applicazioni FastAPI separate vietate: " + ", ".join(offenders)
    )


GIACENZA_ERP_NO_WRITE = {
    "warehouse_stocks",
    "warehouse_products",
    "magazzino",
    "magazzino_articoli",
    "magazzino_movimenti",
    "movimenti_magazzino",
}

# Durante la fusione il nuovo inventario canonico e' warehouse_inventory.
# I writer storici ammessi sono espliciti e devono diminuire, mai aumentare.
WAREHOUSE_INVENTORY_WRITERS_TEMPORANEI = {
    "app/services/handlers/magazzino_handlers.py",
    "app/routers/fornitori_learning.py",
}

COSTANTI_GIACENZA_NO_WRITE = {
    "WAREHOUSE_PRODUCTS",
    "WAREHOUSE_MOVEMENTS",
    "RIMANENZE",
}

WRITE_METHODS = {
    "insert_one", "insert_many", "update_one", "update_many",
    "replace_one", "bulk_write",
}


def _subscript_name(node: ast.AST) -> tuple[str | None, str | None]:
    """Ritorna (stringa_collection, costante_Collections) se riconoscibile."""
    if not isinstance(node, ast.Subscript):
        return None, None
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value, None
    if isinstance(sl, ast.Attribute) and isinstance(sl.value, ast.Name):
        if sl.value.id == "Collections":
            return None, sl.attr
    return None, None


def test_erp_non_scrive_sulle_collezioni_giacenza_legacy_neanche_via_alias():
    offenders = []
    # Lotti e Menu sono ancora proprietari temporanei del proprio dominio
    # operativo fino alle fasi di fusione. Il divieto qui riguarda il core ERP.
    for path in APP.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("app/lotti/", "app/menu/")):
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in WRITE_METHODS:
                continue
            coll, costante = _subscript_name(node.func.value)
            vecchia_giacenza = (
                coll in GIACENZA_ERP_NO_WRITE
                or costante in COSTANTI_GIACENZA_NO_WRITE
            )
            inventario_canonico_fuori_writer = (
                coll == "warehouse_inventory"
                and rel not in WAREHOUSE_INVENTORY_WRITERS_TEMPORANEI
            )
            if vecchia_giacenza or inventario_canonico_fuori_writer:
                bersaglio = coll or f"Collections.{costante}"
                offenders.append(
                    f"{rel}:{node.lineno} -> {bersaglio}.{node.func.attr}"
                )
    assert not offenders, (
        "Scritture ERP vietate sulla vecchia giacenza o fuori dai writer "
        "canonici transitori di warehouse_inventory:\n" + "\n".join(offenders)
    )


def test_public_api_storico_non_puo_ritornare():
    assert not (APP / "routers" / "public_api.py").exists(), (
        "public_api.py e' stato eliminato: non ricreare un router contenitore storico"
    )


def test_endpoint_estratti_hanno_owner_canonico():
    app = FastAPI()
    register_all_routers(app)
    per_chiave = {}
    for route in _routes(app):
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            per_chiave[(method, route.path)] = route

    attesi = {
        ("GET", "/api/pianificazione/events"): "app.routers.pianificazione",
        ("POST", "/api/pianificazione/events"): "app.routers.pianificazione",
        ("GET", "/api/ricerca-globale"): "app.routers.ricerca_globale",
        ("GET", "/api/v1/fatture"): "app.routers.external_api_v1",
        ("GET", "/api/v1/movimenti"): "app.routers.external_api_v1",
        ("GET", "/api/v1/stats"): "app.routers.external_api_v1",
    }
    errori = []
    for chiave, modulo in attesi.items():
        route = per_chiave.get(chiave)
        if route is None:
            errori.append(f"manca {chiave[0]} {chiave[1]}")
            continue
        reale = getattr(route.endpoint, "__module__", "")
        if reale != modulo:
            errori.append(
                f"{chiave[0]} {chiave[1]} owner={reale}, atteso={modulo}"
            )
    assert not errori, "Endpoint senza owner canonico:\n" + "\n".join(errori)


def test_nessun_import_runtime_del_vecchio_public_api():
    offenders = []
    for path in APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "app.routers.public_api" in source or "from app.routers import public_api" in source:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "Il router public_api e' stato eliminato ma esistono ancora import runtime: "
        + ", ".join(offenders)
    )


FILE_MORTI_ELIMINATI = {
    "app/routers/reports/report_pdf.py",
    "app/routers/reports/simple_exports.py",
    "app/routers/batch_operations.py",
    "app/routers/distinte_bpm.py",
    "app/routers/libro_unico_parser.py",
}


def test_codice_morto_eliminato_non_ritorna():
    presenti = [p for p in sorted(FILE_MORTI_ELIMINATI) if (ROOT / p).exists()]
    assert not presenti, (
        "File morti gia' eliminati sono ricomparsi: " + ", ".join(presenti)
    )


def test_importatori_documentali_non_sono_router_http():
    for path in (
        ROOT / "app/services/distinte_bpm.py",
        ROOT / "app/services/libro_unico_parser.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "APIRouter" not in source
        assert "@router." not in source


# Connessioni autonome ancora presenti prima della fusione ERP+HR+Lotti+Menu.
# Questa lista puo' soltanto accorciarsi: un nuovo costruttore DB fa fallire la CI;
# quando un file viene unificato, la relativa voce va rimossa.
CLIENT_DB_LEGACY_TEMPORANEI = {
    ("app/hr/database.py", "AsyncIOMotorClient"),
    ("app/hr/db_supabase.py", "asyncpg.create_pool"),
    ("app/hr/config.py", "MongoClient"),
    ("app/menu/supabase_client.py", "create_client"),
    ("app/lotti/db.py", "AsyncMongoMockClient"),
    ("app/lotti/supabase_document_store.py", "AsyncMongoMockClient"),
}


def _costruttori_db_autonomi() -> set[tuple[str, str]]:
    trovati: set[tuple[str, str]] = set()
    semplici = {
        "AsyncIOMotorClient",
        "MongoClient",
        "create_client",
        "AsyncMongoMockClient",
    }
    for path in APP.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in semplici:
                trovati.add((rel, func.id))
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "create_pool"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncpg"
            ):
                trovati.add((rel, "asyncpg.create_pool"))
    return trovati


def test_nessun_nuovo_client_database_autonomo():
    trovati = _costruttori_db_autonomi()
    nuovi = sorted(trovati - CLIENT_DB_LEGACY_TEMPORANEI)
    assert not nuovi, (
        "Nuovi client/database autonomi vietati durante la fusione: "
        + ", ".join(f"{p}:{c}" for p, c in nuovi)
    )


def test_whitelist_client_db_puo_solo_accorciarsi():
    trovati = _costruttori_db_autonomi()
    rimossi = sorted(CLIENT_DB_LEGACY_TEMPORANEI - trovati)
    assert not rimossi, (
        "Questi client legacy non esistono piu': toglierli dalla whitelist "
        "per mantenerla stretta: "
        + ", ".join(f"{p}:{c}" for p, c in rimossi)
    )
