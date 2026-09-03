"""Flusso completo del PIN unificato sul modulo HR, sull'app reale.

Percorso: l'amministratore (sessione del gestionale) genera i PIN mancanti ->
il portale elenca il dipendente -> il dipendente entra con nome + PIN ->
il suo token vale nel modulo HR ma non sul resto del gestionale -> non e'
mai un token admin, nemmeno se in anagrafica ha ``ruolo_app = admin``.

Il registro dati e' lo store in memoria del gestionale (nessuna rete).
"""
import pytest
from fastapi.testclient import TestClient

from app.services.sheets_document_store import SheetDatabase
from app.utils.auth_tokens import create_access_token


@pytest.fixture
def client(monkeypatch):
    from app import database as gestionale_database
    from app.hr.database import Database as HRDatabase

    store = SheetDatabase("test")
    monkeypatch.setattr(gestionale_database.Database, "db", store)
    monkeypatch.setattr(gestionale_database.Database, "client", store)
    HRDatabase.reset()

    from app.utils import login_lockout
    login_lockout.clear_failures("testclient")

    # Senza context manager: niente lifespan (nessuna connessione al registro reale).
    import app.main as main
    yield TestClient(main.app, raise_server_exceptions=True), store
    HRDatabase.reset()


def _seed(store, **extra):
    import asyncio
    doc = {"id": "dip-1", "nome": "Anna", "cognome": "Rossi", "nome_completo": "Anna Rossi",
           "attivo": True, "stato": "attivo", "mansione": "Barista", **extra}
    asyncio.run(store["hr_dipendenti"].insert_one(doc))
    return doc


def _admin_headers():
    return {"Authorization": f"Bearer {create_access_token(user_id='admin@test', role='admin', auth_method='pin')}"}


def test_senza_pin_il_dipendente_non_compare_e_l_admin_lo_genera(client):
    c, store = client
    _seed(store)
    assert c.get("/api/hr/auth/dipendenti-attivi").json() == {"dipendenti": []}

    # Un dipendente non puo' generare PIN; l'admin del gestionale si'.
    assert c.post("/api/hr/accessi/genera-mancanti").status_code == 401
    r = c.post("/api/hr/accessi/genera-mancanti", headers=_admin_headers())
    assert r.status_code == 200, r.text
    generati = r.json()["generati"]
    assert len(generati) == 1 and generati[0]["nome_completo"] == "Anna Rossi"
    pin = generati[0]["pin"]
    assert pin.isdigit() and len(pin) == 6

    # Nel registro resta solo l'hash, mai il PIN.
    import asyncio
    salvato = asyncio.run(store["hr_dipendenti"].find_one({"id": "dip-1"}))
    assert salvato["pin_hash"] and pin not in str(salvato)

    # Ora il nome compare nel selettore del portale e il PIN apre la sessione.
    assert c.get("/api/hr/auth/dipendenti-attivi").json() == {"dipendenti": [{"id": "dip-1", "nome": "Anna Rossi"}]}
    assert c.post("/api/hr/auth/pin-login", json={"dipendente_id": "dip-1", "pin": "000000" if pin != "000000" else "111111"}).status_code == 401
    login = c.post("/api/hr/auth/pin-login", json={"dipendente_id": "dip-1", "pin": pin})
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "dipendente"
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # La sessione del portale vale nel modulo HR, non sul gestionale.
    assert c.get("/api/hr/notifiche", headers=h).status_code == 200
    assert c.get("/api/hr/accessi", headers=h).status_code == 403
    assert c.get("/api/prima-nota/saldi", headers=h).status_code == 403

    # Seconda generazione: chi ha gia' il PIN non viene toccato.
    assert c.post("/api/hr/accessi/genera-mancanti", headers=_admin_headers()).json()["totale"] == 0


def test_il_portale_non_emette_mai_un_token_admin(client):
    c, store = client
    _seed(store, ruolo_app="admin")
    pin = c.post("/api/hr/accessi/dip-1/pin/genera", headers=_admin_headers()).json()["pin"]
    login = c.post("/api/hr/auth/pin-login", json={"dipendente_id": "dip-1", "pin": pin})
    assert login.status_code == 200
    assert login.json()["role"] == "dipendente"
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert c.get("/api/hr/accessi", headers=h).status_code == 403
    assert c.get("/api/prima-nota/saldi", headers=h).status_code == 403


def test_il_pin_amministratore_non_passa_dal_portale(client):
    c, _ = client
    r = c.post("/api/hr/auth/pin-login", json={"pin": "123456"})
    assert r.status_code == 400
    assert "login del gestionale" in r.json()["message"]  # formato del gestore errori del gestionale


def test_responsabile_turni_e_rimozione_pin(client):
    c, store = client
    _seed(store)
    pin = c.post("/api/hr/accessi/dip-1/pin/genera", headers=_admin_headers()).json()["pin"]
    assert c.post("/api/hr/accessi/dip-1/ruolo", json={"ruolo_app": "admin"}, headers=_admin_headers()).status_code == 400
    assert c.post("/api/hr/accessi/dip-1/ruolo", json={"ruolo_app": "responsabile_turni"}, headers=_admin_headers()).status_code == 200
    login = c.post("/api/hr/auth/pin-login", json={"dipendente_id": "dip-1", "pin": pin})
    assert login.json()["role"] == "responsabile_turni"
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert c.get("/api/hr/dipendenti-cloud/turni", headers=h).status_code == 200
    assert c.delete("/api/hr/accessi/dip-1/pin", headers=_admin_headers()).status_code == 200
    assert c.post("/api/hr/auth/pin-login", json={"dipendente_id": "dip-1", "pin": pin}).status_code == 401
