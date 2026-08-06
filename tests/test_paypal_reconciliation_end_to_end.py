import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.paypal_reconciliation_links import (
    associa_transazione_univoca,
    collega_fattura_paypal_appena_importata,
    finalizza_transazione_paypal_se_completa,
    riprocessa_collegamenti_paypal,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _invoice(invoice_id="INV-DB-1"):
    return {
        "id": invoice_id,
        "invoice_number": "FT-2026-42",
        "invoice_date": "2026-07-10",
        "supplier_name": "FORNITORE PAYPAL SRL",
        "supplier_vat": "05851861210",
        "total_amount": 100.0,
        "divisa": "EUR",
        "pagato": False,
        "stato_pagamento": "da_pagare",
        "importo_pagato": 0.0,
    }


def _transaction(transaction_id="PAY-TX-1"):
    return {
        "transaction_id": transaction_id,
        "paypal_account_id": "PAYPAL-ACCOUNT-1",
        "invoice_id_fornitore": "FT-2026-42",
        "nome_controparte": "FORNITORE PAYPAL SRL",
        "importo": -100.0,
        "currency": "EUR",
        "data": "2026-07-12",
        "transaction_status": "S",
        "balance_affecting": "Y",
    }


async def _seed_identity(db):
    await db.fornitori.insert_one({
        "id": "SUP-1",
        "paypal_account_id": "PAYPAL-ACCOUNT-1",
        "ragione_sociale": "FORNITORE PAYPAL SRL",
        "piva": "05851861210",
    })


def test_importo_api_senza_lordo_collega_sui_due_lati_ma_attende_banca():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one(_invoice())
        await db.paypal_transactions.insert_one(_transaction())

        result = await riprocessa_collegamenti_paypal(db)

        assert result["associate"] == 1
        assert result["finalizzate"] == 0
        transaction = await db.paypal_transactions.find_one({"transaction_id": "PAY-TX-1"})
        invoice = await db.invoices.find_one({"id": "INV-DB-1"})
        assert transaction["fattura_associata"]["fattura_id"] == "INV-DB-1"
        assert invoice["paypal_transaction_id"] == "PAY-TX-1"
        assert invoice["paypal_transaction_ids"] == ["PAY-TX-1"]
        assert invoice["stato_finanziario"] == "in_attesa_estratto_conto"
        assert invoice["pagato"] is False
        assert await db.prima_nota_banca.count_documents({}) == 0

    _run(scenario())


def test_estratto_prima_fattura_dopo_chiude_catena_e_prima_nota_una_sola_volta():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        transaction = {
            **_transaction(),
            "riconciliato_banca": True,
            "riconciliato_con_estratto_banca": True,
            "movimento_banca_id": "EC-PAY-1",
            "estratto_conto_movimento_id": "EC-PAY-1",
            "riconciliazione_banca_score": 20,
        }
        await db.paypal_transactions.insert_one(transaction)
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-PAY-1",
            "data": "2026-07-14",
            "tipo": "uscita",
            "importo": -100.0,
            "descrizione": "ADDEBITO DIRETTO PAYPAL EUROPE",
            "riconciliato": True,
            "paypal_transaction_id": "PAY-TX-1",
        })
        invoice = _invoice()
        await db.invoices.insert_one(invoice)

        first = await collega_fattura_paypal_appena_importata(db, invoice)
        refreshed = await db.invoices.find_one({"id": "INV-DB-1"})
        second = await finalizza_transazione_paypal_se_completa(db, "PAY-TX-1")

        assert first["collegata"] is True
        assert first["finalizzazione"]["finalizzata"] is True
        assert second["finalizzata"] is True
        assert refreshed["pagato"] is True
        assert refreshed["stato_finanziario"] == "riconciliato"
        assert refreshed["paypal_movimento_banca_id"] == "EC-PAY-1"
        assert await db.prima_nota_banca.count_documents({}) == 1

    _run(scenario())


def test_fattura_prima_estratto_dopo_finalizza_appena_arriva_la_banca():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one(_invoice())
        transaction = _transaction()
        await db.paypal_transactions.insert_one(transaction)
        linked = await associa_transazione_univoca(db, transaction)
        assert linked["collegata"] is True

        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-PAY-LATE", "data": "2026-07-15", "tipo": "uscita",
            "importo": -100.0, "riconciliato": True,
            "paypal_transaction_id": "PAY-TX-1",
        })
        await db.paypal_transactions.update_one({"transaction_id": "PAY-TX-1"}, {"$set": {
            "riconciliato_banca": True,
            "movimento_banca_id": "EC-PAY-LATE",
            "estratto_conto_movimento_id": "EC-PAY-LATE",
        }})

        result = await finalizza_transazione_paypal_se_completa(db, "PAY-TX-1")
        invoice = await db.invoices.find_one({"id": "INV-DB-1"})
        assert result["finalizzata"] is True
        assert invoice["pagato"] is True
        assert await db.prima_nota_banca.count_documents({}) == 1

    _run(scenario())


def test_stessa_fattura_non_puo_essere_riutilizzata_da_due_transazioni():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        invoice = _invoice()
        first_tx = _transaction("PAY-FIRST")
        second_tx = _transaction("PAY-SECOND")
        await db.invoices.insert_one(invoice)
        await db.paypal_transactions.insert_many([first_tx, second_tx])

        first = await associa_transazione_univoca(db, first_tx)
        second = await associa_transazione_univoca(db, second_tx)

        assert first["collegata"] is True
        assert second["collegata"] is False
        assert second["motivo"] == "fattura_gia_collegata_ad_altra_transazione"

    _run(scenario())


def test_pending_reversed_e_righe_non_balance_affecting_non_vengono_associate():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one(_invoice())
        rows = [
            {**_transaction("PAY-PENDING"), "transaction_status": "P"},
            {**_transaction("PAY-REVERSED"), "transaction_status": "V"},
            {**_transaction("PAY-NO-BALANCE"), "balance_affecting": "N"},
        ]
        await db.paypal_transactions.insert_many(rows)

        result = await riprocessa_collegamenti_paypal(db)

        assert result["associate"] == 0
        assert await db.paypal_transactions.count_documents({
            "fattura_associata": {"$exists": True},
        }) == 0

    _run(scenario())


def test_fattura_gia_pagata_da_altra_evidenza_non_viene_riutilizzata():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one({
            **_invoice(), "pagato": True, "stato_pagamento": "pagata",
            "riconciliato_con_ec": "EC-ALTRO",
        })
        transaction = _transaction()
        await db.paypal_transactions.insert_one(transaction)

        result = await associa_transazione_univoca(db, transaction)

        assert result["collegata"] is False
        assert result["motivo"] == "fattura_gia_collegata_ad_altra_transazione"
        stored = await db.paypal_transactions.find_one({"transaction_id": "PAY-TX-1"})
        assert "fattura_associata" not in stored

    _run(scenario())
