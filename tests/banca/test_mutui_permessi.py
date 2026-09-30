"""La protezione Mutui vale anche senza il middleware globale ERP."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mutui
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _token_fixture(role):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings
    return jwt.encode({'sub': 'fixture', 'role': role,
                       'exp': datetime.now(timezone.utc) + timedelta(hours=2)},
                      settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.mark.parametrize('trasporto', ['cookie', 'bearer'])
@pytest.mark.parametrize('ruolo,atteso', [('admin', 200), ('operatore', 403), ('sola_lettura', 403)])
def test_mutui_sessione_reale_con_middleware(monkeypatch, trasporto, ruolo, atteso):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings
    from app.database import Database
    from app.middleware.authentication import AuthenticationMiddleware

    db = ClientArchivioMemoria()['mutui_auth_fixture']
    monkeypatch.setattr(Database, 'db', db)
    monkeypatch.setattr(mutui, 'get_db', lambda: db)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(mutui.router, prefix='/api/mutui')
    token = jwt.encode({'sub': 'fixture', 'role': ruolo,
                        'exp': datetime.now(timezone.utc) + timedelta(hours=2)},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    kwargs = ({'cookies': {'access_token': token}} if trasporto == 'cookie'
              else {'headers': {'Authorization': 'Bearer ' + token}})
    with TestClient(app) as client:
        assert client.get('/api/mutui/', **kwargs).status_code == atteso


def test_mutui_bearer_invalido_non_ripiega_sul_cookie_admin(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings
    from app.database import Database
    from app.middleware.authentication import AuthenticationMiddleware

    db = ClientArchivioMemoria()['mutui_auth_fixture']
    monkeypatch.setattr(Database, 'db', db)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(mutui.router, prefix='/api/mutui')
    token = jwt.encode({'sub': 'fixture', 'role': 'admin',
                        'exp': datetime.now(timezone.utc) + timedelta(hours=2)},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with TestClient(app) as client:
        assert client.get('/api/mutui/', cookies={'access_token': token},
                          headers={'Authorization': 'Bearer invalido'}).status_code == 401


@pytest.mark.parametrize('path', ['', '/', '/statistiche/dashboard', '/prova', '/prova/rate'])
def test_letture_mutui_non_ammettono_utenti_non_admin(path):
    app = FastAPI()
    app.include_router(mutui.router, prefix='/api/mutui')
    with TestClient(app) as client:
        assert client.get('/api/mutui' + path,
                          headers={'Authorization': 'Bearer ' + _token_fixture('operatore')}).status_code == 403


def test_mutui_rifiuta_anonimo_e_consente_admin(monkeypatch):
    app = FastAPI()
    app.include_router(mutui.router, prefix='/api/mutui')
    monkeypatch.setattr(mutui, 'get_db', lambda: ClientArchivioMemoria()['mutui_fixture'])
    with TestClient(app) as client:
        assert client.get('/api/mutui/').status_code in (401, 403)
        response = client.get('/api/mutui/',
                              headers={'Authorization': 'Bearer ' + _token_fixture('admin')})
        assert response.status_code == 200
        assert response.json()['data'] == []


@pytest.mark.parametrize('trasporto', ['cookie', 'bearer'])
def test_mutui_sessione_revocata_non_accede(monkeypatch, trasporto):
    from app.database import Database
    from app.middleware.authentication import AuthenticationMiddleware
    from app.utils.token_blacklist import revoca_token
    import asyncio

    db = ClientArchivioMemoria()['mutui_revoca_fixture']
    monkeypatch.setattr(Database, 'db', db)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(mutui.router, prefix='/api/mutui')
    token = _token_fixture('admin')
    asyncio.run(revoca_token(db, token))
    kwargs = ({'cookies': {'access_token': token}} if trasporto == 'cookie'
              else {'headers': {'Authorization': 'Bearer ' + token}})
    with TestClient(app) as client:
        assert client.get('/api/mutui/', **kwargs).status_code == 401


def test_mutui_cookie_senza_middleware_non_e_fidato():
    app = FastAPI()
    app.include_router(mutui.router, prefix='/api/mutui')
    with TestClient(app) as client:
        assert client.get('/api/mutui/', cookies={'access_token': _token_fixture('admin')}).status_code == 401
