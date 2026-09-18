import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.suppliers_module.base import _sincronizza_esclusione_cassa_banca


def _run(coro):
    return asyncio.run(coro)


def test_esclusione_rimuove_solo_movimenti_auto_e_conserva_dati_fiscali():
    async def scenario():
        db = MemorySheetsClient()["test_esclusione_finanziaria"]
        supplier = {"partita_iva": "01234567890"}
        await db["invoices"].insert_one({
            "id": "fatt-1",
            "supplier_vat": "01234567890",
            "imponibile": 100.0,
            "iva": 22.0,
            "total_amount": 122.0,
            "pagato": True,
            "paid": True,
            "stato_pagamento": "pagata",
            "prima_nota_id": "mov-auto",
            "prima_nota_tipo": "banca",
            "registrata_auto_da_metodo_fornitore": True,
        })
        await db["prima_nota_banca"].insert_many([
            {
                "id": "mov-auto",
                "fattura_id": "fatt-1",
                "fornitore_piva": "01234567890",
                "source": "auto_metodo_fornitore",
                "riconciliato": False,
            },
            {
                "id": "mov-reale",
                "fattura_id": "fatt-1",
                "fornitore_piva": "01234567890",
                "source": "riconciliazione_ec",
                "riconciliato": True,
            },
        ])

        esito = await _sincronizza_esclusione_cassa_banca(db, supplier, True)
        fattura = await db["invoices"].find_one({"id": "fatt-1"}, {"_id": 0})

        assert esito["movimenti_auto_rimossi"] == 1
        assert await db["prima_nota_banca"].count_documents({}) == 1
        assert await db["prima_nota_banca"].find_one({"id": "mov-reale"}) is not None
        assert fattura["imponibile"] == 100.0
        assert fattura["iva"] == 22.0
        assert fattura["esclusa_da_cassa_banca"] is True
        assert fattura["registrazione_fiscale_mantenuta"] is True
        assert fattura["stato_finanziario"] == "esclusa_cassa_banca"
        assert "prima_nota_id" not in fattura
        assert "stato_pagamento" not in fattura

    _run(scenario())


def test_riattivazione_rimette_la_fattura_nel_flusso_senza_toccare_iva():
    async def scenario():
        db = MemorySheetsClient()["test_riattivazione_finanziaria"]
        supplier = {"partita_iva": "01234567890"}
        await db["invoices"].insert_one({
            "id": "fatt-2",
            "supplier_vat": "01234567890",
            "iva": 11.0,
            "esclusa_da_cassa_banca": True,
            "stato_finanziario": "esclusa_cassa_banca",
        })

        await _sincronizza_esclusione_cassa_banca(db, supplier, False)
        fattura = await db["invoices"].find_one({"id": "fatt-2"}, {"_id": 0})

        assert fattura["esclusa_da_cassa_banca"] is False
        assert fattura["stato_finanziario"] == "da_registrare"
        assert fattura["iva"] == 11.0

    _run(scenario())
