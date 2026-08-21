import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.routers.bank import assegni as router


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_manual_check_payment_rejects_credit_note(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["allocation_credit_note"]
        await db.assegni.insert_one({"id": "a1", "numero": "0001", "importo": 100.0})
        await db.invoices.insert_one({"id": "nc1", "invoice_number": "NC-1", "tipo_documento": "TD04", "total_amount": 100.0})
        monkeypatch.setattr(router.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await router.collega_fatture_assegno(
                "a1", router.FattureCollegateIn(fatture=[router.FatturaQuotaIn(fattura_id="nc1", quota=100.0)])
            )
        assert exc.value.status_code == 409
        assert "nota di credito" in exc.value.detail
        saved = await db.invoices.find_one({"id": "nc1"}, {"_id": 0})
        assert not saved.get("assegni_collegati")

    run(scenario())


def test_reprocess_endpoint_is_read_only_without_confirmation(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["allocation_preview"]
        monkeypatch.setattr(router.Database, "get_db", staticmethod(lambda: db))
        result = await router.riprocessa_collegamenti_assegni(anno=2026, limit=100)
        assert result["preview"] is True
        assert result["conferma_richiesta"] is True
        assert "nessun dato" in result["message"]

    run(scenario())
