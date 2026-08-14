import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.paypal_reconciliation_links import (
    associa_transazione_univoca,
    collega_fattura_paypal_appena_importata,
    finalizza_transazione_paypal_se_completa,
    riprocessa_collegamenti_paypal,
)
from app.routers.paypal_statements import _auto_riconcilia


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
        relations = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        assert [row["relation_type"] for row in relations] == [
            "allocates_paypal_payment"
        ]

    _run(scenario())


def test_barbetta_senza_numero_fattura_collega_per_nome_importo_data_univoci():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_one({
            **_invoice("INV-BARBETTA"),
            "invoice_number": "5874-2026-FE",
            "invoice_date": "2026-08-05",
            "supplier_name": "",
            "fornitore_ragione_sociale": "BARBETTA RICAMBI BAGNO di BARBETTA ROBERTO",
            "supplier_vat": "02521360699",
            "total_amount": 23.10,
        })
        tx = {
            **_transaction("4817044P"),
            "invoice_id_fornitore": "",
            "paypal_account_id": "",
            "nome_controparte": "Barbetta Roberto",
            "importo": -23.10,
            "data": "2026-08-05",
        }
        await db.paypal_transactions.insert_one(tx)

        result = await associa_transazione_univoca(db, tx)

        assert result["collegata"] is True
        assert result["fattura_id"] == "INV-BARBETTA"
        assert result["fattura_associata"]["match"] == "fornitore_importo_data_univoci"
        assert "denominazione_fornitore" in result["fattura_associata"]["evidenze"]
        assert "data_entro_120_giorni" in result["fattura_associata"]["evidenze"]

    _run(scenario())


def test_paypal_senza_numero_non_sceglie_tra_due_fatture_compatibili():
    async def scenario():
        db = AsyncMongoMockClient().db
        base = {
            **_invoice(), "supplier_name": "Barbetta Roberto",
            "total_amount": 23.10, "invoice_date": "2026-08-05",
        }
        await db.invoices.insert_many([
            {**base, "id": "INV-A", "invoice_number": "A"},
            {**base, "id": "INV-B", "invoice_number": "B"},
        ])
        tx = {
            **_transaction("PAY-AMB"), "invoice_id_fornitore": "",
            "paypal_account_id": "", "nome_controparte": "Barbetta Roberto",
            "importo": -23.10, "data": "2026-08-05",
        }

        result = await associa_transazione_univoca(db, tx)

        assert result == {"collegata": False, "motivo": "fatture_ambigue", "candidati": 2}

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
        assert refreshed["riconciliato"] is True
        assert refreshed["riconciliato_con_ec"] == "EC-PAY-1"
        assert await db.prima_nota_banca.count_documents({}) == 1
        operation_id = "paypal:PAY-TX-1"
        assert refreshed["payment_operation_id"] == operation_id
        stored_tx = await db.paypal_transactions.find_one({"transaction_id": "PAY-TX-1"})
        stored_bank = await db.estratto_conto_movimenti.find_one({"id": "EC-PAY-1"})
        stored_prima_nota = await db.prima_nota_banca.find_one({})
        assert stored_tx["payment_operation_id"] == operation_id
        assert stored_bank["payment_operation_id"] == operation_id
        assert stored_prima_nota["payment_operation_id"] == operation_id
        relations = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        assert {row["relation_type"] for row in relations} == {
            "allocates_paypal_payment", "settles_paypal_transaction",
            "proves_invoice_payment",
        }

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


