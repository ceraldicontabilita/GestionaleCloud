import asyncio
from datetime import datetime, timezone

from mongomock_motor import AsyncMongoMockClient

from app.services import paypal_api_sync as sync_module
from app.routers import paypal_api as api_router


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _api_row(balance_affecting="Y"):
    return {
        "transaction_info": {
            "transaction_id": "PAYPAL-OFFICIAL-1",
            "transaction_event_code": "T0006",
            "transaction_status": "S",
            "transaction_initiation_date": "2026-07-12T10:00:00Z",
            "transaction_amount": {"value": "-42.62", "currency_code": "EUR"},
            "invoice_id": "FT-PP-42",
            "bank_reference_id": "BANK-REF-42",
            "balance_affecting": balance_affecting,
        },
        "payer_info": {
            "email_address": "amministrazione@example.com",
            "payer_name": {"alternate_full_name": "FORNITORE TEST SRL"},
        },
    }


def test_extract_conserva_stato_evento_riferimento_banca_e_balance_affecting():
    doc = sync_module.extract_enriched_fields(_api_row())
    assert doc["transaction_status"] == "S"
    assert doc["transaction_event_code"] == "T0006"
    assert doc["bank_reference_id"] == "BANK-REF-42"
    assert doc["balance_affecting"] == "Y"
    assert doc["invoice_id_fornitore"] == "FT-PP-42"


def test_sync_scarto_riga_tecnica_duplicata_non_balance_affecting(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db

        async def fake_sync_period(start, end):
            return [_api_row("Y"), _api_row("N")]

        monkeypatch.setattr(sync_module.paypal_client, "sync_period", fake_sync_period)
        result = await sync_module.sync_paypal_period(
            db,
            datetime(2026, 7, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 31, tzinfo=timezone.utc),
        )

        assert result["total"] == 1
        assert await db.paypal_transactions.count_documents({}) == 1
        stored = await db.paypal_transactions.find_one({"transaction_id": "PAYPAL-OFFICIAL-1"})
        assert stored["balance_affecting"] == "Y"

    _run(scenario())


def test_riconcilia_intervallo_che_attraversa_due_anni(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        anni = []
        link_calls = []

        async def fake_links(_db, **kwargs):
            link_calls.append(kwargs)
            return {"associate": 0}

        async def fake_bank(_db, anno=None, applica=False):
            anni.append((anno, applica))
            return {"riconciliati": 1, "proposte": 1, "ambigui": 0}

        from app.routers import paypal_statements

        monkeypatch.setattr(api_router, "riprocessa_collegamenti_paypal", fake_links)
        monkeypatch.setattr(paypal_statements, "_auto_riconcilia", fake_bank)
        result = await api_router._riconcilia_intervallo_paypal(
            db,
            datetime(2025, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

        assert anni == [(2025, True), (2026, True)]
        assert len(link_calls) == 2
        assert set(result["banca"]["per_anno"]) == {"2025", "2026"}
        assert result["banca"]["riconciliati"] == 2
        assert result["banca"]["proposte"] == 2

    _run(scenario())
