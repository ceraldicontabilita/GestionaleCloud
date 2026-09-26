"""`/hr/api/health` e `/menu/api/health` hanno lo stesso contratto dell'ERP.

Prima rispondevano `{"status": "ok"}` sempre, anche con il database giu':
il workflow di produzione li vedeva verdi senza sapere niente. Ora dichiarano
il commit pubblicato (stessa fonte di ERP e Lotti), provano database (e per il
Menu lo storage delle foto) con una sola probe in volo per processo, dicono se
i segreti di accesso ci sono — mai il valore — e rispondono entro il budget
anche con la probe appesa (`degraded`, HTTP 200; `?strict=true` per il 503).
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.hr import main as hr_main
from app.menu import server as menu_server
from app.services.health_probe import ProbeUnica

COMMIT = "bd3b2b13df7a07eea54ba6ab293ab3432f4b3c81"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", COMMIT)
    monkeypatch.setenv("HR_JWT_SECRET", "segreto-hr-di-prova")
    monkeypatch.setenv("PIN_HASH_ADMIN", "a" * 64)
    monkeypatch.setenv("MENU_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MENU_SUPABASE_KEY", "chiave-menu-di-prova")
    monkeypatch.setattr("app.menu.routes.qrcode_routes.SECRET_KEY", "segreto-menu-di-prova")
    # probe nuove a ogni test: l'esito in memoria e' per processo
    monkeypatch.setattr(hr_main, "_probe_database", ProbeUnica("database HR"))
    monkeypatch.setattr(menu_server, "_probe_database", ProbeUnica("database Menu"))
    monkeypatch.setattr(menu_server, "_probe_storage", ProbeUnica("storage Menu"))


class _DbHr:
    def __init__(self, ritardo=0.0, errore=None):
        self.ritardo = ritardo
        self.errore = errore
        self.chiamate = 0

    async def ping(self):
        self.chiamate += 1
        await asyncio.sleep(self.ritardo)
        if self.errore:
            raise self.errore


def _hr(monkeypatch, db, backend="supabase"):
    monkeypatch.setattr(hr_main.Database, "db", db)
    monkeypatch.setattr(hr_main.Database, "backend", backend)


def _corpo(risposta):
    if hasattr(risposta, "status_code"):
        return risposta.status_code, json.loads(risposta.body)
    return 200, risposta


# ── HR ──────────────────────────────────────────────────────────────────────
def test_hr_sano_dichiara_commit_database_e_segreti(monkeypatch):
    _hr(monkeypatch, _DbHr())
    stato, corpo = _corpo(asyncio.run(hr_main.health()))
    assert stato == 200
    assert corpo["status"] == "healthy"
    assert corpo["database"] == "connected"
    assert corpo["deploy_commit"] == COMMIT
    assert corpo["auth"] == {"jwt_secret": True, "pin_admin": True}
    # mai il valore dei segreti
    testo = json.dumps(corpo)
    assert "segreto-hr-di-prova" not in testo and "a" * 64 not in testo


def test_hr_database_appeso_risponde_entro_il_budget(monkeypatch):
    _hr(monkeypatch, _DbHr(ritardo=5))
    monkeypatch.setattr(hr_main, "_HEALTH_TIMEOUT", 0.05)
    t0 = time.monotonic()
    stato, corpo = _corpo(asyncio.run(hr_main.health()))
    assert time.monotonic() - t0 < 1.0
    assert stato == 200
    assert corpo["status"] == "degraded"
    assert corpo["database"] == "unreachable"
    assert "oltre" in corpo["database_errore"]


def test_hr_una_sola_probe_in_volo(monkeypatch):
    db = _DbHr(ritardo=0.2)
    _hr(monkeypatch, db)
    monkeypatch.setattr(hr_main, "_HEALTH_TIMEOUT", 0.02)

    async def cinque_chiamate():
        return await asyncio.gather(*(hr_main.health() for _ in range(5)))

    asyncio.run(cinque_chiamate())
    assert db.chiamate == 1


def test_hr_database_in_errore_strict_503(monkeypatch):
    _hr(monkeypatch, _DbHr(errore=ConnectionError("connection refused")))
    stato, corpo = _corpo(asyncio.run(hr_main.health()))
    assert stato == 200 and corpo["status"] == "degraded"
    assert "ConnectionError" in corpo["database_errore"]
    stato, corpo = _corpo(asyncio.run(hr_main.health(strict=True)))
    assert stato == 503 and corpo["status"] == "unhealthy"


def test_hr_segreto_mancante_e_database_non_configurato(monkeypatch):
    monkeypatch.delenv("HR_JWT_SECRET")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("PIN_HASH_ADMIN")
    _hr(monkeypatch, None, backend="non_configurato")
    stato, corpo = _corpo(asyncio.run(hr_main.health()))
    assert stato == 200
    assert corpo["status"] == "degraded"
    assert corpo["database"] == "not_configured"
    assert corpo["auth"] == {"jwt_secret": False, "pin_admin": False}
    stato, _ = _corpo(asyncio.run(hr_main.health(strict=True)))
    assert stato == 503


# ── Menu ────────────────────────────────────────────────────────────────────
def _menu(monkeypatch, db=None, storage=None):
    chiamate = {"db": 0, "storage": 0}

    async def ping_db():
        chiamate["db"] += 1
        if db:
            await db()

    async def ping_storage():
        chiamate["storage"] += 1
        if storage:
            await storage()

    monkeypatch.setattr(menu_server, "_ping_database", ping_db)
    monkeypatch.setattr(menu_server, "_ping_storage", ping_storage)
    return chiamate


def test_menu_sano_dichiara_commit_database_storage_e_segreti(monkeypatch):
    _menu(monkeypatch)
    stato, corpo = _corpo(asyncio.run(menu_server.health()))
    assert stato == 200
    assert corpo["status"] == "healthy"
    assert corpo["database"] == "connected"
    assert corpo["storage"] == "connected"
    assert corpo["storage_bucket"] == "menu-images"
    assert corpo["deploy_commit"] == COMMIT
    assert corpo["auth"] == {"jwt_secret": True, "pin_admin": True}
    testo = json.dumps(corpo)
    assert "segreto-menu-di-prova" not in testo and "chiave-menu-di-prova" not in testo


def test_menu_storage_giu_degraded_strict_503(monkeypatch):
    async def storage_rotto():
        raise RuntimeError("bucket non raggiungibile")

    _menu(monkeypatch, storage=storage_rotto)
    stato, corpo = _corpo(asyncio.run(menu_server.health()))
    assert stato == 200 and corpo["status"] == "degraded"
    assert corpo["database"] == "connected"
    assert corpo["storage"] == "unreachable"
    stato, _ = _corpo(asyncio.run(menu_server.health(strict=True)))
    assert stato == 503


def test_menu_supabase_appeso_risponde_entro_il_budget(monkeypatch):
    async def lento():
        await asyncio.sleep(5)

    chiamate = _menu(monkeypatch, db=lento, storage=lento)
    monkeypatch.setattr(menu_server, "_HEALTH_TIMEOUT", 0.05)

    async def tre_chiamate():
        return await asyncio.gather(*(menu_server.health() for _ in range(3)))

    t0 = time.monotonic()
    risposte = asyncio.run(tre_chiamate())
    assert time.monotonic() - t0 < 1.0
    assert all(r["status"] == "degraded" for r in risposte)
    # una sola probe in volo per componente
    assert chiamate == {"db": 1, "storage": 1}
    # il solo budget scaduto non e' un guasto certo: anche strict resta 200
    stato, _ = _corpo(asyncio.run(menu_server.health(strict=True)))
    assert stato == 200


def test_menu_senza_credenziali_supabase(monkeypatch):
    monkeypatch.delenv("MENU_SUPABASE_URL")
    chiamate = _menu(monkeypatch)
    stato, corpo = _corpo(asyncio.run(menu_server.health()))
    assert stato == 200
    assert corpo["database"] == "not_configured"
    assert corpo["storage"] == "not_configured"
    assert chiamate == {"db": 0, "storage": 0}


def test_menu_probe_vere_usano_tabella_e_bucket_leggeri(monkeypatch):
    """Le probe reali leggono una riga di menu_allergens e al piu' un oggetto
    del bucket, con la chiave anon del Menu (niente get_bucket: su
    storage.buckets anon non ha policy)."""
    registro = []

    class _Query:
        def select(self, campi):
            registro.append(("select", campi))
            return self

        def limit(self, n):
            registro.append(("limit", n))
            return self

        def execute(self):
            return None

    class _Bucket:
        def list(self, path, options):
            registro.append(("list", path, options))
            return []

    class _Storage:
        def from_(self, nome):
            registro.append(("bucket", nome))
            return _Bucket()

        def get_bucket(self, nome):  # pragma: no cover - non deve servire
            raise AssertionError("get_bucket non e' permesso alla chiave anon")

    class _Client:
        storage = _Storage()

        def table(self, nome):
            registro.append(("table", nome))
            return _Query()

    monkeypatch.setattr(menu_server, "get_supabase", lambda: _Client())
    asyncio.run(menu_server._ping_database())
    asyncio.run(menu_server._ping_storage())
    assert ("table", "menu_allergens") in registro
    assert ("limit", 1) in registro
    assert ("bucket", "menu-images") in registro
    assert ("list", "", {"limit": 1}) in registro
