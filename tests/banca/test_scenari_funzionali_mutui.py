"""Collaudo funzionale Mutui: dall'addebito in estratto conto alla pagina, con i motori veri.

Scenario dell'utente: la rata esce dal conto (movimento d'estratto), la proiezione bancaria
scrive la riga di Prima Nota Banca `rata_mutuo` (numero mutuo + scadenza) e la pagina Mutui
la legge con `valuta_prove`. ATTESO secondo CLAUDE.md, sezione «Mutui».
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mutui as mod
from app.services import mutui_rate_dichiarate as svc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici

MUTUO = "mutuo_905217466"


def _run(coro):
    return asyncio.run(coro)


def _rata(n, scadenza, stato="Da pagare"):
    return {"numero_rata": n, "data_scadenza": scadenza, "importo_totale": 1000.0,
            "quota_capitale": 900.0, "quota_interessi": 100.0, "stato": stato}


def _movimento(mid, scadenza, importo, mutuo="1788 5217466", giorno=None):
    gg, mm, aaaa = scadenza.split("/")
    return {"id": mid, "data": giorno or f"{aaaa}-{mm}-{gg}", "tipo": "uscita", "importo": importo,
            "fonte": "enable_banking",
            "descrizione_originale": f"RIMBORSO FINANZ. - MUTUO N.{mutuo} RATA {scadenza}"}


@pytest.fixture
def db(monkeypatch):
    db = ClientArchivioMemoria()["mutui-scenari"]
    _run(db["mutui_piani_documentali"].insert_one({
        "numero_delibera": "905217466", "tipo_finanziamento": "MUTUO IMPRESA RETAIL",
        "importo_accordato": 10000.0, "sha256": "s", "updated_at": "2026-09-01T00:00:00+00:00",
        "rate": [
            _rata(1, "17/01/2021"), _rata(2, "17/02/2021"), _rata(3, "17/03/2021"),
            _rata(4, "17/04/2021"), _rata(5, "17/05/2021"),
            _rata(6, "17/06/2021", "Pagata"),        # «Pagata» scritto sul piano, senza prova
        ],
    }))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    return db


@pytest.fixture
def client(db):
    from app.utils.dependencies import get_current_admin_user

    app = FastAPI()
    app.include_router(mod.router, prefix="/api/mutui")
    app.dependency_overrides[mod._admin_mutui] = lambda: {"user_id": "titolare", "role": "admin"}
    app.dependency_overrides[get_current_admin_user] = lambda: {"user_id": "titolare", "role": "admin"}
    return TestClient(app)


def _rate(client):
    dati = client.get(f"/api/mutui/{MUTUO}").json()["data"]
    return dati, {r["numero_rata"]: r for r in dati["rate"]}


def _addebita(db, *movimenti):
    _run(db["estratto_conto_movimenti"].insert_many([dict(m) for m in movimenti]))
    return _run(proietta_movimenti_bancari_semantici(db))


def test_addebito_in_banca_pagata_con_differenza_entro_5_euro_da_verificare_oltre(db, client):
    """ATTESO: +2,75 (tasso variabile) e +5,00 al confine -> Pagata con la differenza;
    +5,01 -> «Da verificare», mai Pagata, e la rata resta nel residuo."""
    esito = _addebita(
        db,
        _movimento("m1", "17/01/2021", 1002.75),
        _movimento("m2", "17/02/2021", 1005.00),
        _movimento("m3", "17/03/2021", 1005.01),
    )
    assert esito["rate_mutuo"] == 3
    mutuo, rate = _rate(client)
    assert rate[1]["stato"] == "Pagata" and rate[1]["prova"] == "banca"
    assert rate[1]["differenza_importo_cents"] == 275 and rate[1]["riconciliata"] is True
    assert rate[2]["stato"] == "Pagata" and rate[2]["differenza_importo_cents"] == 500
    assert rate[3]["stato"] == "Da verificare" and rate[3]["prova"] is None
    assert rate[3]["differenza_importo_cents"] == 501
    assert rate[4]["stato"] == "Da pagare"
    # residuo: 3 (da verificare), 4, 5 da pagare; la 6 e' pagata solo sul piano
    assert mutuo["rate_da_verificare"] == 1
    assert mutuo["debito_residuo_totale"] == 3000.0


def test_due_pagamenti_dello_stesso_giorno_che_sommano_la_rata_la_reggono(db, client):
    _addebita(db, _movimento("m1", "17/04/2021", 600.0), _movimento("m2", "17/04/2021", 400.0))
    _, rate = _rate(client)
    assert rate[4]["stato"] == "Pagata" and rate[4]["prova"] == "banca"
    assert rate[4]["differenza_importo_cents"] == 0


def test_il_pagamento_di_un_altro_mutuo_o_di_un_altra_scadenza_non_paga_la_rata(db, client):
    _addebita(
        db,
        _movimento("m1", "17/01/2021", 1000.0, mutuo="1788 9999999"),      # altro mutuo
        _movimento("m2", "17/03/2021", 1000.0),                            # rata 3, non la 2
    )
    _, rate = _rate(client)
    assert rate[1]["stato"] == "Da pagare" and rate[2]["stato"] == "Da pagare"
    assert rate[3]["stato"] == "Pagata"


def test_pagato_sul_piano_con_pagamento_parziale_e_da_verificare(db, client):
    """ATTESO: il «Pagata» del piano non copre un pagamento di 600 su 1000."""
    _addebita(db, _movimento("m1", "17/06/2021", 600.0))
    mutuo, rate = _rate(client)
    assert rate[6]["stato"] == "Da verificare" and rate[6]["differenza_importo_cents"] == -40000
    assert mutuo["debito_residuo_totale"] >= 1000.0


def test_dichiarazione_dry_run_non_scrive_conferma_forte_scrive_solo_la_collezione_dedicata(db, client):
    _addebita(db, _movimento("m1", "17/03/2021", 1005.01))   # rata 3 da verificare
    piano_prima = _run(db["mutui_piani_documentali"].find_one({}, {"_id": 0}))
    prima_nota = _run(db["prima_nota_banca"].count_documents({}))

    anteprima = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={"data_limite": "2026-09-30"}).json()["data"]
    assert anteprima["dry_run"] is True and anteprima["effetti_contabili"] == "nessuno"
    assert 3 not in anteprima["numeri_rata"] and anteprima["da_verificare"] == [3]
    assert anteprima["numeri_rata"] == [1, 2, 4, 5]
    assert _run(db["mutui_rate_dichiarate"].count_documents({})) == 0

    senza = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={"dry_run": False})
    assert senza.status_code == 409 and _run(db["mutui_rate_dichiarate"].count_documents({})) == 0

    fatto = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={
        "dry_run": False, "conferma": anteprima["frase_conferma"], "data_limite": "2026-09-30"}).json()["data"]
    assert fatto["dichiarate"] == 4
    righe = _run(db["mutui_rate_dichiarate"].find({}, {"_id": 0}).to_list(None))
    assert {r["numero_rata"] for r in righe} == {1, 2, 4, 5}
    assert all(r["stato"] == svc.STATO_DICHIARATA for r in righe)
    # non nel piano, nessuna scrittura contabile
    assert _run(db["mutui_piani_documentali"].find_one({}, {"_id": 0})) == piano_prima
    assert _run(db["prima_nota_banca"].count_documents({})) == prima_nota
    for coll in ("movimenti_contabili", "prima_nota_cassa", "prima_nota"):
        assert _run(db[coll].count_documents({})) == 0

    # la dichiarazione non salva la rata con importo non conforme
    _, rate = _rate(client)
    assert rate[3]["stato"] == "Da verificare"
    assert rate[4]["stato"] == "Pagata" and rate[4]["prova"] == "dichiarata_titolare"


def test_una_prova_successiva_sostituisce_la_dichiarazione(db, client):
    anteprima = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={"data_limite": "2026-09-30"}).json()["data"]
    client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={
        "dry_run": False, "conferma": anteprima["frase_conferma"], "data_limite": "2026-09-30"})
    # arriva l'estratto con l'addebito della rata 2
    _addebita(db, _movimento("m2", "17/02/2021", 1002.75))
    _, rate = _rate(client)
    assert rate[2]["prova"] == "banca" and rate[2]["dichiarata_titolare"] is False
    assert rate[2]["dichiarazione_sostituita"] is True
    esito = client.post("/api/mutui/riconcilia").json()["data"]
    assert esito["dichiarazioni_sostituite_da_prova"] == 1
    riga = _run(db["mutui_rate_dichiarate"].find_one({"numero_rata": 2}, {"_id": 0}))
    assert riga["stato"] == svc.STATO_SOSTITUITA and riga["sostituita_da_prova"] == "banca"
    # le altre restano dichiarate
    assert _run(db["mutui_rate_dichiarate"].count_documents({"stato": svc.STATO_DICHIARATA})) == 4
    # secondo giro: niente di nuovo
    assert client.post("/api/mutui/riconcilia").json()["data"]["dichiarazioni_sostituite_da_prova"] == 0


def test_la_prova_non_conforme_non_sostituisce_la_dichiarazione(db, client):
    anteprima = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={"data_limite": "2026-09-30"}).json()["data"]
    client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={
        "dry_run": False, "conferma": anteprima["frase_conferma"], "data_limite": "2026-09-30"})
    _addebita(db, _movimento("m2", "17/02/2021", 500.0))
    _, rate = _rate(client)
    assert rate[2]["stato"] == "Da verificare"
    assert client.post("/api/mutui/riconcilia").json()["data"]["dichiarazioni_sostituite_da_prova"] == 0
    assert _run(db["mutui_rate_dichiarate"].find_one({"numero_rata": 2}))["stato"] == svc.STATO_DICHIARATA


def test_le_rate_future_non_si_dichiarano(db, client):
    _run(db["mutui_piani_documentali"].update_one(
        {"numero_delibera": "905217466"},
        {"$push": {"rate": _rata(7, "17/12/2030")}}))
    anteprima = client.post(f"/api/mutui/{MUTUO}/rate-dichiarate", json={"data_limite": "2031-01-01"}).json()["data"]
    assert 7 in anteprima["future_escluse"] and 7 not in anteprima["numeri_rata"]
