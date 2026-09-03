"""Perimetro delle sessioni HR nel middleware unico.

- il login del portale e' pubblico (nome + PIN), tutto il resto di /api/hr
  richiede un token;
- un token con ruolo ``dipendente`` o ``responsabile_turni`` passa SOLO sui
  percorsi /api/hr/ (mai sui dati contabili del gestionale);
- l'amministratore del gestionale entra in /api/hr con la stessa sessione;
- le dependency HR distinguono admin / staff / dipendente.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware.authentication import AuthenticationMiddleware
from app.utils import token_blacklist


def _token(role, exp_minutes=10):
    return jwt.encode(
        {"sub": "u1", "role": role, "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


@pytest.fixture
def client(monkeypatch):
    async def _non_revocato(_db, _token):
        return False
    monkeypatch.setattr(token_blacklist, "is_revocato", _non_revocato)

    from app import database as gestionale_database
    monkeypatch.setattr(gestionale_database.Database, "get_db", classmethod(lambda cls: object()))

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/api/hr/auth/dipendenti-attivi")
    async def pubblico():
        return {"ok": True}

    @app.get("/api/hr/portale/buste")
    async def hr(request: Request):
        return {"role": request.state.user_role}

    @app.get("/api/prima-nota/saldi")
    async def contabile(request: Request):
        return {"role": request.state.user_role}

    @app.post("/api/auth/logout")
    async def logout():
        return {"ok": True}

    return TestClient(app)


def test_login_portale_e_pubblico(client):
    assert client.get("/api/hr/auth/dipendenti-attivi").status_code == 200
    assert client.get("/api/hr/portale/buste").status_code == 401


def test_dipendente_entra_solo_nel_modulo_hr(client):
    h = {"Authorization": f"Bearer {_token('dipendente')}"}
    assert client.get("/api/hr/portale/buste", headers=h).json() == {"role": "dipendente"}
    r = client.get("/api/prima-nota/saldi", headers=h)
    assert r.status_code == 403
    assert client.post("/api/auth/logout", headers=h).status_code == 200


def test_responsabile_turni_stesso_perimetro(client):
    h = {"Authorization": f"Bearer {_token('responsabile_turni')}"}
    assert client.get("/api/hr/portale/buste", headers=h).status_code == 200
    assert client.get("/api/prima-nota/saldi", headers=h).status_code == 403


def test_admin_del_gestionale_entra_anche_in_hr(client):
    h = {"Authorization": f"Bearer {_token('admin')}"}
    assert client.get("/api/hr/portale/buste", headers=h).json() == {"role": "admin"}
    assert client.get("/api/prima-nota/saldi", headers=h).status_code == 200


def test_dependency_hr_admin_staff_e_identita():
    from app.hr.utils.dependencies import require_admin, require_staff
    from app.hr.utils.identity import get_identity
    from fastapi import HTTPException

    def _req(role, cookie=False):
        token = _token(role)
        headers = [(b"cookie", f"access_token={token}".encode())] if cookie else [(b"authorization", f"Bearer {token}".encode())]
        return Request({"type": "http", "headers": headers, "method": "GET", "path": "/api/hr/x", "query_string": b""})

    assert asyncio.run(require_admin(_req("admin")))["role"] == "admin"
    assert asyncio.run(require_admin(_req("admin", cookie=True)))["role"] == "admin"
    with pytest.raises(HTTPException) as e:
        asyncio.run(require_admin(_req("responsabile_turni")))
    assert e.value.status_code == 403
    assert asyncio.run(require_staff(_req("responsabile_turni")))["role"] == "responsabile_turni"
    with pytest.raises(HTTPException):
        asyncio.run(require_staff(_req("dipendente")))
    identita = asyncio.run(get_identity(_req("dipendente")))
    assert identita == {"id": "u1", "role": "dipendente", "tipo": "dipendente", "name": None, "auth_method": None}
    with pytest.raises(HTTPException) as e:
        asyncio.run(get_identity(Request({"type": "http", "headers": [], "method": "GET", "path": "/", "query_string": b""})))
    assert e.value.status_code == 401
