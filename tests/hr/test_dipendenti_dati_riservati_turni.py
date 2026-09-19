"""18/09/2026: il ruolo "responsabile_turni" entra con lo stesso require_staff
di un admin (gli serve per la pagina Turni, che legge da questo router), ma
riceveva IBAN, stipendio, email, telefono, indirizzo, data di nascita e
codice fiscale di tutta l'azienda — dati che la pagina Turni (l'unica che
App.jsx gli mostra: la forza sempre su quella) non usa mai. GET /dipendenti e
GET /dipendenti/{id} ora tolgono quei campi solo per quel ruolo; un admin (o
una chiamata diretta fuori da FastAPI, come fanno gli altri test di questo
file) continua a vederli tutti."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import dipendenti_cloud as mod


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_riservati_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    _run(db.dipendenti.insert_one({
        "id": "dip-1", "nome": "Mario", "cognome": "Rossi", "stato": "attivo",
        "attivo": True, "ruolo": "cameriere", "luogo_lavoro": "Sala",
        "iban": "IT60X0542811101000000123456", "email": "mario@example.com",
        "telefono": "3331234567", "importo_stipendio": 1500.0,
        "data_nascita": "1990-01-01", "indirizzo": "Via Roma 1, Napoli",
        "codice_fiscale": "RSSMRA90A01F839X",
    }))
    return db


_ADMIN = {"role": "admin", "sub": "admin"}
_TURNI = {"role": "responsabile_turni", "sub": "resp"}
_CAMPI_RISERVATI = ("iban", "email", "telefono", "importo_stipendio",
                    "data_nascita", "indirizzo", "codice_fiscale")


def test_lista_toglie_i_campi_riservati_solo_al_responsabile_turni(hr):
    completa = {d["id"]: d for d in _run(mod.get_dipendenti(identity=_ADMIN))}["dip-1"]
    for campo in _CAMPI_RISERVATI:
        assert campo in completa and completa[campo]

    filtrata = {d["id"]: d for d in _run(mod.get_dipendenti(identity=_TURNI))}["dip-1"]
    for campo in _CAMPI_RISERVATI:
        assert campo not in filtrata
    # i campi che servono alla pagina Turni restano tutti
    assert filtrata["nome"] == "Mario" and filtrata["cognome"] == "Rossi"
    assert filtrata["ruolo"] == "cameriere" and filtrata["luogo_lavoro"] == "Sala"
    assert filtrata["stato"] == "attivo" and filtrata["id"] == "dip-1"


def test_dettaglio_toglie_i_campi_riservati_solo_al_responsabile_turni(hr):
    completo = _run(mod.get_dipendente("dip-1", identity=_ADMIN))
    for campo in _CAMPI_RISERVATI:
        assert campo in completo

    filtrato = _run(mod.get_dipendente("dip-1", identity=_TURNI))
    for campo in _CAMPI_RISERVATI:
        assert campo not in filtrato
    assert filtrato["nome"] == "Mario"


def test_chiamata_diretta_senza_richiesta_fastapi_resta_completa(hr):
    """I test esistenti (test_hr_anagrafica_stato_rapporto.py) chiamano
    get_dipendenti()/get_dipendente() senza passare identity: il parametro
    resta il sentinella Depends(require_staff) non risolto, non un dict, e
    non deve mai essere scambiato per il ruolo da filtrare."""
    lista = {d["id"]: d for d in _run(mod.get_dipendenti())}["dip-1"]
    for campo in _CAMPI_RISERVATI:
        assert campo in lista
    dettaglio = _run(mod.get_dipendente("dip-1"))
    for campo in _CAMPI_RISERVATI:
        assert campo in dettaglio


def test_identity_none_o_senza_ruolo_non_filtra(hr):
    assert mod._per_responsabile_turni(None) is False
    assert mod._per_responsabile_turni({}) is False
    assert mod._per_responsabile_turni({"role": "admin"}) is False
    assert mod._per_responsabile_turni({"role": "responsabile_turni"}) is True