def test_finalizzazione_paypal_archivia_la_proiezione_ec_duplicata():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one(_invoice())
        await db.paypal_transactions.insert_one({
            **_transaction(),
            "fattura_associata": {"fattura_id": "INV-DB-1"},
            "riconciliato_banca": True,
            "movimento_banca_id": "EC-PAY-DUP",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-PAY-DUP", "data": "2026-07-14", "tipo": "uscita",
            "importo": -100.0, "riconciliato": True,
            "paypal_transaction_id": "PAY-TX-1",
        })
        await db.prima_nota_banca.insert_one({
            "id": "PN-RAW", "data": "2026-07-14", "tipo": "uscita",
            "importo": 100.0, "categoria": "Pagamento PayPal",
            "source": "proiezione_semantica_ec",
            "estratto_conto_id": "EC-PAY-DUP",
        })
        await db.prima_nota_banca.insert_one({
            "id": "PN-DOC", "data": "2026-07-14", "tipo": "uscita",
            "importo": 100.0, "categoria": "Fatture",
            "source": "riconciliazione_paypal_end_to_end",
            "estratto_conto_id": "EC-PAY-DUP", "fattura_id": "INV-DB-1",
            "invoice_id": "INV-DB-1",
        })

        result = await finalizza_transazione_paypal_se_completa(db, "PAY-TX-1")

        assert result["finalizzata"] is True
        attive = await db.prima_nota_banca.find({
            "status": {"$nin": ["deleted", "archived"]},
        }).to_list(length=10)
        assert len(attive) == 1
        assert attive[0]["fattura_id"] == "INV-DB-1"
        archiviata = await db.prima_nota_banca.find_one({"id": "PN-RAW"})
        assert archiviata["status"] == "archived"
        assert archiviata["deleted_reason"] == "duplicato_proiezione_paypal_documentata"

    _run(scenario())


def test_riprocessa_backfill_movimento_storico_collegato_solo_dal_lato_banca():
    async def scenario():
        db = AsyncMongoMockClient().db
        await _seed_identity(db)
        await db.invoices.insert_one(_invoice())
        await db.paypal_transactions.insert_one({
            **_transaction(),
            "fattura_associata": {
                "fattura_id": "INV-DB-1", "match": "fornitore_numero_importo_esatti",
                "evidenze": ["denominazione_fornitore", "numero_fattura", "importo"],
            },
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-STORICO", "data": "2026-07-14", "tipo": "uscita",
            "importo": -100.0, "riconciliato": True,
            "paypal_transaction_id": "PAY-TX-1",
        })

        result = await riprocessa_collegamenti_paypal(db)

        invoice = await db.invoices.find_one({"id": "INV-DB-1"})
        transaction = await db.paypal_transactions.find_one({"transaction_id": "PAY-TX-1"})
        assert result["finalizzate"] == 1
        assert transaction["movimento_banca_id"] == "EC-STORICO"
        assert invoice["riconciliato"] is True
        assert invoice["pagato"] is True

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


def test_riconciliazione_banca_unifica_due_importazioni_della_stessa_riga():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.paypal_transactions.insert_one({
            **_transaction(), "importo": -42.62, "data": "2026-07-15",
            "invoice_id_fornitore": "FT-NON-PRESENTE",
        })
        await db.estratto_conto_movimenti.insert_many([
            {
                "id": "EC-PAYPAL-SHORT", "data": "2026-07-17",
                "tipo": "uscita", "importo": 42.62,
                "descrizione": "SDD CORE: 49RJ2252ASLM4 PAYPAL EUROPE S.A.R.L.",
                "created_at": "2026-08-03T10:00:00+00:00",
            },
            {
                "id": "EC-PAYPAL-FULL", "data": "2026-07-17",
                "tipo": "uscita", "importo": 42.62, "rapporto": "conto-bancario",
                "descrizione": (
                    "ADDEBITO DIRETTO SDD - SDD CORE: 49RJ2252ASLM4 "
                    "PayPal Europe S.a.r.l."
                ),
                "created_at": "2026-08-04T10:00:00+00:00",
            },
        ])

        result = await _auto_riconcilia(db, anno=2026, applica=True)

        assert result["totale_banca_raw"] == 2
        assert result["duplicati_banca_unificati"] == 1
        assert result["totale_banca"] == 1
        assert result["riconciliati"] == 1
        transaction = await db.paypal_transactions.find_one({"transaction_id": "PAY-TX-1"})
        assert transaction["movimento_banca_id"] == "EC-PAYPAL-FULL"

    _run(scenario())
