import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import assegni as assegni_router


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_ricostruzione_assegni_e_solo_anteprima(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_ricostruzione_assegni"]
        monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))
        await db.assegni.insert_one({
            "id": "ASS-1", "importo": 120.0, "beneficiario": "",
            "movimento_estratto_conto_id": "EC-1",
        })
        await db.assegni.insert_one({
            "id": "ASS-VUOTO", "importo": None, "beneficiario": "",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-1", "beneficiario": "FORNITORE SICURO SRL",
        })
        await db.invoices.insert_one({
            "id": "F-1", "invoice_number": "1/2026", "total_amount": 120.0,
            "supplier_name": "FORNITORE SICURO SRL",
        })

        result = await assegni_router.ricostruisci_dati_assegni(dry_run=True)

        assert result["dry_run"] is True
        assert result["nessuna_modifica_applicata"] is True
        assert result["assegni_processati"] == 2
        assert result["beneficiari_trovati"] == 1
        assert result["fatture_associate"] == 1
        assegno = await db.assegni.find_one({"id": "ASS-1"}, {"_id": 0})
        assert assegno["beneficiario"] == ""
        assert "fattura_id" not in assegno
        assegno_vuoto = await db.assegni.find_one({"id": "ASS-VUOTO"}, {"_id": 0})
        assert assegno_vuoto["importo"] is None

    _run(scenario())


def test_ricostruzione_diretta_e_disabilitata(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_ricostruzione_bloccata"]
        monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await assegni_router.ricostruisci_dati_assegni(dry_run=False)
        assert exc.value.status_code == 400

    _run(scenario())
