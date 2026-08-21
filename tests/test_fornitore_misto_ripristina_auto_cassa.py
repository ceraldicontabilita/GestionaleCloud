import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.prima_nota_module import manutenzione


def test_fornitore_misto_rimette_provvisoria_solo_auto_cassa(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["test_fornitore_misto"]
        monkeypatch.setattr(
            manutenzione.Database, "get_db", staticmethod(lambda: db)
        )
        await db["fornitori"].insert_one({
            "id": "supplier-1", "partita_iva": "00000000001",
            "metodo_pagamento": "misto",
        })
        await db["invoices"].insert_many([
            {
                "id": "invoice-auto", "supplier_vat": "00000000001",
                "invoice_number": "AUTO-1", "supplier_name": "FORNITORE TEST",
                "pagato": True, "paid": True,
                "stato_pagamento": "pagata", "payment_status": "paid",
                "importo_pagato": 100, "importo_residuo": 0,
                "data_pagamento": "2026-06-15",
                "prima_nota_id": "pn-auto", "prima_nota_tipo": "cassa",
                "prima_nota_cassa_id": "pn-auto",
                "registrata_auto_da_metodo_fornitore": True,
            },
            {
                "id": "invoice-manuale", "supplier_vat": "00000000001",
                "invoice_number": "MAN-1", "supplier_name": "FORNITORE TEST",
                "pagato": True, "stato_pagamento": "pagata",
                "prima_nota_id": "pn-manuale", "prima_nota_tipo": "cassa",
            },
        ])
        await db["prima_nota_cassa"].insert_many([
            {
                "id": "pn-auto", "fattura_id": "invoice-auto",
                "data": "2026-06-15", "tipo": "uscita", "importo": 100,
                "source": "fattura_pagata",
            },
            {
                "id": "pn-manuale", "fattura_id": "invoice-manuale",
                "data": "2026-06-16", "tipo": "uscita", "importo": 200,
                "source": "fattura_pagata",
            },
        ])

        esito = await manutenzione.ripristina_provvisori_metodo_errato(
            dry_run=False, anno=2026, banca_non_riconciliate=True, _admin={}
        )

        assert esito["corretti"] >= 1
        auto = await db["invoices"].find_one({"id": "invoice-auto"})
        manuale = await db["invoices"].find_one({"id": "invoice-manuale"})
        pn_auto = await db["prima_nota_cassa"].find_one({"id": "pn-auto"})
        pn_manuale = await db["prima_nota_cassa"].find_one({"id": "pn-manuale"})
        assert auto["pagato"] is False
        assert auto["paid"] is False
        assert auto["stato_pagamento"] == "da_pagare"
        assert auto["payment_status"] == "open"
        assert auto["importo_pagato"] == 0
        assert auto["prima_nota_id"] is None
        assert auto.get("prima_nota_cassa_id") is None
        assert auto.get("prima_nota_banca_id") is None
        assert auto.get("data_pagamento") is None
        assert pn_auto["status"] == "deleted"
        assert manuale["pagato"] is True
        assert pn_manuale.get("status") != "deleted"

    asyncio.run(scenario())
