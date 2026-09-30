"""La protezione Mutui vale anche senza il middleware globale ERP."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mutui
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.utils.dependencies import get_current_user


@pytest.mark.parametrize('path', ['', '/', '/statistiche/dashboard', '/prova', '/prova/rate'])
def test_letture_mutui_non_ammettono_utenti_non_admin(path):
    app = FastAPI()
    app.include_router(mutui.router, prefix='/api/mutui')
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'fixture', 'role': 'viewer'}
    with TestClient(app) as client:
        assert client.get('/api/mutui' + path).status_code == 403


def test_mutui_rifiuta_anonimo_e_consente_admin(monkeypatch):
    app = FastAPI()
    app.include_router(mutui.router, prefix='/api/mutui')
    monkeypatch.setattr(mutui, 'get_db', lambda: ClientArchivioMemoria()['mutui_fixture'])
    with TestClient(app) as client:
        assert client.get('/api/mutui/').status_code in (401, 403)
        app.dependency_overrides[get_current_user] = lambda: {'user_id': 'fixture', 'role': 'admin'}
        response = client.get('/api/mutui/')
        assert response.status_code == 200
        assert response.json()['data'] == []
