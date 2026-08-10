import asyncio
from copy import deepcopy

from mongomock_motor import AsyncMongoMockClient

from app.services.entity_relations import upsert_entity_relation
from app.services.entity_relations_audit import audit_legacy_entity_relations


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_audit_storico_e_solo_lettura_e_non_promuove_documenti_a_pagamenti():
    async def scenario():
        db = AsyncMongoMockClient()["relations_audit"]
        await db.assegni.insert_one({
            "id": "CHK-1", "movimento_estratto_conto_id": "EC-CHK-1",
            "incassato_confermato_banca": True,
            "fatture_collegate": [{
                "fattura_id": "INV-1", "banca_confermata": True,
            }],
        })
        await db.f24_unificato.insert_many([
            {"id": "F24-DOC", "quietanza_id": "QUIET-1", "pagato": False},
            {
                "id": "F24-PAID", "pagato": True,
                "movimento_bancario_id": "EC-F24-1",
                "data_pagamento_effettivo": "2026-08-07",
            },
            {
                "id": "F24-LEGACY-NO-PROOF", "pagato": True,
                "movimento_bancario_id": "EC-F24-UNVERIFIED",
            },
        ])
        await db.paypal_transactions.insert_one({
            "transaction_id": "PAY-1",
            "fattura_associata": {"fattura_id": "INV-PAY-1"},
            "movimento_banca_id": "EC-PAY-1",
            "fattura_pagamento_finalizzato": False,
        })
        await upsert_entity_relation(
            db,
            source_type="f24_receipt", source_id="QUIET-1",
            relation_type="documents_f24_model", target_type="f24_model",
            target_id="F24-DOC", status="confirmed", rule="test",
        )
        source_before = {
            "assegni": deepcopy(await db.assegni.find_one({}, {"_id": 0})),
            "f24": deepcopy(await db.f24_unificato.find({}, {"_id": 0}).to_list(10)),
            "paypal": deepcopy(await db.paypal_transactions.find_one({}, {"_id": 0})),
        }
        relation_count_before = await db.entity_relations.count_documents({})
        first = await audit_legacy_entity_relations(db)
        second = await audit_legacy_entity_relations(db)
        relation_count_after = await db.entity_relations.count_documents({})
        source_after = {
            "assegni": await db.assegni.find_one({}, {"_id": 0}),
            "f24": await db.f24_unificato.find({}, {"_id": 0}).to_list(10),
            "paypal": await db.paypal_transactions.find_one({}, {"_id": 0}),
        }
        return (
            first, second, relation_count_before, relation_count_after,
            source_before, source_after,
        )

    first, second, count_before, count_after, source_before, source_after = _run(
        scenario()
    )
    assert first == second
    assert first["read_only"] is True
    assert first["writes_performed"] == 0
    assert count_before == count_after == 1
    assert source_before == source_after
    assert first["by_domain"]["f24"] == {
        "expected": 2, "present": 1, "missing": 1,
    }
    paypal_types = {
        row["relation_type"] for row in first["sample_missing"]
        if row["domain"] == "paypal"
    }
    assert paypal_types == {"allocates_paypal_payment"}
    assert "settles_paypal_transaction" not in paypal_types
    assert "proves_invoice_payment" not in paypal_types
