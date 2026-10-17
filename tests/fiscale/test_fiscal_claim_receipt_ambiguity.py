import asyncio
from copy import deepcopy

import pytest

from app.db_collections import (
    COLL_DOCUMENTS_INBOX, COLL_F24, COLL_QUIETANZE_F24, COLL_TAX_COLLECTION_CLAIMS,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_claim_source_reconciliation import (
    ALERT_REFUND, ALERT_RELIEF, apply_claim_source_plan, build_claim_source_plan,
    match_f24_models_for_obligation, match_quietanza_for_obligation,
)


COMPANY = "04523831214"
IDENTITY = "5124776507"


def _obligation(**overrides):
    return {"codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "06/2024",
            "matricola_inps": IDENTITY, "importo_richiesto_cents": 10000, **overrides}


def _receipt(*, amount=15000, code="RC01", period="06/2024", identity=IDENTITY, **overrides):
    return {"id": "receipt", "protocollo_telematico": "PROTOCOL-1", "codice_fiscale": COMPANY,
            "sezione_inps": [{"causale": code, "matricola": identity,
                              "periodo_riferimento": period, "importo_debito_cents": amount}],
            **overrides}


def _notice_text(amounts, periods=None):
    periods = periods or ["06/2024"] * len(amounts)
    return "\n".join(
        f"{index:03d}       8050-Modello DM 10\n"
        f"CONTRIBUTI DA {period} A {period} {amount},00 0,00 {amount},00"
        for index, (amount, period) in enumerate(zip(amounts, periods), 1)
    )


async def _seed_notice(db, amounts, *, claim_id="claim", number="37120240000000001000",
                       identity=IDENTITY, periods=None, original_id=None):
    await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": claim_id, "company_id": COMPANY, "collection_number": number, "business_status": "PAYABLE",
    })
    await db[COLL_DOCUMENTS_INBOX].insert_one({
        "id": original_id or f"notice-{claim_id}", "tax_collection_claim_id": claim_id,
        "parsed_metadata": {"numero_atto": number, "matricola_inps": identity,
                            "testo_estratto": _notice_text(amounts, periods)},
    })


def _rows(plan):
    return [row for item in plan for link in item["source_obligation_links"] for row in link["tax_lines"]]


@pytest.mark.parametrize("amount,code", [(10000, "DM10"), (10000, "RC01"), (15000, "RC01")])
@pytest.mark.parametrize("identity", [None, "", "  "])
def test_missing_notice_identity_never_certifies_receipt_or_model(amount, code, identity):
    obligation = _obligation(matricola_inps=identity)
    receipt = _receipt(amount=amount, code=code)
    assert match_quietanza_for_obligation(obligation, [receipt]) == []
    assert match_f24_models_for_obligation(obligation, [receipt]) == []


@pytest.mark.parametrize("identity", [None, "", "9999999999"])
def test_missing_or_different_receipt_identity_is_not_a_match(identity):
    assert match_quietanza_for_obligation(_obligation(), [_receipt(identity=identity)]) == []


@pytest.mark.parametrize("obligation,receipt", [
    (_obligation(periodo_da="2024", periodo_a="2024"), _receipt(period="2024")),
    (_obligation(periodo_a="07/2024"), _receipt()),
    (_obligation(), _receipt(sezione_inps=[{
        "causale": "RC01", "matricola": IDENTITY, "periodo_da": "06/2024",
        "periodo_a": "07/2024", "importo_debito_cents": 15000,
    }])),
])
def test_inps_period_must_identify_the_complete_same_month_range(obligation, receipt):
    assert match_quietanza_for_obligation(obligation, [receipt]) == []


def test_missing_identity_is_visible_for_review_without_relief_or_refund():
    async def scenario():
        db = ClientArchivioMemoria()["missing-matricola"]
        await _seed_notice(db, [100], identity=None)
        await db[COLL_QUIETANZE_F24].insert_one(_receipt())
        result = await apply_claim_source_plan(db, company_id=COMPANY, actor="test")
        row = _rows(result["items"])[0]
        assert row["payment_evidence_status"] == "REVIEW_REQUIRED"
        assert row["payment_matches"] == []
        assert result["items"][0]["remediation_alert"] is None
        assert result["alerts_created"] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("paid_amount", [20000, 25000, 40000])
