import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.invoices.fatture_upload import find_ec_match_for_invoice


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_banca_richiede_numero_importo_e_fornitore_insieme():
    async def scenario():
        db = MemorySheetsClient()["strict_bank_invoice"]
        base = {
            "tipo": "uscita",
            "importo": 122.00,
            "data": "2025-07-02",
            "riconciliato": False,
        }
        await db.estratto_conto_movimenti.insert_many([
            {**base, "id": "solo-nome", "descrizione": "BONIFICO CARTA PARTY SNC"},
            {**base, "id": "solo-numero", "descrizione": "SALDO FATTURA 120"},
            {**base, "id": "completo", "descrizione": "BONIFICO CARTA PARTY SNC SALDO FATTURA 120"},
        ])
        match = await find_ec_match_for_invoice(
            db, 122.00, "CARTA & PARTY SNC", "2025-06-30", "120"
        )
        assert match["id"] == "completo"
        assert match["match_tipo"] == "numero_fattura+importo_centesimo+fornitore"

    _run(scenario())


def test_banca_blocca_un_centesimo_di_differenza():
    async def scenario():
        db = MemorySheetsClient()["strict_bank_invoice_cent"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "cent-diff",
            "tipo": "uscita",
            "importo": 122.01,
            "data": "2025-07-02",
            "descrizione": "BONIFICO CARTA PARTY SNC SALDO FATTURA 120",
            "riconciliato": False,
        })
        match = await find_ec_match_for_invoice(
            db, 122.00, "CARTA & PARTY SNC", "2025-06-30", "120"
        )
        assert match is None

    _run(scenario())
