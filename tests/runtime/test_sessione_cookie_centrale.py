"""Ritorno B&B → ERP e accesso B&B: richieste vere, solo database in memoria."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from mongomock_motor import AsyncMongoMockClient

from app.config import settings
from app.middleware.authentication import AuthenticationMiddleware
from app.routers import auth, colazioni
from app.services import group_session


def token(**extra):
    return jwt.encode({"sub": "admin-fixture", "role": "admin", "sid": "test-sessione-unica",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=50), **extra},
                      settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.fixture
def client(monkeypatch):
    db = AsyncMongoMockClient()['cookie_centrale']
    monkeypatch.setattr('app.database.Database.get_db', staticmethod(lambda: db))
    group_session._azzera_cache()

    async def stato(*_args):
        return {"enabled": False}

    async def apri():
        return {"token": "tk:fixture", "scade": "2099-01-01T00:00:00Z"}

    monkeypatch.setattr('app.services.mfa_service.get_status', stato)
    monkeypatch.setattr(colazioni, '_apri_sessione_supabase', apri)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(auth.router)
    app.include_router(colazioni.router, prefix='/api/colazioni')
    with TestClient(app) as c:
        yield c
    group_session._azzera_cache()


def test_cookie_admin_apre_bb_e_ripristina_erp_senza_pin(client):
    centrale = token()
    client.cookies.set('access_token', centrale)
    r = client.post('/api/colazioni/accesso')
    assert r.status_code == 200 and r.json()['token'] == 'tk:fixture'
    r = client.get('/api/auth/verify')
    assert r.status_code == 200 and r.json()['user']['role'] == 'admin'
    assert r.headers['x-token-rinnovato'] == centrale
    assert r.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('credenziale,atteso', [
    (None, 401), ('non-firmato', 401),
    (token(role='operatore'), 403), (token(role='dipendente'), 403),
    (token(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), 401),
    (token(purpose='mfa_login'), 401),
])
def test_cookie_non_amministratore_non_apre_bb(client, credenziale, atteso):
    if credenziale:
        client.cookies.set('access_token', credenziale)
    assert client.post('/api/colazioni/accesso').status_code == atteso


def test_logout_revoca_anche_vecchia_copia_della_sessione(client):
    primo = token(name='Prima emissione')
    rinnovato = token(name='Rinnovo')
    client.cookies.set('access_token', rinnovato)
    assert client.post('/api/auth/logout').status_code == 200
    client.cookies.set('access_token', primo)
    assert client.get('/api/auth/verify').status_code == 401
    assert client.post('/api/colazioni/accesso').status_code == 401


def test_challenge_mfa_non_ripristina_sessione(client):
    client.cookies.set('access_token', token(purpose='mfa_login'))
    r = client.get('/api/auth/verify')
    assert r.status_code == 401
    assert 'x-token-rinnovato' not in r.headers
