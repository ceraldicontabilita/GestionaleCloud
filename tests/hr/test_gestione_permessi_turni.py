"""Confine HTTP: il responsabile gestisce i turni, non PIN e paghe."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from jose import jwt
from mongomock_motor import AsyncMongoMockClient

from app.hr.config import settings
from app.hr.database import Database
from app.hr.main import app
from app.services import group_session
from app.hr.services import auth_dipendenti


@pytest.fixture
def hr(monkeypatch):
    db = AsyncMongoMockClient()["permessi_turni_test"]
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    group_session._azzera_cache()

    async def non_revocata(_):
        return False

    monkeypatch.setattr(group_session, "sessione_revocata", non_revocata)
    asyncio.run(db.dipendenti.insert_one({
        "id": "dip-test", "nome": "Persona", "cognome": "Prova",
        "stato": "attivo", "ruolo_app": "dipendente", "pin_hash": "hash-prova",
    }))
    return db


def _request(method, path, *, ruolo="responsabile_turni", **kwargs):
    payload = {"sub": "operatore-prova", "role": ruolo,
               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    if ruolo == "admin":
        payload.update(auth_method="sessione_erp", sid="sessione-prova")
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def run():
        # ASGI senza lifespan: nessuna connessione/scheduler/seed reale.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://hr.test") as client:
            return await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)

    return asyncio.run(run())


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/dipendenti-cloud/dipendenti/dip-test/pin", {"pin": "1234"}),
    ("DELETE", "/api/dipendenti-cloud/dipendenti/dip-test/pin", None),
    ("DELETE", "/api/dipendenti-cloud/dipendenti/dip-test", None),
    ("POST", "/api/dipendenti-cloud/dipendenti/dip-test/cessa", {"data_cessazione": "2026-09-30"}),
    ("GET", "/api/dipendenti-cloud/paghe/in-attesa", None),
    ("GET", "/api/dipendenti-cloud/documenti", None),
    ("GET", "/api/dipendenti-cloud/dashboard/stats", None),
    ("POST", "/api/dipendenti-cloud/seed-data", None),
    ("GET", "/api/dipendenti", None),
    ("GET", "/api/dipendenti/dip-test/fascicolo", None),
    ("GET", "/api/giustificativi/saldi-finali-tutti", None),
    ("PUT", "/api/attendance/set-in-carico/dip-test", {"in_carico": False}),
])
def test_responsabile_non_raggiunge_gestione_riservata(hr, method, path, payload):
    response = _request(method, path, json=payload)
    assert response.status_code == 403
    dip = asyncio.run(hr.dipendenti.find_one({"id": "dip-test"}))
    assert dip["pin_hash"] == "hash-prova"
    assert dip["stato"] == "attivo"


def test_turni_scrittura_lettura_e_anagrafica_minima_resta_accessibile(hr):
    creazione = _request("POST", "/api/dipendenti-cloud/turni", json={
        "nome": "Mattina prova", "orario_inizio": "08:00", "orario_fine": "12:00"})
    assert creazione.status_code == 200
    turno_id = creazione.json()["id"]
    assert _request("GET", "/api/dipendenti-cloud/turni").json()[0]["id"] == turno_id
    dip = _request("GET", "/api/dipendenti-cloud/dipendenti").json()[0]
    assert dip["id"] == "dip-test"
    assert "pin_hash" not in dip and "iban" not in dip


def test_amministratore_accede_alla_gestione(hr):
    assert _request("GET", "/api/dipendenti-cloud/documenti", ruolo="admin").status_code == 200


def test_assenza_sessione_non_apre_gestione(hr):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://hr.test") as client:
            return await client.get("/api/dipendenti-cloud/dipendenti")

    assert asyncio.run(run()).status_code in {401, 403}


@pytest.mark.parametrize("modifica", [
    {"$set": {"stato": "cessato"}},
    {"$set": {"in_carico": False}},
    {"$set": {"ruolo_app": "dipendente"}},
    {"$unset": {"pin_hash": ""}},
    {"$set": {"pin_updated_at": "reset_dopo_emissione"}},
])
def test_revoca_di_una_sessione_gia_emessa_su_portale_e_gestione(hr, modifica):
    async def run():
        await hr.dipendenti.update_one({"id": "dip-test"}, {"$set": {"ruolo_app": "responsabile_turni"}})
        dip = await hr.dipendenti.find_one({"id": "dip-test"})
        token = auth_dipendenti.crea_token_dipendente(dip)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://hr.test",
                                    headers={"Authorization": f"Bearer {token}"}) as client:
            assert (await client.get("/api/timbrature/mie/oggi")).status_code == 200
            assert (await client.get("/api/dipendenti-cloud/dipendenti")).status_code == 200
            aggiornamento = modifica
            if modifica.get("$set", {}).get("pin_updated_at") == "reset_dopo_emissione":
                # Il reset deve seguire l'emissione del token, anche quando
                # questo test gira minuti dopo la collection di tutta la suite.
                aggiornamento = {"$set": {"pin_updated_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()}}
            await hr.dipendenti.update_one({"id": "dip-test"}, aggiornamento)
            assert (await client.get("/api/timbrature/mie/oggi")).status_code == 401
            assert (await client.get("/api/dipendenti-cloud/dipendenti")).status_code == 401

    asyncio.run(run())


@pytest.mark.parametrize("stato", [{"stato": "inattivo"}, {"in_carico": False}])
def test_login_per_nome_usa_lo_stesso_stato_del_selettore(hr, stato):
    async def run():
        await hr.dipendenti.update_one({"id": "dip-test"}, {"$set": {
            "pin_hash": auth_dipendenti.hash_pin("1234"), **stato}})
        assert await auth_dipendenti.login_dipendente_per_nome("Persona", "1234") is None
        assert await auth_dipendenti.login_dipendente("dip-test", "1234") is None

    asyncio.run(run())


def test_rinnovo_non_annulla_revoca_del_pin(hr):
    adesso = datetime.now(timezone.utc)
    dip = {"stato": "attivo", "pin_hash": "hash-sintetico",
           "pin_updated_at": adesso.isoformat()}
    assert not auth_dipendenti.sessione_pin_corrente(dip, {
        "iat": int(adesso.timestamp()) + 30, "auth_at": int(adesso.timestamp()) - 30,
    })


def test_helper_riusa_la_scheda_canonica_senza_seconda_lettura(monkeypatch):
    def lettura_vietata():
        raise AssertionError("scheda gia' letta dal chiamante")

    monkeypatch.setattr(Database, "get_db", lettura_vietata)
    payload = {"auth_method": "pin_dipendente", "role": "dipendente", "sub": "dip-prova"}
    dip = {"stato": "attivo", "pin_hash": "hash-sintetico", "ruolo_app": "dipendente"}
    assert asyncio.run(auth_dipendenti.sessione_dipendente_corrente(payload, dipendente=dip))
    dip["ruolo_app"] = "responsabile_turni"
    assert not asyncio.run(auth_dipendenti.sessione_dipendente_corrente(payload, dipendente=dip))
