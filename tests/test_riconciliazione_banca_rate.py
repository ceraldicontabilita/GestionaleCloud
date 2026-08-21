import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.services.riconciliazione_bancaria import _applica_pagamento_banca


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_bonifici_rateali_aggiornano_quota_e_non_totale_documento():
    async def scenario():
        db = MemorySheetsClient().db
        await db.invoices.insert_one({
            "id": "fatt-rate-banca", "invoice_number": "TEST-RATE-BANCA",
            "invoice_date": "2026-02-06", "supplier_vat": "00000000000",
            "supplier_name": "FORNITORE TEST SRL", "total_amount": 12000.0,
            "importo_pagato": 0.0, "importo_residuo": 12000.0,
            "payment_status": "open", "pagato": False,
            "pagamento_rate": [{"importo": "3000.00"} for _ in range(4)],
        })

        for idx in range(1, 5):
            fattura = await db.invoices.find_one({"id": "fatt-rate-banca"})
            await _applica_pagamento_banca(
                db, fattura, "Bonifico", f"2026-0{idx + 2}-10", f"ec-rata-{idx}",
                15, "2026-07-20T00:00:00+00:00", "test_rate",
                importo_pagamento=3000.0,
            )
            aggiornata = await db.invoices.find_one({"id": "fatt-rate-banca"}, {"_id": 0})
            assert aggiornata["importo_pagato"] == 3000.0 * idx
            assert aggiornata["importo_residuo"] == 12000.0 - 3000.0 * idx
            assert aggiornata["payment_status"] == ("paid" if idx == 4 else "partial")

        assert await db.prima_nota_banca.count_documents({}) == 4
        assert [r["importo"] async for r in db.prima_nota_banca.find({})] == [3000.0] * 4

    _run(scenario())


def test_stessa_evidenza_bancaria_non_applica_due_volte_la_rata():
    async def scenario():
        db = MemorySheetsClient().db
        await db.invoices.insert_one({
            "id": "fatt-idem", "invoice_number": "TEST-IDEM",
            "total_amount": 6000.0, "importo_pagato": 0.0,
            "payment_status": "open", "pagato": False,
        })
        fattura = await db.invoices.find_one({"id": "fatt-idem"})
        args = (db, fattura, "Bonifico", "2026-05-10", "ec-unica", 15,
                "2026-07-20T00:00:00+00:00", "test_idem")
        await _applica_pagamento_banca(*args, importo_pagamento=3000.0)
        fattura = await db.invoices.find_one({"id": "fatt-idem"})
        args = (db, fattura, "Bonifico", "2026-05-10", "ec-unica", 15,
                "2026-07-20T00:00:00+00:00", "test_idem")
        await _applica_pagamento_banca(*args, importo_pagamento=3000.0)

        aggiornata = await db.invoices.find_one({"id": "fatt-idem"}, {"_id": 0})
        assert aggiornata["importo_pagato"] == 3000.0
        assert aggiornata["payment_status"] == "partial"
        assert await db.prima_nota_banca.count_documents({}) == 1

    _run(scenario())
