"""Permessi della sotto-app montata: DB sintetico, nessuna chiamata esterna."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.hr.routers import dipendenti_cloud as module
from app.hr.utils.dependencies import require_staff, require_cloud_access


@pytest.fixture
def client(monkeypatch):
    db = MagicMock()
    db.dipendenti.find.return_value.to_list = AsyncMock(return_value=[{
        "id": "fixture", "nome": "Persona", "cognome": "Prova", "stato": "attivo",
        "iban": "non-pubblicare", "importo_stipendio": 100, "email": "test@example.invalid",
    }])
    db.ferie_cloud.find.return_value.to_list = AsyncMock(return_value=[{
        "id": "assenza", "dipendente_id": "fixture", "stato": "approvata", "nota": "riservata",
    }])
    monkeypatch.setattr(module, "get_db", lambda: db)
    hr = FastAPI()
    hr.include_router(module.router, prefix="/api", dependencies=[Depends(require_cloud_access)])
    hr.dependency_overrides[require_staff] = lambda: {"role": "responsabile_turni"}
    app = FastAPI()
    app.mount("/hr", hr)
    with TestClient(app) as value:
        yield value, hr, db


@pytest.mark.parametrize("method,path", [
    ("GET", "/paghe"), ("GET", "/bonifici-da-associare"),
    ("GET", "/dipendenti/fixture"), ("GET", "/prestiti"),
    ("POST", "/dipendenti"), ("DELETE", "/dipendenti/fixture"),
    ("POST", "/assegnazioni-turni/migra"),
])
def test_responsabile_non_puo_accedere_ad_amministrazione(client, method, path):
    web, _, db = client
    response = web.request(method, f"/hr/api/dipendenti-cloud{path}", json={})
    assert response.status_code == 403
    assert db.mock_calls == []


def test_turni_leggono_solo_anagrafica_minima(client):
    web, _, _ = client
    result = web.get("/hr/api/dipendenti-cloud/dipendenti")
    assert result.status_code == 200
    assert result.json()[0]["id"] == "fixture"
    assert not {"iban", "importo_stipendio", "email"}.intersection(result.json()[0])


def test_assenze_senza_note_private(client):
    web, _, _ = client
    result = web.get("/hr/api/dipendenti-cloud/ferie")
    assert result.status_code == 200
    assert "nota" not in result.json()[0]


def test_admin_conserva_anagrafica_completa(client):
    web, hr, _ = client
    hr.dependency_overrides[require_staff] = lambda: {"role": "admin"}
    result = web.get("/hr/api/dipendenti-cloud/dipendenti")
    assert result.status_code == 200
    assert result.json()[0]["importo_stipendio"] == 100


def test_app_hr_reale_monta_la_guardia_sui_cedolini(monkeypatch):
    from app.hr.main import app as hr

    monkeypatch.setitem(hr.dependency_overrides, require_staff,
                        lambda: {"role": "responsabile_turni"})
    root = FastAPI()
    root.mount("/hr", hr)
    # Nessun lifespan HR: scheduler e archivi reali non vengono avviati.
    response = TestClient(root).get("/hr/api/dipendenti-cloud/paghe")
    assert response.status_code == 403
