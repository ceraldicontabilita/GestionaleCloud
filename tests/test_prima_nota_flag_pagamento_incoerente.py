import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import manutenzione
from app.services.collaudo_invarianti import check_prima_nota_link_rotti
from app.services.prima_nota_integrity import (
    fatture_senza_pagamento_contabile_confermato,
)


def test_paid_alias_e_id_laterale_sono_rilevati_e_ripristinati(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_prima_nota_flag_incoerente"]
        monkeypatch.setattr(
            manutenzione.Database, "get_db", staticmethod(lambda: db)
        )
        await db["invoices"].insert_one({
            "id": "fattura-1",
            "invoice_number": "F-1",
            "total_amount": 125.5,
            "pagato": False,
            "paid": True,
            "stato_pagamento": "da_pagare",
            "payment_status": "paid",
            "prima_nota_banca_id": "pn-cancellata",
            "data_pagamento": "2026-08-01",
        })
        await db["prima_nota_banca"].insert_one({
            "id": "pn-cancellata",
            "fattura_id": "fattura-1",
            "status": "deleted",
            "data": "2026-08-01",
        })

        check = await check_prima_nota_link_rotti(db)
        assert check["violazioni"] == 1

        anteprima = await manutenzione.ripristina_fatture_con_movimento_cancellato(
            dry_run=True
        )
        assert anteprima["da_ripristinare"] == 1
        assert (await db["invoices"].find_one({"id": "fattura-1"}))["paid"] is True

        applicata = await manutenzione.ripristina_fatture_con_movimento_cancellato(
            dry_run=False
        )
        assert applicata["ripristinate"] == 1
        fattura = await db["invoices"].find_one({"id": "fattura-1"})
        assert fattura["pagato"] is False
        assert fattura["paid"] is False
        assert fattura["payment_status"] == "open"
        assert fattura["importo_pagato"] == 0
        assert fattura["importo_residuo"] == 125.5
        assert fattura.get("prima_nota_banca_id") is None
        assert fattura.get("data_pagamento") is None

        check_finale = await check_prima_nota_link_rotti(db)
        assert check_finale["violazioni"] == 0

    asyncio.run(scenario())


def test_fattura_paid_con_movimento_attivo_non_viene_toccata(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_prima_nota_flag_coerente"]
        monkeypatch.setattr(
            manutenzione.Database, "get_db", staticmethod(lambda: db)
        )
        await db["invoices"].insert_one({
            "id": "fattura-2",
            "total_amount": 80,
            "paid": True,
            "prima_nota_cassa_id": "pn-viva",
        })
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-viva",
            "fattura_id": "fattura-2",
            "data": "2026-08-02",
        })

        check = await check_prima_nota_link_rotti(db)
        assert check["violazioni"] == 0
        esito = await manutenzione.ripristina_fatture_con_movimento_cancellato(
            dry_run=False
        )
        assert esito["ripristinate"] == 0
        assert (await db["invoices"].find_one({"id": "fattura-2"}))["paid"] is True

    asyncio.run(scenario())


def test_provvisoria_include_banca_senza_estratto_e_link_cancellato():
    async def scenario():
        db = AsyncMongoMockClient()["test_provvisoria_evidenza"]
        fatture = [
            {"id": "cassa", "prima_nota_cassa_id": "pn-cassa"},
            {"id": "banca-auto", "prima_nota_banca_id": "pn-auto", "paid": True},
            {"id": "banca-ec", "prima_nota_banca_id": "pn-ec", "paid": True},
            {"id": "cancellata", "prima_nota_banca_id": "pn-del", "paid": True},
        ]
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-cassa", "fattura_id": "cassa",
        })
        await db["prima_nota_banca"].insert_many([
            {"id": "pn-auto", "fattura_id": "banca-auto"},
            {"id": "pn-ec", "fattura_id": "banca-ec", "estratto_conto_id": "ec-1"},
            {"id": "pn-del", "fattura_id": "cancellata", "status": "deleted"},
        ])

        risultato = await fatture_senza_pagamento_contabile_confermato(db, fatture)
        assert {f["id"] for f in risultato} == {"banca-auto", "cancellata"}

    asyncio.run(scenario())


def test_pagamento_parziale_mantiene_aperto_solo_il_residuo():
    async def scenario():
        db = AsyncMongoMockClient()["test_provvisoria_residuo"]
        fattura = {
            "id": "fattura-parziale",
            "total_amount": 100.0,
            "prima_nota_cassa_id": "pn-cassa-40",
        }
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-cassa-40",
            "fattura_id": "fattura-parziale",
            "importo": 40.0,
            "status": "active",
        })

        aperte = await fatture_senza_pagamento_contabile_confermato(
            db, [fattura]
        )
        assert len(aperte) == 1
        assert aperte[0]["_importo_pagato_confermato"] == 40.0
        assert aperte[0]["_importo_residuo"] == 60.0

        # Una riga Banca senza estratto conto non chiude il residuo.
        await db["prima_nota_banca"].insert_one({
            "id": "pn-banca-senza-evidenza",
            "fattura_id": "fattura-parziale",
            "importo": 60.0,
            "status": "active",
        })
        ancora_aperte = await fatture_senza_pagamento_contabile_confermato(
            db, [fattura]
        )
        assert ancora_aperte[0]["_importo_residuo"] == 60.0

        await db["prima_nota_banca"].insert_one({
            "id": "pn-banca-60",
            "fattura_id": "fattura-parziale",
            "importo": 60.0,
            "estratto_conto_id": "ec-60",
            "status": "active",
        })
        saldate = await fatture_senza_pagamento_contabile_confermato(
            db, [fattura]
        )
        assert saldate == []

    asyncio.run(scenario())