def test_one_rc01_cannot_pay_two_same_period_obligations_even_if_large_enough(paid_amount):
    async def scenario():
        db = ClientArchivioMemoria()["one-receipt-two-obligations"]
        await _seed_notice(db, [100, 200])
        await db[COLL_QUIETANZE_F24].insert_one(_receipt(amount=paid_amount))
        result = await apply_claim_source_plan(db, company_id=COMPANY, actor="test")
        rows = _rows(result["items"])
        assert len(rows) == 2
        assert {row["payment_evidence_status"] for row in rows} == {"REVIEW_REQUIRED"}
        assert all(row["payment_evidence_review_reason"] == "RECEIPT_ROW_MATCHES_MULTIPLE_OBLIGATIONS"
                   for row in rows)
        assert result["items"][0]["remediation_alert"] is None
        assert result["alerts_created"] == 0
    asyncio.run(scenario())


def test_receipt_reuse_is_checked_across_notices_and_claims_before_generating_alerts():
    async def scenario():
        db = ClientArchivioMemoria()["receipt-cross-notice"]
        await _seed_notice(db, [100])
        await _seed_notice(db, [200], claim_id="claim-2", number="37120240000000002000")
        await db[COLL_QUIETANZE_F24].insert_one(_receipt(amount=25000))
        plan = await build_claim_source_plan(db, company_id=COMPANY)
        assert len(plan) == 2
        assert {row["payment_evidence_status"] for row in _rows(plan)} == {"REVIEW_REQUIRED"}
        assert all(item["remediation_alert"] is None for item in plan)
    asyncio.run(scenario())


def test_two_compatible_rows_in_one_receipt_are_not_collapsed_to_one_candidate():
    async def scenario():
        db = ClientArchivioMemoria()["receipt-two-rows"]
        await _seed_notice(db, [100])
        receipt = _receipt()
        receipt["sezione_inps"].append({**receipt["sezione_inps"][0], "importo_debito_cents": 16000})
        await db[COLL_QUIETANZE_F24].insert_one(receipt)
        plan = await build_claim_source_plan(db, company_id=COMPANY)
        assert len(_rows(plan)[0]["payment_matches"]) == 2
        assert _rows(plan)[0]["payment_evidence_status"] == "REVIEW_REQUIRED"
        assert plan[0]["remediation_alert"] is None
    asyncio.run(scenario())


def test_distinct_period_rows_in_same_receipt_can_each_pay_their_own_obligation_without_bank():
    async def scenario():
        db = ClientArchivioMemoria()["receipt-distinct-periods"]
        await _seed_notice(db, [100, 200], periods=["06/2024", "07/2024"])
        receipt = _receipt(amount=10000)
        receipt["sezione_inps"].append({**receipt["sezione_inps"][0], "periodo_riferimento": "07/2024",
                                        "importo_debito_cents": 20000})
        await db[COLL_QUIETANZE_F24].insert_one(receipt)
        plan = await build_claim_source_plan(db, company_id=COMPANY)
        assert {row["payment_evidence_status"] for row in _rows(plan)} == {"PAID_DOCUMENTED"}
        assert all(not row["payment_matches"][0]["bank_verified"] for row in _rows(plan))
        assert plan[0]["remediation_alert"]["action"] == "VERIFY_RELIEF_REQUEST"
    asyncio.run(scenario())


def test_repeated_copy_of_same_protocol_does_not_create_another_payment():
    receipt = _receipt()
    duplicate = {**deepcopy(receipt), "id": "duplicate"}
    assert len(match_quietanza_for_obligation(_obligation(), [receipt, duplicate])) == 1


