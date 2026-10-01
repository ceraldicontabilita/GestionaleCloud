"""Conferma multipla delle fatture provvisorie: un giro solo, guardie intatte.

La richiesta e' nata dalla lentezza — una conferma alla volta, una ricarica a
clic. Il rischio dell'endpoint cumulativo pero' e' un altro: che per andare
veloce salti le guardie contabili della conferma singola. Questi test provano
che non le salta: passa dalle stesse funzioni, e una fattura rifiutata non
ferma le altre ne' sparisce in silenzio.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.prima_nota_module import sync as modulo
from app.routers.prima_nota_module.sync import conferma_provvisorie_multiple


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def registro(monkeypatch):
    """Sostituisce le due conferme singole con spie: qui si verifica il giro,
    non la scrittura contabile (coperta dai test della conferma singola)."""
    chiamate = {"cassa": [], "banca": []}

    async def _cassa(data):
        if data["fattura_id"] == "gia-pagata":
            raise HTTPException(status_code=409, detail="Gia' pagata")
        chiamate["cassa"].append(data)
        return {"success": True}

    async def _banca(data):
        chiamate["banca"].append(data)
        return {"success": True}

    monkeypatch.setattr(modulo, "conferma_fattura_provvisoria", _cassa)
    monkeypatch.setattr(modulo, "imposta_fattura_in_attesa_banca", _banca)
    return chiamate


def test_ogni_fattura_passa_dalla_conferma_singola(registro):
    esito = _run(conferma_provvisorie_multiple(
        {"fattura_ids": ["f1", "f2", "f3"], "metodo": "cassa"}))

    assert esito["riuscite"] == 3
    assert [c["fattura_id"] for c in registro["cassa"]] == ["f1", "f2", "f3"]
    # La spunta esplicita VALE come approvazione del metodo.
    assert all(c["approva_metodo_fattura"] is True for c in registro["cassa"])


def test_attendi_banca_usa_il_suo_percorso(registro):
    _run(conferma_provvisorie_multiple(
        {"fattura_ids": ["f1"], "metodo": "attendi_banca"}))

    assert registro["banca"] == [{"fattura_id": "f1"}]
    assert registro["cassa"] == []


def test_una_fattura_rifiutata_non_ferma_le_altre(registro):
    esito = _run(conferma_provvisorie_multiple(
        {"fattura_ids": ["f1", "gia-pagata", "f3"], "metodo": "cassa"}))

    assert esito["riuscite"] == 2
    assert esito["scartate"] == 1
    scarto = next(e for e in esito["esiti"] if not e["success"])
    assert scarto["fattura_id"] == "gia-pagata"
    assert "pagata" in scarto["detail"].lower()


def test_id_duplicati_contano_una_volta_sola(registro):
    _run(conferma_provvisorie_multiple(
        {"fattura_ids": ["f1", "f1", "f1"], "metodo": "cassa"}))
    assert len(registro["cassa"]) == 1


def test_duplicati_vengono_ridotti_prima_del_limite(registro):
    esito = _run(conferma_provvisorie_multiple(
        {"fattura_ids": ["f1"] * 201, "metodo": "cassa"}))
    assert esito["riuscite"] == 1
    assert len(registro["cassa"]) == 1


def test_fattura_ids_deve_essere_una_lista(registro):
    with pytest.raises(HTTPException) as err:
        _run(conferma_provvisorie_multiple(
            {"fattura_ids": "f1", "metodo": "cassa"}))
    assert "lista" in str(err.value.detail)


@pytest.mark.parametrize(("payload", "atteso"), [
    ({"fattura_ids": [], "metodo": "cassa"}, "Nessuna fattura"),
    ({"fattura_ids": ["f1"], "metodo": "banca"}, "Metodo non valido"),
    ({"fattura_ids": [f"f{i}" for i in range(201)], "metodo": "cassa"}, "Massimo 200"),
])
def test_richieste_malformate_si_fermano_subito(registro, payload, atteso):
    with pytest.raises(HTTPException) as err:
        _run(conferma_provvisorie_multiple(payload))
    assert atteso in str(err.value.detail)
    assert registro["cassa"] == [] and registro["banca"] == []


# ── metodo del fornitore dalla scheda di conferma, poi le sue altre fatture ───────────

from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from app.database import Collections, Database  # noqa: E402
from app.routers.prima_nota_module.sync import imposta_metodo_fornitore_provvisoria  # noqa: E402


def _fattura(id_, piva, numero="1"):
    return {"id": id_, "supplier_vat": piva, "invoice_number": numero, "metodo_pagamento": "sospesa"}


@pytest.fixture
def archivio(monkeypatch, registro):
    db = AsyncMongoMockClient()["metodo"]
    _run(db["invoices"].insert_many([
        _fattura("a", "IT111", "880"), _fattura("b", "IT111", "881"), _fattura(7, "IT111", "882"),
        _fattura("x", "IT999", "1"),
    ]))
    _run(db[Collections.SUPPLIERS].insert_many([
        {"id": "s1", "partita_iva": "IT111", "denominazione": "F.LLI SOMMELLA", "metodo_pagamento": "sospesa"},
        {"id": "s2", "partita_iva": "IT999", "denominazione": "ALTRO", "metodo_pagamento": "bonifico"},
    ]))
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    return db


def test_si_imposta_il_metodo_una_volta_e_si_spostano_le_altre_dello_stesso_fornitore(archivio, registro):
    esito = _run(imposta_metodo_fornitore_provvisoria(
        {"fattura_id": "a", "metodo": "cassa", "altre_fattura_ids": ["b", 7, "x"]}))
    fornitore = _run(archivio[Collections.SUPPLIERS].find_one({"id": "s1"}))
    assert fornitore["metodo_pagamento"] == "cassa" and fornitore["metodo_pagamento_dal"]   # con la sua data «dal»
    assert [c["fattura_id"] for c in registro["cassa"]] == ["a", "b", "7"]
    assert esito["altre_incluse"] == 2 and esito["altre_escluse"] == ["x"]      # un altro fornitore non si sposta mai
    assert esito["metodo_fornitore_cambiato"] is True and esito["riuscite"] == 3


def test_banca_manda_tutte_fra_i_pagamenti_attesi_in_banca(archivio, registro):
    _run(imposta_metodo_fornitore_provvisoria({"fattura_id": "a", "metodo": "banca", "altre_fattura_ids": ["b"]}))
    assert [c["fattura_id"] for c in registro["banca"]] == ["a", "b"] and registro["cassa"] == []
    assert _run(archivio[Collections.SUPPLIERS].find_one({"id": "s1"}))["metodo_pagamento"] == "banca"


def test_un_metodo_gia_impostato_diverso_non_si_cambia_di_nascosto(archivio, registro):
    with pytest.raises(HTTPException) as err:
        _run(imposta_metodo_fornitore_provvisoria({"fattura_id": "x", "metodo": "cassa"}))
    assert err.value.status_code == 409 and "bonifico" in err.value.detail
    assert registro["cassa"] == []
    # lo stesso senso (bonifico = banca) non e' un cambio: si sposta soltanto
    esito = _run(imposta_metodo_fornitore_provvisoria({"fattura_id": "x", "metodo": "banca"}))
    assert esito["metodo_fornitore_cambiato"] is False and esito["metodo_fornitore"] == "bonifico"
    # chi lo vuole cambiare lo dice
    _run(imposta_metodo_fornitore_provvisoria({"fattura_id": "x", "metodo": "cassa", "cambia_metodo": True}))
    assert _run(archivio[Collections.SUPPLIERS].find_one({"id": "s2"}))["metodo_pagamento"] == "cassa"


@pytest.mark.parametrize(("payload", "stato"), [
    ({"fattura_id": "a", "metodo": "assegno"}, 400),
    ({"metodo": "cassa"}, 400),
    ({"fattura_id": "nessuna", "metodo": "cassa"}, 404),
    ({"fattura_id": "a", "metodo": "cassa", "altre_fattura_ids": "b"}, 400),
])
def test_richieste_sbagliate_si_fermano_prima_di_toccare_il_fornitore(archivio, registro, payload, stato):
    with pytest.raises(HTTPException) as err:
        _run(imposta_metodo_fornitore_provvisoria(payload))
    assert err.value.status_code == stato
    assert _run(archivio[Collections.SUPPLIERS].find_one({"id": "s1"}))["metodo_pagamento"] == "sospesa"
