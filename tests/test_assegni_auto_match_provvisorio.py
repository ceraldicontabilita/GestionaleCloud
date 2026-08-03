import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.bank.assegni_auto_match import _apply_match


def test_conferma_proposta_collega_ma_non_crea_banca_ne_segna_pagata():
    async def scenario():
        db = AsyncMongoMockClient()["assegni_auto_match_provvisorio"]
        assegno = {
            "id": "ass-1",
            "numero": "0208771000-01",
            "importo": 100.00,
            "beneficiario": "FORNITORE PROVA SRL",
            "fornitore_piva": "01234567890",
            "stato": "compilato",
        }
        fattura = {
            "id": "fatt-1",
            "invoice_number": "1/2026",
            "total_amount": 100.00,
            "importo_pagato": 0.0,
            "importo_residuo": 100.00,
            "payment_status": "open",
            "pagato": False,
            "supplier_vat": "01234567890",
            "supplier_name": "FORNITORE PROVA SRL",
            "_residuo": 100.00,
        }
        await db.assegni.insert_one(dict(assegno))
        await db.invoices.insert_one(dict(fattura))

        result = await _apply_match(
            db, [assegno], [fattura], livello="L1", dry_run=False
        )

        assegno_db = await db.assegni.find_one({"id": "ass-1"}, {"_id": 0})
        fattura_db = await db.invoices.find_one({"id": "fatt-1"}, {"_id": 0})
        assert result["movimenti_banca"] == 0
        assert await db.prima_nota_banca.count_documents({}) == 0
        assert assegno_db["stato"] == "assegnato"
        assert fattura_db["pagato"] is False
        assert fattura_db["importo_pagato"] == 0.0
        assert fattura_db["stato_finanziario"] == "in_attesa_estratto_conto"
        assert fattura_db["assegni_collegati"][0]["banca_confermata"] is False

    asyncio.run(scenario())
