import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import bank_supplier_rules as rules


def run(value):
    return asyncio.run(value)


def test_regola_sdd_collega_solo_fornitore_importo_e_data_compatibili(monkeypatch):
    db = AsyncMongoMockClient()["bank_supplier_rules_match"]
    run(rules.save_rule(db, {
        "reference_text": "SDD CORE: M-100286973-3908993102489156 WORLDPAY",
        "supplier_name": "HP Italy",
    }))
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "bank-1", "data": "2026-07-29", "importo": -1.79,
        "descrizione_originale": "ADDEBITO DIRETTO SDD - SDD CORE: M-100286973-3908993102489156 WORLDPAY",
        "riconciliato": False,
    }))
    run(db["invoices"].insert_many([
        {"id": "hp", "invoice_date": "2026-07-05", "supplier_name": "HP Italy S.r.l", "total_amount": 1.79, "pagato": False},
        {"id": "other", "invoice_date": "2026-07-06", "supplier_name": "Altro", "total_amount": 1.79, "pagato": False},
    ]))
    calls = []
    async def fake_reconcile(_db, request):
        calls.append(request)
        return {"success": True}
    monkeypatch.setattr(rules, "reconcile_invoice_bank_movement", fake_reconcile)

    result = run(rules.reprocess_rules(db, 2026))

    assert result["linked_count"] == 1
    assert calls[0].fattura_id == "hp"
    assert calls[0].movimento_id == "bank-1"
    assert "Regola Admin SDD" in calls[0].override_reason


def test_regola_non_indovina_due_fatture_stessa_data(monkeypatch):
    db = AsyncMongoMockClient()["bank_supplier_rules_ambiguous"]
    run(rules.save_rule(db, {"reference_text": "SDD CORE: FASTWEB-REF FASTWEB", "supplier_name": "FASTWEB"}))
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "bank-2", "data": "2026-07-27", "importo": -43.86,
        "descrizione": "ADDEBITO DIRETTO SDD - SDD CORE: FASTWEB-REF FASTWEB", "riconciliato": False,
    }))
    run(db["invoices"].insert_many([
        {"id": "f1", "invoice_date": "2026-07-10", "supplier_name": "FASTWEB SpA", "total_amount": 43.86},
        {"id": "f2", "invoice_date": "2026-07-10", "supplier_name": "FASTWEB SpA", "total_amount": 43.86},
    ]))
    async def should_not_run(*_args):
        raise AssertionError("match ambiguo")
    monkeypatch.setattr(rules, "reconcile_invoice_bank_movement", should_not_run)

    result = run(rules.reprocess_rules(db, 2026))

    assert result["linked_count"] == 0
    assert result["ambiguous_count"] == 1
