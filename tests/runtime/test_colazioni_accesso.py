"""Colazioni B&B: il titolare entra con la sessione del gestionale, mai con un PIN suo.

Il token lo emette il database (`bb_tit_sessione_apri`) dietro la chiave di
runtime che ha solo questo backend; qui si verifica che l'endpoint lo chieda
soltanto per un amministratore e che non sia pubblico.
"""
import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.middleware.authentication import PUBLIC_PATHS
from app.routers import colazioni
from app.utils.dependencies import get_current_admin_user


def _client(monkeypatch, admin: bool, esito=None):
    app = FastAPI()
    app.include_router(colazioni.router, prefix="/api/colazioni")

    async def _admin():
        if not admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return {"id": "1", "role": "admin"}

    app.dependency_overrides[get_current_admin_user] = _admin

    async def _finto():
        return esito

    monkeypatch.setattr(colazioni, "_apri_sessione_supabase", _finto)
    return TestClient(app)


def test_admin_riceve_il_token(monkeypatch):
    c = _client(monkeypatch, True, {"token": "tk:abc", "scade": "2026-10-01T00:00:00Z"})
    r = c.post("/api/colazioni/accesso")
    assert r.status_code == 200
    assert r.json() == {"token": "tk:abc", "scade": "2026-10-01T00:00:00Z"}


def test_chi_non_e_admin_non_riceve_niente(monkeypatch):
    c = _client(monkeypatch, False, {"token": "tk:abc"})
    assert c.post("/api/colazioni/accesso").status_code == 403


def test_risposta_senza_token_e_un_errore(monkeypatch):
    c = _client(monkeypatch, True, {})
    assert c.post("/api/colazioni/accesso").status_code == 502


def test_senza_configurazione_supabase_risponde_503(monkeypatch):
    for nome in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_RUNTIME_SECRET"):
        monkeypatch.setattr(colazioni.settings, nome, None, raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(colazioni._apri_sessione_supabase())
    assert exc.value.status_code == 503


def test_l_endpoint_non_e_pubblico():
    assert "/api/colazioni/accesso" not in PUBLIC_PATHS
    assert {p for p in PUBLIC_PATHS if p.startswith("/api/colazioni")} == {
        "/api/colazioni/ospite/evento"
    }


def test_l_endpoint_e_registrato_nel_gestionale():
    from app.main import app

    percorsi = {getattr(r, "path", "") for r in app.routes}
    assert "/api/colazioni/accesso" in percorsi
