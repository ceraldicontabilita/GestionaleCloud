"""PayPal pagato con addebito in conto: il titolare collega la transazione al movimento bancario."""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.routers import paypal_statements as r


def _run(coro):
    return asyncio.run(coro)


def _db(movimenti, transazioni):
    db = AsyncMongoMockClient()["t"]

    async def riempi():
        if movimenti:
            await db[r.COLL_ESTRATTO_CONTO].insert_many([dict(m) for m in movimenti])
        await db[r.COLL_PAYPAL_TRANSACTIONS].insert_many([dict(t) for t in transazioni])

    _run(riempi())
    return db


TX = {"transaction_id": "TX1", "data": "2026-09-12", "lordo": -20.99, "currency": "EUR",
      "tipo": "pagamento_web", "nome_controparte": "Spotify AB"}


def _mov(id_, data, importo, descr="ADDEBITO DIRETTO SPOTIFY", **extra):
    return {"id": id_, "data": data, "importo": importo, "descrizione": descr, "tipo": "uscita", **extra}


def test_candidati_importo_al_centesimo_uscita_non_collegati_e_vicini_nel_tempo():
    db = _db([
        _mov("M-OK", "2026-09-14", -20.99),                       # senza «PayPal» nella causale
        _mov("M-PP", "2026-09-13", -20.99, descr="PAYPAL EUROPE"),
        _mov("M-IMPORTO", "2026-09-14", -20.98),
        _mov("M-LONTANO", "2026-11-14", -20.99),
        _mov("M-GIA", "2026-09-14", -20.99, riconciliato=True),
        _mov("M-ENTRATA", "2026-09-14", 20.99, tipo="entrata"),
    ], [TX])
    esito = _run(r._candidati_banca(db, TX))
    assert esito["importo_eur"] == "20.99"
    assert [c["id"] for c in esito["candidati"]] == ["M-PP", "M-OK"]       # il piu' vicino prima
    assert esito["candidati"][0]["citata_paypal"] is True and esito["candidati"][1]["citata_paypal"] is False


def test_in_valuta_estera_serve_la_gamba_in_euro_altrimenti_nessun_candidato():
    usd = {"transaction_id": "TX2", "data": "2026-08-20", "lordo": -184.31, "currency": "USD"}
    db = _db([_mov("M1", "2026-08-21", -184.31)], [usd])
    esito = _run(r._candidati_banca(db, usd))
    assert esito["candidati"] == [] and "euro" in esito["motivo"]
    gamba = {"transaction_id": "G1", "paypal_reference_id": "TX2", "tipo": "T0200", "currency": "EUR",
             "lordo": -158.40, "data": "2026-08-20"}
    db2 = _db([_mov("M2", "2026-08-21", -158.40)], [usd, gamba])
    assert [c["id"] for c in _run(r._candidati_banca(db2, usd))["candidati"]] == ["M2"]


@pytest.fixture(autouse=True)
def _db_corrente(monkeypatch):
    # Ogni test costruisce il suo db: la rotta lo legge da Database.get_db().
    from app.database import Database
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _CORRENTE["db"]))
    yield


_CORRENTE = {}


def test_rotta_collega_applica_e_rifiuta_movimento_non_candidato_o_gia_collegata():
    db = _db([_mov("M-OK", "2026-09-14", -20.99), _mov("M-ALTRO", "2026-09-14", -5.00)], [TX])
    _CORRENTE["db"] = db
    with pytest.raises(HTTPException) as e:
        _run(r.collega_banca_transazione("TX1", {"movimento_id": "M-ALTRO"}))
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        _run(r.collega_banca_transazione("TX1", {}))
    assert e.value.status_code == 400

    esito = _run(r.collega_banca_transazione("TX1", {"movimento_id": "M-OK"}))
    assert esito["success"] is True
    tx = _run(db[r.COLL_PAYPAL_TRANSACTIONS].find_one({"transaction_id": "TX1"}))
    mov = _run(db[r.COLL_ESTRATTO_CONTO].find_one({"id": "M-OK"}))
    assert tx["movimento_banca_id"] == "M-OK" and tx["riconciliazione_banca_manuale"] is True
    assert mov["paypal_transaction_id"] == "TX1" and mov["tipo_riconciliazione"] == "paypal_scelto_dal_titolare"
    with pytest.raises(HTTPException) as e:
        _run(r.collega_banca_transazione("TX1", {"movimento_id": "M-OK"}))
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        _run(r.candidati_banca_transazione("NON-ESISTE"))
    assert e.value.status_code == 404
