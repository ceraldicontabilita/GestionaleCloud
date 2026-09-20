import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers.invoices import fatture_upload


def test_metodo_fornitore_cassa_resta_da_confermare_fase0(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_fattura_cassa_provvisoria"]
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

        # Fase 0 (15/09/2026, PROMPT_CLAUDE_CODE_FASE_0.md punto 2): il ramo
        # cassa non scrive più prima_nota_cassa né marca pagato da solo —
        # resta "da confermare" finché non interviene una conferma esplicita.
        assert await db["prima_nota_cassa"].count_documents({}) == 0
        assert esito.get("pagato") is not True
        assert esito["stato_finanziario"] == "da_confermare_cassa"

    asyncio.run(scenario())
