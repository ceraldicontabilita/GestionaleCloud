import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import estratto_conto
from app.routers.prima_nota_module import banca, cassa
from app.services import riconciliazione_bancaria


def _run(coro):
    return asyncio.run(coro)


def test_versamento_manuale_crea_attesa_e_non_pagamento_confermato(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_versamento_attesa"]
        monkeypatch.setattr(cassa.Database, "get_db", staticmethod(lambda: db))

        result = await cassa.create_prima_nota_cassa({
            "data": "2026-06-10",
            "tipo": "uscita",
            "importo": 1234.56,
            "descrizione": "Versamento contanti",
            "categoria": "Versamento Banca",
        })

        movimento_cassa = await db["prima_nota_cassa"].find_one({"id": result["id"]})
        attese = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(10)
        assert len(attese) == 1
        assert movimento_cassa["tipo"] == "uscita"
        assert movimento_cassa["riconciliato"] is False
        assert movimento_cassa["in_attesa_estratto_conto"] is True
        assert attese[0]["tipo"] == "entrata"
        assert attese[0]["provvisorio"] is True
        assert attese[0]["riconciliato"] is False
        assert attese[0]["prima_nota_cassa_id"] == result["id"]
        assert not attese[0].get("estratto_conto_id")

    _run(scenario())


def test_estratto_conto_completa_attesa_senza_creare_doppione(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_versamento_riconciliato"]
        monkeypatch.setattr(cassa.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr(
            riconciliazione_bancaria.Database, "get_db", staticmethod(lambda: db)
        )
        monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))

        creato = await cassa.create_prima_nota_cassa({
            "data": "2026-06-10",
            "tipo": "uscita",
            "importo": 1234.56,
            "descrizione": "Versamento contanti",
            "categoria": "Versamento Banca",
        })
        await db["estratto_conto_movimenti"].insert_one({
            "id": "EC-versamento",
            "data": "2026-06-10",
            "tipo": "entrata",
            "importo": 1234.56,
            "descrizione_originale": "VERS. CONTANTI - TEST",
            "riconciliato": False,
        })

        result = await riconciliazione_bancaria.riconcilia_movimenti_banca()

        assert result["riconciliati_versamenti"] == 1
        movimenti_banca = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(10)
        assert len(movimenti_banca) == 1
        assert movimenti_banca[0]["estratto_conto_id"] == "EC-versamento"
        assert movimenti_banca[0]["provvisorio"] is False
        assert movimenti_banca[0]["riconciliato"] is True

        movimento_cassa = await db["prima_nota_cassa"].find_one({"id": creato["id"]})
        movimento_ec = await db["estratto_conto_movimenti"].find_one({"id": "EC-versamento"})
        assert movimento_cassa["riconciliato"] is True
        assert movimento_cassa["riconciliato_con_ec"] == "EC-versamento"
        assert movimento_ec["riconciliato"] is True
        assert movimento_ec["tipo_riconciliazione"] == "versamento"

        await banca._arricchisci_riconciliazione(db, movimenti_banca)
        assert movimenti_banca[0]["riconciliazione"]["verificata"] is True

    _run(scenario())


def test_storno_non_viene_scambiato_per_nuovo_versamento():
    descrizione = "STORNO VERS. CONTANTI - TEST"
    assert estratto_conto.is_storno_versamento(descrizione) is True
    assert estratto_conto.is_versamento_contanti(descrizione) is False
    assert estratto_conto.mappa_categoria_ec(None, descrizione) == "Storno versamento"
