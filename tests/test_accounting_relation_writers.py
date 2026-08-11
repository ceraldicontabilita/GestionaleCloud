import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.accounting_relation_writers import (
    record_check_reconciliation,
    record_f24_bank_allocations,
    record_f24_receipt_link,
    record_paypal_bank_chain,
    record_paypal_invoice_link,
    record_salary_reconciliation,
)
from app.services.entity_relations import find_entity_relations
from app.services.tax_payment_query import TaxPaymentQueryService


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_assegno_registra_catena_bidirezionale_senza_mutare_le_entita():
    async def scenario():
        db = AsyncMongoMockClient()["relations_check"]
        cheque = {"id": "CHK-1", "numero": "0208769328", "importo": 1861.71}
        movement = {"id": "EC-1", "importo": 1861.71}
        invoice_links = [{
            "fattura_id": "INV-1", "numero_fattura": "1/10663",
            "quota": 1861.71, "match_livello": "numero+fornitore+centesimi",
        }]
        before = (dict(cheque), dict(movement), [dict(invoice_links[0])])
        first = await record_check_reconciliation(
            db, cheque=cheque, movement=movement, invoice_links=invoice_links
        )
        second = await record_check_reconciliation(
            db, cheque=cheque, movement=movement, invoice_links=invoice_links
        )
        from_invoice = await find_entity_relations(
            db, entity_type="invoice", entity_id="INV-1"
        )
        return db, before, cheque, movement, invoice_links, first, second, from_invoice

    db, before, cheque, movement, links, first, second, from_invoice = _run(scenario())
    assert first == second
    assert len(first) == 3
    assert _run(db.entity_relations.count_documents({})) == 3
    assert {row["relation_type"] for row in from_invoice} == {
        "allocated_to_invoice", "proves_invoice_payment"
    }
    assert (cheque, movement, links) == before


def test_salario_parziale_conserva_centesimi_e_collega_il_cedolino():
    async def scenario():
        db = AsyncMongoMockClient()["relations_salary"]
        keys = await record_salary_reconciliation(
            db,
            salary_entry={
                "id": "SAL-1", "cedolino_id": "CED-1", "mese": 7,
                "anno": 2026, "netto": 1400.00,
            },
            movement={"id": "EC-SAL-1"},
            amount=1000.35,
            employee_name="CERALDI VALERIO",
        )
        rows = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        return keys, rows

    keys, rows = _run(scenario())
    assert len(keys) == 3
    bank_salary = next(
        row for row in rows if row["relation_type"] == "allocates_salary_payment"
    )
    assert bank_salary["amount_cents"] == 100035
    assert any(row["target"]["id"] == "CED-1" for row in rows)


def test_quietanza_f24_non_diventa_prova_bancaria():
    async def scenario():
        db = AsyncMongoMockClient()["relations_f24"]
        f24 = {"id": "F24-1", "sezione_erario": [{
            "id": "TRIB-2001", "codice_tributo": "2001",
            "periodo_riferimento": "06", "anno_riferimento": "2026",
            "importo_debito_cents": 461350,
        }]}
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-F24-1", "prima_nota_banca_id": "PN-F24-1",
            "data_contabile": "2026-07-21",
        })
        await record_f24_receipt_link(
            db, f24=f24, receipt_id="QUIET-1", protocol="P-1",
            amount=5362.52, matched_tributes=6, total_tributes=6,
        )
        before_bank = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        await record_f24_bank_allocations(
            db,
            f24=f24,
            allocations=[{
                "movimento_id": "EC-F24-1", "importo": 4613.50,
                "codici_tributo": ["2001"], "tributo_ids": ["TRIB-2001"],
            }],
        )
        after_bank = await db.entity_relations.find({}, {"_id": 0}).to_list(length=20)
        return before_bank, after_bank

    before_bank, after_bank = _run(scenario())
    assert {row["relation_type"] for row in before_bank} == {
        "documents_f24_model", "contains_tax_row", "proves_tax_row_payment"
    }
    assert {row["relation_type"] for row in after_bank} == {
        "documents_f24_model", "contains_tax_row", "proves_tax_row_payment",
        "settles_f24_model", "settles_tax_row", "represented_by_prima_nota",
        "posted_in_prima_nota",
    }


def test_vista_fiscale_ricostruisce_catena_completa_dalle_relazioni():
    async def scenario():
        db = AsyncMongoMockClient()["tax_payment_chain"]
        f24 = {"id": "F24-CATENA", "sezione_erario": [{
            "codice_tributo": "1040", "periodo_riferimento": "06",
            "anno_riferimento": "2026", "importo_debito_cents": 28400,
        }]}
        await db.f24_unificato.insert_one(f24)
        await db.quietanze_f24.insert_one({
            "id": "QUIET-CATENA", "protocollo_telematico": "PROTO-1040",
            "data_pagamento": "2026-07-21", "filename": "quietanza.pdf",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-CATENA", "prima_nota_banca_id": "PN-CATENA",
            "data_contabile": "2026-07-21",
        })
        await record_f24_receipt_link(
            db, f24=f24, receipt_id="QUIET-CATENA", protocol="PROTO-1040",
            amount="284.00", matched_tributes=1, total_tributes=1,
        )
        await record_f24_bank_allocations(
            db, f24=f24, allocations=[{
                "movimento_id": "EC-CATENA", "importo_cents": 28400,
                "codici_tributo": ["1040"],
            }],
        )
        return (await TaxPaymentQueryService(db).list_documents())[0]

    document = _run(scenario())
    chain = document["payment_chain"]
    assert document["versato_documentalmente"] is True
    assert document["banca_verificata"] is True
    assert chain["receipt"]["id"] == "QUIET-CATENA"
    assert chain["bank_movement"]["id"] == "EC-CATENA"
    assert chain["prima_nota"]["id"] == "PN-CATENA"
    assert chain["axes"] == {
        "obligation": "F24_MODELLO_PRESENTE",
        "document_evidence": "VERSATO_DOCUMENTALMENTE",
        "bank": "VERIFICATA",
    }
    assert {relation["relation_type"] for relation in chain["relations"]} >= {
        "documents_f24_model", "proves_tax_row_payment", "settles_tax_row",
        "settles_f24_model", "posted_in_prima_nota",
    }


def test_paypal_richiede_movimento_bancario_per_provare_il_pagamento():
    async def scenario():
        db = AsyncMongoMockClient()["relations_paypal"]
        transaction = {"transaction_id": "PAY-1"}
        invoice = {"id": "INV-PAY-1"}
        await record_paypal_invoice_link(
            db, transaction=transaction, invoice=invoice, amount=42.62,
            evidence=[{"type": "invoice_number", "value": "FT-42"}],
        )
        before_bank = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        await record_paypal_bank_chain(
            db, transaction=transaction, invoice=invoice,
            movement={"id": "EC-PAY-1"}, amount=42.62,
        )
        after_bank = await db.entity_relations.find({}, {"_id": 0}).to_list(length=10)
        return before_bank, after_bank

    before_bank, after_bank = _run(scenario())
    assert [row["relation_type"] for row in before_bank] == [
        "allocates_paypal_payment"
    ]
    assert {row["relation_type"] for row in after_bank} == {
        "allocates_paypal_payment", "settles_paypal_transaction",
        "proves_invoice_payment",
    }
