import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.invoices import fatture_upload


def test_metodo_fornitore_cassa_registra_pagamento_canonico(monkeypatch):
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
        from app.routers.prima_nota_module import sync as sync_mod
        monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: db))

        esito = await fatture_upload.auto_registra_prima_nota(
            db, invoice, "cassa"
        )

        assert esito["prima_nota_tipo"] == "cassa"
        assert await db["prima_nota_cassa"].count_documents({}) == 1
        assert esito["pagato"] is True
        assert esito["registrata_auto_da_metodo_fornitore"] is True

    asyncio.run(scenario())
