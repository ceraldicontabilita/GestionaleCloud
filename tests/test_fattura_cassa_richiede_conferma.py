import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.invoices import fatture_upload


def test_metodo_fornitore_cassa_non_prova_il_pagamento(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["test_fattura_cassa_provvisoria"]
        await db["fornitori"].insert_one({
            "partita_iva": "01234567890",
            "metodo_pagamento": "cassa",
        })
        invoice = {
            "id": "fattura-cassa-1",
            "supplier_vat": "01234567890",
            "supplier_name": "FORNITORE CASSA",
            "invoice_number": "C-1",
            "invoice_date": "2026-08-13",
            "total_amount": 122.0,
        }

        async def vietato_cercare_estratto_conto(*args, **kwargs):
            raise AssertionError("una fattura cassa non deve cercare un match bancario")

        monkeypatch.setattr(
            fatture_upload,
            "find_ec_match_for_invoice",
            vietato_cercare_estratto_conto,
        )

        esito = await fatture_upload.auto_registra_prima_nota(
            db, invoice, "cassa"
        )

        assert esito is None
        assert await db["prima_nota_cassa"].count_documents({}) == 0
        assert invoice.get("pagato") is not True
        assert invoice.get("registrata_auto_da_metodo_fornitore") is not True

    asyncio.run(scenario())
