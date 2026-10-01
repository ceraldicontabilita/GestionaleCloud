"""Le scritture operative verificano la sessione sulla scheda HR vigente."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def ambiente(monkeypatch):
    from app.hr.database import Database as DatabaseHR
    import app.lotti.db as lotti_db
    from app.lotti.auth import auth_dependency

    hr = AsyncMongoMockClient()["hr_sessioni_test"]
    lotti = AsyncMongoMockClient()["lotti_sessioni_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    monkeypatch.setattr(lotti_db, "database", lotti)
    monkeypatch.setenv("LOTTI_AUTH_SECRET", "segreto-sessioni-isolate-di-prova-32")
    run(hr.dipendenti.insert_one({
        "id": "hr-operatore", "stato": "attivo", "pin_hash": "hash-fixture",
        "lotti_operatore": True, "lotti_ruolo": "operatore",
    }))
    run(lotti.tablet_operatori.insert_one({
        "id": "tablet-storico", "hr_id": "hr-operatore", "gestionale_dipendente_id": "hr-operatore",
        "attivo": True, "ruolo_lotti": "haccp",
    }))
    app = FastAPI(dependencies=[Depends(auth_dependency)])
    scritture = []

    async def scrivi():
        scritture.append("operazione-di-prova")
        return {"ok": True}

    for metodo, percorso in PERCORSI:
        app.add_api_route(percorso, scrivi, methods=[metodo])
    return TestClient(app), hr, lotti, scritture


PERCORSI = [
    ("POST", "/api/magazzino-bar/richieste"),
    ("PUT", "/api/magazzino-bar/richieste/r1/ok"),
    ("DELETE", "/api/magazzino-bar/richieste/r1"),
    ("POST", "/api/lotti"),
    ("POST", "/api/gelati/produzioni"),
    ("POST", "/api/vendita-banco/registra"),
    ("POST", "/api/temperature-positive/scheda/2026/1/registra"),
]


def headers(sub="hr-operatore", *, metodo="pin", auth_at=None):
    from app.lotti.auth import make_token

    return {"Authorization": f"Bearer {make_token(sub, 'Operatore prova', 'operatore', via=metodo, auth_at=auth_at)}"}


@pytest.mark.parametrize("metodo,percorso", PERCORSI)
@pytest.mark.parametrize("revoca", [{"stato": "cessato"}, {"pin_hash": None}, {"lotti_operatore": False}])
def test_stesso_token_revocato_non_scrive_piu(ambiente, metodo, percorso, revoca):
    client, hr, _lotti, scritture = ambiente
    token = headers()
    assert client.request(metodo, percorso, headers=token).status_code == 200
    run(hr.dipendenti.update_one({"id": "hr-operatore"}, {"$set": revoca}))
    assert client.request(metodo, percorso, headers=token).status_code == 401
    assert len(scritture) == 1


@pytest.mark.parametrize("metodo", ["pin", "pin_dipendente"])
def test_pin_cambiato_non_rivive_con_jwt_rinnovato(ambiente, metodo):
    client, hr, _lotti, scritture = ambiente
    now = datetime.now(timezone.utc)
    token = headers(metodo=metodo, auth_at=int((now - timedelta(minutes=1)).timestamp()))
    run(hr.dipendenti.update_one({"id": "hr-operatore"}, {"$set": {
        "pin_updated_at": (now - timedelta(seconds=5)).isoformat(),
    }}))
    assert client.post("/api/lotti", headers=token).status_code == 401
    assert scritture == []


def test_token_tablet_storico_risolto_solo_per_identita(ambiente):
    client, hr, _lotti, scritture = ambiente
    token = headers("tablet-storico")
    assert client.post("/api/lotti", headers=token).status_code == 200
    run(hr.dipendenti.update_one({"id": "hr-operatore"}, {"$set": {"stato": "cessato"}}))
    assert client.post("/api/lotti", headers=token).status_code == 401
    assert len(scritture) == 1


def test_identita_tablet_ambigua_non_autorizza(ambiente):
    client, _hr, lotti, scritture = ambiente
    run(lotti.tablet_operatori.update_one({"id": "tablet-storico"}, {"$set": {"hr_id": "persona-diversa"}}))
    assert client.post("/api/lotti", headers=headers("tablet-storico")).status_code == 401
    assert scritture == []


def test_sessione_hr_non_usa_permessi_portale_revocati(ambiente):
    client, hr, _lotti, scritture = ambiente
    token = headers(metodo="pin_dipendente")
    assert client.post("/api/lotti", headers=token).status_code == 200
    run(hr.dipendenti.update_one({"id": "hr-operatore"}, {"$set": {"ruolo_app": "responsabile_turni"}}))
    assert client.post("/api/lotti", headers=token).status_code == 401
    assert len(scritture) == 1


def test_hr_indisponibile_blocca_scrittura_ma_preserva_sessione_erp(ambiente, monkeypatch):
    from app.hr.database import Database as DatabaseHR
    from app.lotti.auth import make_token
    from app.services import group_session

    client, _hr, _lotti, scritture = ambiente
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: None))
    assert client.post("/api/lotti", headers=headers()).status_code == 503

    async def non_revocata(_sid):
        return False

    monkeypatch.setattr(group_session, "sessione_revocata", non_revocata)
    token = make_token("erp:prova", "Titolare prova", "amministratore", via="sessione_erp", sid="sessione-di-prova")
    assert client.post("/api/lotti", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert len(scritture) == 1


def test_login_tablet_e_rinnovo_conservano_versione_pin(ambiente):
    from app.hr.services.auth_dipendenti import versione_pin
    from app.lotti.auth import router, verify_token
    from app.lotti.routers.tablet_operatori import _op_response

    client, hr, _lotti, _scritture = ambiente
    client.app.include_router(router, prefix="/api")
    dip = run(hr.dipendenti.find_one({"id": "hr-operatore"}))
    login = _op_response({"dipendente_id": dip["id"], "nome": "Persona prova",
                          "ruolo": "operatore", "pin_version": versione_pin(dip)})
    prima = verify_token(login["token"])
    assert prima["pin_version"] == versione_pin(dip)
    risposta = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {login['token']}"})
    assert risposta.status_code == 200
    dopo = verify_token(risposta.json()["token"])
    assert dopo["pin_version"] == prima["pin_version"]
    assert dopo["auth_at"] == prima["auth_at"]
    run(hr.dipendenti.update_one({"id": dip["id"]}, {"$set": {"pin_hash": "hash-reset-fixture",
        "pin_updated_at": datetime.now(timezone.utc).isoformat()}}))
    assert client.post("/api/lotti", headers={"Authorization": f"Bearer {risposta.json()['token']}"}).status_code == 401