def test_reconciliation_resolves_stale_relief_and_refund_alerts_when_receipt_becomes_ambiguous():
    async def scenario():
        db = ClientArchivioMemoria()["receipt-stale-alert"]
        await _seed_notice(db, [100])
        await db[COLL_QUIETANZE_F24].insert_one(_receipt(amount=25000))
        first = await apply_claim_source_plan(db, company_id=COMPANY, actor="test")
        assert first["alerts_created"] == 1
        await db["alerts"].insert_one({"id": "stale-refund", "entita_id": "claim",
                                       "codice": ALERT_REFUND, "stato": "aperto"})
        await db[COLL_DOCUMENTS_INBOX].update_one({"id": "notice-claim"}, {"$set": {
            "parsed_metadata.testo_estratto": _notice_text([100, 200]),
        }})
        result = await apply_claim_source_plan(db, company_id=COMPANY, actor="test")
        assert result["alerts_created"] == 0
        assert result["items"][0]["remediation_alert"] is None
        alerts = await db["alerts"].find({"entita_id": "claim"}).to_list(None)
        assert {alert["codice"] for alert in alerts} == {ALERT_RELIEF, ALERT_REFUND}
        assert all(alert["stato"] == "risolto" for alert in alerts)
    asyncio.run(scenario())


def test_f24_and_bank_metadata_without_receipt_never_generate_documented_payment():
    async def scenario():
        db = ClientArchivioMemoria()["model-bank-no-receipt"]
        await _seed_notice(db, [100])
        model = _receipt(amount=10000, code="DM10", riscontro_banca={
            "stato": "RISCONTRATO_BANCA", "movimento_id": "bank-1",
        })
        await db[COLL_F24].insert_one(model)
        plan = await build_claim_source_plan(db, company_id=COMPANY)
        assert len(_rows(plan)[0]["f24_model_matches"]) == 1
        assert _rows(plan)[0]["f24_model_matches"][0]["payment_evidence"] is False
        assert _rows(plan)[0]["payment_evidence_status"] == "NO_PAYMENT_EVIDENCE"
        assert plan[0]["remediation_alert"] is None
    asyncio.run(scenario())


@pytest.mark.parametrize("status", [{"entity_status": "deleted"}, {"status": "eliminato"}])
def test_deleted_receipt_cannot_document_payment(status):
    assert match_quietanza_for_obligation(_obligation(), [_receipt(**status)]) == []


@pytest.mark.parametrize("status", [
    {"entity_status": "deleted"}, {"status": "eliminato"},
    {"superato_da": "model-current"}, {"motivo_quarantena": "versione superata"},
])
def test_inactive_model_neither_matches_nor_supports_wrong_dm10_payment(status):
    model = _receipt(amount=10000, code="DM10", **status)
    assert match_f24_models_for_obligation(_obligation(), [model]) == []
    assert match_quietanza_for_obligation(_obligation(), [_receipt(code="DM10")], [model]) == []


@pytest.mark.parametrize("section,entity_field,tax_code,entity,wrong_field", [
    ("sezione_regioni", "codice_regione", "3802", "15", "codice_sede"),
    ("sezione_regioni", "codice_regione", "3802", "15", "codice_comune"),
    ("sezione_tributi_locali", "codice_comune", "3848", "F839", "codice_ufficio"),
    ("sezione_tributi_locali", "codice_comune", "3848", "F839", "codice_regione"),
])
def test_other_code_namespaces_never_replace_missing_jurisdiction(section, entity_field, tax_code, entity, wrong_field):
    original_row = {"codice_tributo": tax_code, entity_field: entity,
                    "periodo_riferimento": "2024", "importo_debito_cents": 10000}
    wrong_row = {key: value for key, value in original_row.items() if key != entity_field}
    wrong_row[wrong_field] = entity
    receipt = _receipt(code="DM10", **{section: [wrong_row]})
    model = _receipt(amount=10000, code="DM10", **{section: [original_row]})
    assert match_quietanza_for_obligation(_obligation(), [receipt], [model]) == []
    tax_obligation = {"codice_tributo": tax_code, "periodo": "2024",
                      "importo_cents": 10000, entity_field: entity}
    assert match_quietanza_for_obligation(tax_obligation, [receipt]) == []
