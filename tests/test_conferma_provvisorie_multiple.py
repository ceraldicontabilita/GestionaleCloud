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
