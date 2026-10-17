"""Regressions for the read-only evidence chronology, including imported dates."""
import asyncio
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db_collections import (
    COLL_ADER_POSITION_SNAPSHOTS, COLL_DOCUMENTS_INBOX, COLL_ESTRATTO_CONTO,
    COLL_F24, COLL_FISCAL_DOCUMENTS, COLL_FISCAL_EVIDENCE, COLL_FISCAL_LINKS,
    COLL_QUIETANZE_F24, COLL_TAX_ALLOCATIONS, COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS, COLL_TAX_PAYMENTS, COLL_TAX_RATE_PLANS,
    COLL_TAX_COLLECTION_DOCUMENTS, COLL_TAX_LEGAL_EVENTS, COLL_TAX_NOTIFICATION_EVENTS,
    COLL_TAX_RATE_INSTALLMENTS, COLL_TAX_RATE_PLAN_CLAIM_ALLOCATIONS,
    COLL_TAX_SETTLEMENT_APPLICATIONS, COLL_TAX_SETTLEMENT_CLAIMS,
    COLL_TAX_SETTLEMENT_INSTALLMENTS,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_collection_dossier import build_collection_dossier


COMPANY = "04523831214"
NUMBER = "07120260000000000001"


def run(coro):
    return asyncio.run(coro)


async def seed(*, kind="CARTELLA_ESATTORIALE", **extra):
    db = ClientArchivioMemoria()["collection-dossier-test"]
    await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": "claim-1", "company_id": COMPANY, "collection_number": NUMBER,
        "document_type": kind, **extra,
    })
    return db


def dossier(db):
    return run(build_collection_dossier(db, company_id=COMPANY, claim_id="claim-1"))


def all_entries(result):
    return result["timeline"] + result["undated"]


def codes(result):
    return {item["code"] for item in result["findings"]}


def row(**extra):
    return {
        "codice_tributo": "8050", "periodo_da": "06/2003", "periodo_a": "07/2003",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 10000,
        "f24_model_matches": [{"f24_id": "model-1"}],
        "payment_matches": [{"quietanza_id": "receipt-1"}], **extra,
    }


async def with_source(*, receipt=True, partial=False, **claim_fields):
    source_row = row()
    if partial:
        source_row["payment_matches"] = []
        source_row["partial_payment_candidates"] = [{"quietanza_id": "receipt-1"}]
    if not receipt:
        source_row["payment_matches"] = []
    db = await seed(source_obligation_links=[{
        "source_type": "AVVISO_ADDEBITO_INPS", "relation_status": "CONFIRMED",
        "inbox_document_id": "notice-1", "tax_lines": [source_row],
    }], **claim_fields)
    await db[COLL_DOCUMENTS_INBOX].insert_one({
        "id": "notice-1", "company_id": COMPANY, "filename": "avviso.pdf",
        "document_type": "AVVISO_BONARIO", "parsed_metadata": {
            "data_atto": "20/11/2003", "matricola_inps": "5124776507",
            "numero_atto": NUMBER,
            "testo_estratto": "001 8050-Modello DM 10\nCONTRIBUTI DA 06/2003 A 07/2003 100,00 0,00 100,00\n",
        },
        "created_at": "2026-10-17",
    })
    await db[COLL_F24].insert_one({
        "id": "model-1", "codice_fiscale": COMPANY, "data_compilazione": "10/08/2003",
        "data_scadenza": "2003-08-16", "created_at": "2026-10-17",
    })
    if receipt:
        await db[COLL_QUIETANZE_F24].insert_one({
            "id": "receipt-1", "codice_fiscale": COMPANY, "data_pagamento": "2003-08-18",
            "protocollo_telematico": "P-1",
            "sezione_erario": [{"importo_debito": "50,00" if partial else "100,00",
                                 "raw_text": "5100 DM10 5124776507 06 2003 07 2003 "
                                             + ("50,00" if partial else "100,00") + " , 0,00 ,"}],
        })
    return db


def test_chronology_keeps_all_missing_stages_unknown_and_does_not_write():
    db = run(with_source(receipt=False, notification_date="15/01/2004"))
    before = run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    first, second = dossier(db), dossier(db)
    assert first == second
    assert first["safety"] == {"payment_inferred": False, "requests_submitted": False}
    assert first["timeline"][0]["date"] == "2003-08-10"
    assert [entry["event_type"] for entry in first["timeline"]] == [
        "F24_MODEL", "F24_DUE_DATE", "ORIGINAL_NOTICE", "COLLECTION_NOTIFICATION",
    ]
    assert "F24_MODEL_WITHOUT_RECEIPT" in codes(first)
    role = next(step for step in first["path"]["steps"] if step["code"] == "ROLE_FORMATION")
    assert role["status"] == "NOT_DOCUMENTED"
    assert not any("REQUEST" in item["event_type"] for item in all_entries(first))
    assert run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"})) == before
    assert run(db[COLL_TAX_COLLECTION_EVENTS].count_documents({})) == 0


@pytest.mark.parametrize("status,fields", [
    ("eliminato", {}), (None, {"entity_status": "deleted"}),
    (None, {"superato_da": "other"}), (None, {"motivo_quarantena": "duplicate"}),
])
def test_cached_model_reference_does_not_revive_an_inactive_document(status, fields):
    db = run(with_source(receipt=False))
    run(db[COLL_F24].update_one({"id": "model-1"}, {"$set": {"status": status, **fields}}))
    result = dossier(db)
    assert result["evidence_summary"]["f24_models"] == 0
    assert not any(item["event_type"] == "F24_MODEL" for item in all_entries(result))


def test_upload_and_generic_model_payment_date_do_not_become_legal_dates():
    db = run(with_source(receipt=False))
    run(db[COLL_F24].update_one({"id": "model-1"}, {
        "$unset": {"data_compilazione": "", "data_scadenza": ""},
        "$set": {"data_pagamento": "2003-08-16", "data_stampa": "2026-10-17"},
    }))
    result = dossier(db)
    model = next(item for item in result["undated"] if item["event_type"] == "F24_MODEL")
    assert model["date"] is None
    assert model["evidence_level"] == "MODEL_ONLY"
    assert model["url"].startswith("/api/originale/f24/")
    assert not any(item["date"] == "2026-10-17" for item in result["timeline"])


@pytest.mark.parametrize("role_fields,expected", [
    ({"data_formazione_ruolo": "2003-09-01"}, "SOURCE_PAID_BEFORE_ROLE"),
    ({"data_formazione_ruolo": "2003-08-01"}, "SOURCE_PAID_ON_OR_AFTER_ROLE"),
    ({"data_formazione_ruolo": "2003-08-18"}, "SOURCE_PAID_ON_OR_AFTER_ROLE"),
    ({"data_esecutivita_ruolo": "2003-09-01", "data_consegna_ruolo": "2003-09-20"}, "ROLE_DATE_REQUIRED"),
])
def test_exact_historical_receipt_uses_actual_formation_date_not_execution_or_delivery(role_fields, expected):
    result = dossier(run(with_source(**role_fields)))
    assert expected in codes(result)
    assert result["evidence_summary"]["documentary_receipts"] == 1
    assert result["evidence_summary"]["claim_allocated_cents"] == 0
    assert not any("REQUEST" in item["event_type"] for item in all_entries(result))


@pytest.mark.parametrize("change", [
    {"matricola_inps": None}, {"periodo_a": "08/2003"},
])
def test_cached_exact_match_does_not_certify_missing_identity_or_incomplete_period(change):
    db = run(with_source(data_formazione_ruolo="2003-09-01"))
    notice = run(db[COLL_DOCUMENTS_INBOX].find_one({"id": "notice-1"}))
    metadata = notice["parsed_metadata"]
    if "matricola_inps" in change:
        metadata["matricola_inps"] = change["matricola_inps"]
    else:
        metadata["testo_estratto"] = metadata["testo_estratto"].replace("A 07/2003", "A 08/2003")
    run(db[COLL_DOCUMENTS_INBOX].update_one({"id": "notice-1"}, {"$set": {"parsed_metadata": metadata}}))
    result = dossier(db)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert "SOURCE_PAID_ON_OR_AFTER_ROLE" not in codes(result)


def test_partial_source_receipt_is_provisional_and_does_not_certify_payment_before_role():
    result = dossier(run(with_source(partial=True, data_formazione_ruolo="2003-09-01")))
    entry = next(item for item in all_entries(result) if item["event_type"] == "PARTIAL_RECEIPT_CANDIDATE")
    assert entry["date"] == "2003-08-18"
    assert "amount_cents" not in entry
    assert "PARTIAL_SOURCE_RECEIPT_CANDIDATE" in codes(result)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert result["evidence_summary"]["claim_allocated_cents"] == 0


def test_cross_company_and_unowned_ids_do_not_disclose_cached_documents():
    db = run(with_source())
    run(db[COLL_DOCUMENTS_INBOX].update_one({"id": "notice-1"}, {"$set": {"company_id": "other"}}))
    run(db[COLL_F24].update_one({"id": "model-1"}, {"$set": {"company_id": "other"}}))
    run(db[COLL_QUIETANZE_F24].update_one({"id": "receipt-1"}, {"$unset": {"codice_fiscale": ""}}))
    result = dossier(db)
    assert result["timeline"] == [] and result["undated"] == []
    assert run(build_collection_dossier(db, company_id="other", claim_id="claim-1")) is None


def test_a_receipt_total_spanning_claims_is_never_the_single_claim_amount():
    db = run(seed(original_total_cents=10000, linked_payment_ids=["payment-1"]))
    run(db[COLL_TAX_PAYMENTS].insert_one({
        "id": "payment-1", "company_id": COMPANY, "operation_amount": "900.00",
        "payment_date": "2004-02-01", "documentary_evidence": True,
    }))
    run(db[COLL_TAX_ALLOCATIONS].insert_one({
        "id": "alloc-1", "company_id": COMPANY, "payment_id": "payment-1",
        "entity_type": "tax_collection_claim", "entity_id": "claim-1", "amount": "25.00",
        "evidence_types": ["RICEVUTA_PAGOPA"],
    }))
    run(db[COLL_TAX_ALLOCATIONS].insert_one({
        "id": "alloc-wrong-company", "company_id": "other", "payment_id": "payment-1",
        "entity_type": "tax_collection_claim", "entity_id": "claim-1", "amount": "875.00",
        "evidence_types": ["RICEVUTA_PAGOPA"],
    }))
    result = dossier(db)
    payment = next(item for item in result["timeline"] if item["event_type"] == "DIRECT_COLLECTION_PAYMENT")
    assert payment["amount_cents"] == 2500
    assert result["evidence_summary"]["claim_allocated_cents"] == 2500
    assert "PARTIAL_COLLECTION_PAYMENT" in codes(result)


def test_unallocated_shared_payment_and_import_timestamp_are_not_payment_date_or_amount():
    db = run(seed(linked_payment_ids=["payment-1"]))
    run(db[COLL_TAX_PAYMENTS].insert_one({
        "id": "payment-1", "company_id": COMPANY, "operation_amount": "900.00",
        "documentary_evidence": True, "created_at": "2026-10-17",
    }))
    run(db[COLL_TAX_COLLECTION_EVENTS].insert_one({
        "id": "event-1", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": "INSTALLMENT_PAYMENT", "payment_id": "payment-1",
        "effective_at": "2026-10-17T08:00:00Z", "amount": "0.00",
    }))
    result = dossier(db)
    assert result["timeline"] == []
    assert len(result["undated"]) == 1
    assert result["undated"][0]["event_type"] == "DIRECT_COLLECTION_PAYMENT"
    assert "amount_cents" not in result["undated"][0]
    assert "PAYMENT_ALLOCATION_MISSING" in codes(result)


def test_model_only_technical_payment_record_and_portal_closed_are_not_payment_receipts():
    db = run(seed(linked_payment_ids=["technical-1"]))
    run(db[COLL_TAX_PAYMENTS].insert_one({
        "id": "technical-1", "company_id": COMPANY, "source_kind": "F24_DOCUMENT_EVIDENCE",
        "documentary_evidence": True, "payment_date": "2026-10-17", "amount": 1000,
    }))
    run(db[COLL_ADER_POSITION_SNAPSHOTS].insert_one({
        "id": "snap-1", "company_id": COMPANY, "document_number": NUMBER,
        "snapshot_date": "2026-10-17", "net_payable_amount": 0, "portal_bucket": "SALDATI",
    }))
    result = dossier(db)
    assert {item["event_type"] for item in result["timeline"]} == {"PORTAL_SNAPSHOT"}
    assert result["evidence_summary"]["documentary_receipts"] == 0


@pytest.mark.parametrize("kind,path_code", [
    ("AVVISO_ADDEBITO_INPS", "INPS_EXECUTIVE_NOTICE"),
    ("AVVISO_ACCERTAMENTO_ESECUTIVO", "EXECUTIVE_ASSESSMENT"),
    ("CARTELLA_ESATTORIALE", "ADE_ROLE_CARTELLA"), ("", "UNKNOWN"),
])
def test_actual_collection_title_selects_route_and_never_assumes_preceding_bonario(kind, path_code):
    result = dossier(run(seed(kind=kind)))
    assert result["path"]["code"] == path_code
    original = next((step for step in result["path"]["steps"] if step["code"] == "ORIGINAL_NOTICE"), None)
    assert original is None or original["status"] == "NOT_DOCUMENTED"
    if kind in {"AVVISO_ADDEBITO_INPS", "AVVISO_ACCERTAMENTO_ESECUTIVO"}:
        assert next(step for step in result["path"]["steps"] if step["code"] == "ROLE_FORMATION")["status"] == "NOT_APPLICABLE"


def test_snapshot_explicit_type_and_notification_are_usable_without_inventing_original_act():
    db = run(seed(kind=""))
    run(db[COLL_ADER_POSITION_SNAPSHOTS].insert_one({
        "id": "snap-1", "company_id": COMPANY, "document_number": NUMBER,
        "document_type": "AVVISO_ADDEBITO", "snapshot_date": "2026-10-17",
        "notification_date": "2014-05-18", "net_payable_amount": 100,
    }))
    result = dossier(db)
    assert result["path"]["code"] == "INPS_EXECUTIVE_NOTICE"
    notification = next(item for item in result["timeline"] if item["event_type"] == "COLLECTION_NOTIFICATION")
    assert notification["date"] == "2014-05-18" and notification["evidence_level"] == "PORTAL"
    assert not any(item["event_type"] == "ROLE_FORMATION" for item in all_entries(result))


def test_confirmed_evidence_has_page_provenance_pending_evidence_not_loaded():
    db = run(seed())
    for status in ("confirmed", "pending", "revoked"):
        run(db[COLL_FISCAL_LINKS].insert_one({
            "id": "link-" + status, "company_id": COMPANY, "entity_type": "tax_collection_claim",
            "entity_id": "claim-1", "status": status, "evidence_ids": ["ev-" + status],
        }))
        run(db[COLL_FISCAL_EVIDENCE].insert_one({
            "id": "ev-" + status, "company_id": COMPANY, "document_id": "doc-" + status,
            "version_id": "v-" + status, "page_number": 2, "field": "notice_number",
        }))
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({
            "id": "doc-" + status, "company_id": COMPANY, "document_type": "CARTELLA_ADE_R",
            "filename": status + ".pdf",
        }))
    result = dossier(db)
    assert len(result["undated"]) == 1
    doc = result["undated"][0]
    assert doc["document_id"] == "doc-confirmed"
    assert doc["evidence"][0]["page_number"] == 2


def test_request_does_not_become_relief_and_legal_role_dates_are_not_conflated():
    db = run(seed(data_formazione_ruolo="2004-02-01", data_esecutivita_ruolo="2004-02-03",
                  data_consegna_ruolo="2004-02-05"))
    run(db[COLL_TAX_COLLECTION_EVENTS].insert_one({
        "id": "request-1", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": "RELIEF_REQUEST", "effective_at": "2026-10-16T22:30:00Z",
        "source_document_id": "request-doc",
    }))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": "request-doc", "company_id": COMPANY}))
    result = dossier(db)
    by_type = {item["event_type"]: item for item in result["timeline"]}
    assert by_type["ROLE_FORMATION"]["date"] == "2004-02-01"
    assert by_type["ROLE_EXECUTIVITY"]["date"] == "2004-02-03"
    assert by_type["ROLE_DELIVERY"]["date"] == "2004-02-05"
    assert by_type["RELIEF_REQUEST"]["date"] == "2026-10-17"
    assert "RELIEF" not in by_type and result["safety"]["requests_submitted"] is False


def test_bank_verified_flag_is_not_a_bank_movement_and_actual_bank_tenant_is_enforced():
    db = run(with_source())
    run(db[COLL_QUIETANZE_F24].update_one({"id": "receipt-1"}, {"$set": {
        "riscontro_banca": {"stato": "RISCONTRATO_BANCA", "movimento_id": "bank-1"},
    }}))
    run(db[COLL_ESTRATTO_CONTO].insert_one({"id": "bank-1", "company_id": "other", "data": "2003-08-19"}))
    result = dossier(db)
    assert result["evidence_summary"]["bank_movements"] == 0
    assert "BANK_ORIGINAL_UNAVAILABLE" in codes(result)
    run(db[COLL_ESTRATTO_CONTO].update_one({"id": "bank-1"}, {"$set": {"company_id": COMPANY}}))
    result = dossier(db)
    bank = next(item for item in result["timeline"] if item["event_type"] == "BANK_MOVEMENT")
    assert bank["date"] == "2003-08-19" and bank["evidence_level"] == "BANK"


def test_unlinked_same_period_document_and_wrong_company_plan_are_not_loaded():
    db = run(seed())
    run(db[COLL_DOCUMENTS_INBOX].insert_one({
        "id": "unrelated", "company_id": COMPANY, "document_type": "AVVISO_BONARIO",
        "periodo": "06/2003", "data_atto": "2003-09-01",
    }))
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "wrong-plan", "company_id": "other", "document_references": [{"document_number": NUMBER}],
        "application_date": "2004-03-01",
    }))
    assert all_entries(dossier(db)) == []


def test_dossier_route_requires_admin_and_returns_404_for_another_tenant(monkeypatch):
    from app.routers import fiscal_control
    from app.utils.dependencies import get_current_admin_user

    db = run(seed())
    monkeypatch.setattr(fiscal_control.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(fiscal_control, "_company", lambda: COMPANY)
    app = FastAPI()
    app.include_router(fiscal_control.router, prefix="/api/fiscal")
    with TestClient(app) as client:
        assert client.get("/api/fiscal/collections/claim-1/dossier").status_code in {401, 403}
        app.dependency_overrides[get_current_admin_user] = lambda: {"user_id": "admin"}
        assert client.get("/api/fiscal/collections/claim-1/dossier").status_code == 200
        monkeypatch.setattr(fiscal_control, "_company", lambda: "other")
        assert client.get("/api/fiscal/collections/claim-1/dossier").status_code == 404


@pytest.mark.parametrize("partial", [False, True])
def test_new_receipt_is_visible_without_mutating_or_reconciling_cached_source_links(partial):
    db = run(with_source(receipt=True, partial=partial, data_formazione_ruolo="2003-09-01"))
    claim = run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    claim["source_obligation_links"][0]["tax_lines"][0].update({
        "payment_matches": [], "partial_payment_candidates": [], "f24_model_matches": [],
    })
    run(db[COLL_TAX_COLLECTION_CLAIMS].update_one({"id": "claim-1"}, {
        "$set": {"source_obligation_links": claim["source_obligation_links"]},
    }))
    before = run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    result = dossier(db)
    expected = "PARTIAL_RECEIPT_CANDIDATE" if partial else "QUIETANZA_F24"
    assert any(item["event_type"] == expected for item in all_entries(result))
    assert "SOURCE_PAID_BEFORE_ROLE" in codes(result) if not partial else "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"})) == before
    assert run(db[COLL_TAX_COLLECTION_EVENTS].count_documents({})) == 0


def test_live_company_scan_does_not_include_unrelated_models_receipts_or_quietanza_ids():
    db = run(with_source())
    run(db[COLL_F24].insert_one({
        "id": "unrelated-model", "codice_fiscale": COMPANY, "quietanza_id": "unrelated-receipt",
        "data_compilazione": "2003-06-01",
    }))
    run(db[COLL_QUIETANZE_F24].insert_one({
        "id": "unrelated-receipt", "codice_fiscale": COMPANY, "data_pagamento": "2003-06-02",
    }))
    result = dossier(db)
    assert not any(item.get("document_id", "").startswith("unrelated") for item in all_entries(result))


@pytest.mark.parametrize("receipt_change", ["wrong_identity", "wrong_end", "greater_amount"])
def test_stale_partial_pointer_does_not_reassert_compatibility_of_changed_original(receipt_change):
    db = run(with_source(partial=True, data_formazione_ruolo="2003-09-01"))
    raw = "5100 DM10 5124776507 06 2003 07 2003 50,00 , 0,00 ,"
    amount = "50,00"
    if receipt_change == "wrong_identity":
        raw = raw.replace("5124776507", "9999999999")
    elif receipt_change == "wrong_end":
        raw = raw.replace("07 2003", "08 2003")
    else:
        raw, amount = raw.replace("50,00", "150,00"), "150,00"
    run(db[COLL_QUIETANZE_F24].update_one({"id": "receipt-1"}, {"$set": {
        "sezione_erario": [{"importo_debito": amount, "raw_text": raw}],
    }}))
    result = dossier(db)
    assert "PARTIAL_SOURCE_RECEIPT_CANDIDATE" not in codes(result)
    assert "RECEIPT_ATTRIBUTION_UNVERIFIED" in codes(result)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)


@pytest.mark.parametrize("evidence_case", ["nonexistent", "foreign_document", "foreign_evidence"])
def test_unverified_role_event_cannot_document_a_stage_or_date_a_relief_review(evidence_case):
    db = run(with_source())
    run(db[COLL_TAX_COLLECTION_EVENTS].insert_one({
        "id": "fake-role", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": "ROLE_FORMATION", "effective_at": "2003-09-01", "evidence_ids": ["ev-role"],
    }))
    if evidence_case != "nonexistent":
        run(db[COLL_FISCAL_EVIDENCE].insert_one({
            "id": "ev-role", "company_id": "other" if evidence_case == "foreign_evidence" else COMPANY,
            "document_id": "role-doc", "version_id": "role-version", "page_number": 1,
        }))
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({
            "id": "role-doc", "company_id": "other" if evidence_case == "foreign_document" else COMPANY,
        }))
    result = dossier(db)
    assert next(step for step in result["path"]["steps"] if step["code"] == "ROLE_FORMATION")["status"] == "NOT_DOCUMENTED"
    assert "ROLE_DATE_REQUIRED" in codes(result)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert any(item["event_type"] == "UNVERIFIED_RECORDED_EVENT" for item in result["undated"])


def test_claim_original_title_selects_path_without_snapshot_and_old_source_does_not_override_it():
    db = run(with_source(kind="", original_document_id="actual-cartella"))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "actual-cartella", "company_id": COMPANY, "document_type": "CARTELLA_ADE_R",
    }))
    assert dossier(db)["path"]["code"] == "ADE_ROLE_CARTELLA"


def test_canonical_multi_claim_receipt_integration_uses_real_allocated_share_and_original_date():
    from app.services.fiscal_payment_reconciliation import reconcile_direct_collection_receipt

    db = run(seed(original_total_cents=10000))
    other_number = "07120260000000000002"
    run(db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": "claim-2", "company_id": COMPANY, "collection_number": other_number,
        "original_total_cents": 90000,
    }))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "receipt-original", "company_id": COMPANY, "document_type": "RICEVUTA_PAGOPA",
    }))
    reconciled = run(reconcile_direct_collection_receipt(
        db, company_id=COMPANY, payment={
            "importo": 900, "data_pagamento": "2022-03-10",
            "documenti": [{"numero": NUMBER, "totale": 25, "quadra": True},
                          {"numero": other_number, "totale": 875, "quadra": True}],
        }, source_type="RICEVUTA_PAGOPA", source_id="receipt-actual",
        document_id="receipt-original", version_id="receipt-version",
    ))
    assert reconciled["matched"] is True
    before = run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    result = dossier(db)
    payment = next(item for item in result["timeline"] if item["event_type"] == "DIRECT_COLLECTION_PAYMENT")
    assert payment["date"] == "2022-03-10" and payment["amount_cents"] == 2500
    assert payment["url"] == "/api/originale/documento_fiscale/receipt-original"
    assert "PARTIAL_COLLECTION_PAYMENT" in codes(result)
    assert result["evidence_summary"]["claim_allocated_cents"] == 2500
    assert run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"})) == before


@pytest.mark.parametrize("status,amount", [("revoked", "25.00"), ("rejected", "25.00"), (None, "901.00")])
def test_invalid_or_revoked_allocation_does_not_reduce_claim_dossier_amount(status, amount):
    db = run(seed(linked_payment_ids=["payment-1"]))
    run(db[COLL_TAX_PAYMENTS].insert_one({
        "id": "payment-1", "company_id": COMPANY, "operation_amount": "900.00",
        "documentary_evidence": True,
    }))
    run(db[COLL_TAX_ALLOCATIONS].insert_one({
        "id": "alloc-1", "company_id": COMPANY, "payment_id": "payment-1",
        "entity_type": "tax_collection_claim", "entity_id": "claim-1", "amount": amount,
        "status": status, "evidence_types": ["RICEVUTA_PAGOPA"],
    }))
    assert dossier(db)["evidence_summary"]["claim_allocated_cents"] == 0


@pytest.mark.parametrize("label", ["Avviso", "Avviso di accertamento"])
def test_legacy_snapshot_generic_avviso_is_not_misrepresented_as_inps_executive_notice(label):
    db = run(seed(document_type=None))
    run(db[COLL_ADER_POSITION_SNAPSHOTS].insert_one({
        "id": "legacy-typed-snapshot", "company_id": COMPANY, "document_number": NUMBER,
        "snapshot_date": "2026-09-01", "document_type": "AVVISO_ADDEBITO",
        "document_label": label,
    }))
    result = dossier(db)
    assert result["path"]["code"] == "UNKNOWN"
    assert "INPS_DIRECT_EXECUTIVE_NOTICE" not in codes(result)


def test_changed_original_act_number_never_reuses_old_confirmed_source_attribution():
    db = run(with_source(data_formazione_ruolo="2003-09-01"))
    run(db[COLL_DOCUMENTS_INBOX].update_one({"id": "notice-1"}, {"$set": {
        "parsed_metadata.numero_atto": "99999999999999999999",
    }}))
    result = dossier(db)
    assert "SOURCE_DOCUMENT_IDENTITY_UNVERIFIED" in codes(result)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert result["evidence_summary"]["documentary_receipts"] == 0


def test_deleted_original_is_not_live_source_or_event_proof():
    db = run(with_source())
    run(db[COLL_DOCUMENTS_INBOX].update_one({"id": "notice-1"}, {"$set": {
        "entity_status": "deleted", "data_formazione_ruolo": "2003-09-01",
    }}))
    run(db[COLL_TAX_COLLECTION_EVENTS].insert_one({
        "id": "role-event", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": "ROLE_FORMATION", "effective_at": "2003-09-01", "source_document_id": "notice-1",
    }))
    result = dossier(db)
    assert not any(item.get("document_id") == "notice-1" for item in all_entries(result))
    assert not any(item["event_type"] == "ROLE_FORMATION" for item in all_entries(result))
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)


def test_multiple_exact_receipts_keep_canonical_attribution_ambiguous():
    db = run(with_source(data_formazione_ruolo="2003-09-01"))
    second = run(db[COLL_QUIETANZE_F24].find_one({"id": "receipt-1"}))
    second.pop("_id", None)
    second.update({"id": "receipt-2", "protocollo_telematico": "P-2"})
    run(db[COLL_QUIETANZE_F24].insert_one(second))
    result = dossier(db)
    assert "SOURCE_RECEIPTS_AMBIGUOUS" in codes(result)
    assert "SOURCE_PAID_BEFORE_ROLE" not in codes(result)
    assert result["evidence_summary"]["documentary_receipts"] == 0
    assert sum(item["event_type"] == "LINKED_RECEIPT_UNVERIFIED" for item in all_entries(result)) == 2


def test_canonical_plan_correspondence_and_copies_are_visible_without_claim_side_duplicate_links():
    """Shapes written by parse_rate_plan/archivia_richiesta_informazioni."""
    db = run(seed())
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "plan-1", "company_id": COMPANY, "plan_reference": "AR071000001",
        "document_references": [{"printed_reference": NUMBER[:17], "document_number": NUMBER}],
        "application_date": "2009-06-26", "source_document_id": "plan-original",
        "source_document_ids": ["plan-original", "plan-copy"],
    }))
    run(db[COLL_TAX_COLLECTION_DOCUMENTS].insert_one({
        "id": "request-1", "company_id": COMPANY, "linked_rate_plan_id": "plan-1",
        "link_status": "CONFIRMED", "status": "REQUEST_RECORDED_RESPONSE_NOT_FOUND",
        "source_document_id": "request-original", "payment_evidence": False,
        "acceptance_evidence": False, "response_evidence": False,
    }))
    for doc_id, kind in (("plan-original", "PIANO_RATEIZZAZIONE"),
                         ("plan-copy", "PIANO_RATEIZZAZIONE"),
                         ("request-original", "CORRISPONDENZA_ADE_R"),
                         ("answer-original", "RIGETTO_RATEIZZAZIONE")):
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({
            "id": doc_id, "company_id": COMPANY, "document_type": kind,
            "document_date": "2012-08-03", "filename": doc_id + ".pdf",
            "source_occurrences": [{"source": "drive", "drive_file_id": "drive-" + doc_id,
                                    "sha256": "a" * 64}],
        }))
    # A response can be attached canonically to the plan with page provenance.
    run(db[COLL_FISCAL_EVIDENCE].insert_one({
        "id": "answer-proof", "company_id": COMPANY, "document_id": "answer-original",
        "version_id": "answer-version", "page_number": 1, "field": "plan_reference",
    }))
    run(db[COLL_FISCAL_LINKS].insert_one({
        "id": "answer-link", "company_id": COMPANY, "entity_type": "tax_rate_plan",
        "entity_id": "plan-1", "status": "confirmed", "evidence_ids": ["answer-proof"],
    }))
    result = dossier(db)
    docs = {item["document_id"]: item for item in all_entries(result) if item.get("document_id")}
    assert set(docs) == {"plan-original", "plan-copy", "request-original", "answer-original"}
    assert docs["request-original"]["event_type"] == "CORRESPONDENCE"
    assert docs["answer-original"]["event_type"] == "REQUEST_REJECTED"
    assert docs["answer-original"]["evidence"][0]["page_number"] == 1
    assert docs["request-original"]["source_provenance"][0]["drive_file_id"] == "drive-request-original"
    assert docs["request-original"]["original_verified"] is False
    assert result["evidence_summary"]["documentary_receipts"] == 0
    assert result["coverage"]["correspondence_records"] == 1
    assert result["coverage"]["drive_inventory_verified"] is False
    assert "DRIVE_COVERAGE_NOT_VERIFIED" in codes(result)


@pytest.mark.parametrize("change", [
    {"company_id": "other"}, {"link_status": "UNRESOLVED_REFERENCE"},
    {"link_status": "REVOKED"}, {"linked_rate_plan_id": "plan-unrelated"},
])
def test_correspondence_needs_confirmed_same_company_plan_edge(change):
    db = run(seed())
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "plan-1", "company_id": COMPANY,
        "document_references": [{"document_number": NUMBER}],
    }))
    run(db[COLL_TAX_COLLECTION_DOCUMENTS].insert_one({
        "id": "request-1", "company_id": COMPANY, "linked_rate_plan_id": "plan-1",
        "link_status": "CONFIRMED", "source_document_id": "request-doc", **change,
    }))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": "request-doc", "company_id": COMPANY}))
    assert not any(item.get("document_id") == "request-doc" for item in all_entries(dossier(db)))


def test_expected_installments_and_payment_modules_never_become_receipts():
    db = run(seed())
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "plan-1", "company_id": COMPANY, "source_document_id": "plan-doc",
        "document_references": [{"document_number": NUMBER}],
        "payment_modules": [{"id": "module-1", "source_document_id": "module-doc",
                             "payment_evidence": False, "installments": [{"due_date": "2010-01-31"}]}],
    }))
    run(db[COLL_TAX_RATE_INSTALLMENTS].insert_one({
        "id": "installment-1", "company_id": COMPANY, "rate_plan_id": "plan-1",
        "installment_number": 1, "due_date": "2010-01-31", "amount": "100.00",
        "status": "EXPECTED", "payment_evidence": False, "source_document_id": "plan-doc",
        "created_at": "2026-10-17",
    }))
    for doc_id in ("plan-doc", "module-doc"):
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": doc_id, "company_id": COMPANY}))
    result = dossier(db)
    due = next(item for item in result["timeline"] if item["event_type"] == "RATE_INSTALLMENT_DUE")
    assert due["date"] == "2010-01-31" and "amount_cents" not in due
    module = next(item for item in result["undated"] if item["event_type"] == "PAYMENT_MODULE")
    assert module["evidence_level"] == "MODEL_ONLY"
    assert result["evidence_summary"]["documentary_receipts"] == 0
    assert result["evidence_summary"]["claim_allocated_cents"] == 0
    assert not any(item["date"] == "2026-10-17" for item in result["timeline"])


def test_settlement_exact_claim_edge_loads_source_module_and_installment_but_not_candidates():
    db = run(seed())
    run(db[COLL_TAX_SETTLEMENT_CLAIMS].insert_one({
        "id": "settlement-edge", "company_id": COMPANY, "claim_id": "claim-1",
        "settlement_application_id": "settlement-1", "relation_status": "CONFIRMED",
    }))
    run(db[COLL_TAX_SETTLEMENT_APPLICATIONS].insert_one({
        "id": "settlement-1", "company_id": COMPANY, "source_document_id": "offer-doc",
        "payment_evidence": False, "status": "PENDING_PAYMENT_EVIDENCE",
        "payment_modules": [{"id": "settlement-module", "source_document_id": "module-doc"}],
    }))
    run(db[COLL_TAX_SETTLEMENT_APPLICATIONS].insert_one({
        "id": "candidate-only", "company_id": COMPANY, "source_document_id": "candidate-doc",
        "related_document_candidates": [NUMBER],
    }))
    run(db[COLL_TAX_SETTLEMENT_INSTALLMENTS].insert_one({
        "id": "settlement-rate", "company_id": COMPANY,
        "settlement_application_id": "settlement-1", "due_date": "2023-10-31",
    }))
    for doc_id in ("offer-doc", "module-doc", "candidate-doc"):
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": doc_id, "company_id": COMPANY}))
    result = dossier(db)
    docs = {item.get("document_id") for item in all_entries(result)}
    assert {"offer-doc", "module-doc"}.issubset(docs) and "candidate-doc" not in docs
    assert any(item["event_type"] == "SETTLEMENT_INSTALLMENT_DUE" for item in result["timeline"])
    assert result["evidence_summary"]["documentary_receipts"] == 0
    assert not any(item["event_type"] == "SETTLEMENT_ACCEPTED" for item in all_entries(result))


def test_notification_and_legal_stores_retain_actual_dates_originals_and_namespace():
    db = run(seed())
    for collection, doc_id, fields in (
        (COLL_TAX_NOTIFICATION_EVENTS, "relata-doc", {"notification_date": "2004-01-15"}),
        (COLL_TAX_LEGAL_EVENTS, "request-doc", {"event_type": "RELIEF_REQUEST", "effective_at": "2004-02-03"}),
    ):
        run(db[collection].insert_one({
            "id": "same-id", "company_id": COMPANY, "claim_id": "claim-1",
            "source_document_id": doc_id, "created_at": "2026-10-17", **fields,
        }))
        run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": doc_id, "company_id": COMPANY}))
    result = dossier(db)
    event_entries = [item for item in result["timeline"] if item["evidence_level"] == "EVENT"]
    assert len(event_entries) == 2
    assert {item["date"] for item in event_entries} == {"2004-01-15", "2004-02-03"}
    assert {item["document_id"] for item in event_entries} == {"relata-doc", "request-doc"}
    assert not any(item["date"] == "2026-10-17" for item in result["timeline"])


@pytest.mark.parametrize("relationship,expected", [("CONFIRMED", True), ("PENDING", False), ("REVOKED", False)])
def test_plan_claim_allocation_only_traverses_confirmed_edge(relationship, expected):
    db = run(seed())
    run(db[COLL_TAX_RATE_PLAN_CLAIM_ALLOCATIONS].insert_one({
        "id": "edge-1", "company_id": COMPANY, "claim_id": "claim-1",
        "rate_plan_id": "plan-1", "relation_status": relationship,
    }))
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "plan-1", "company_id": COMPANY, "source_document_id": "plan-doc",
    }))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({"id": "plan-doc", "company_id": COMPANY}))
    assert any(item.get("document_id") == "plan-doc" for item in all_entries(dossier(db))) is expected


@pytest.mark.parametrize("kind,event_type", [
    ("ISTANZA_SGRAVIO", "RELIEF"), ("RIGETTO_SGRAVIO", "PARTIAL_RELIEF"),
    ("ISTANZA_SOSPENSIONE", "SUSPENSION_START"), ("PREAVVISO_RIGETTO", "RATE_PLAN_GRANTED"),
])
def test_request_refusal_or_pre_notice_cannot_prove_recorded_granted_event(kind, event_type):
    db = run(seed())
    run(db[COLL_TAX_LEGAL_EVENTS].insert_one({
        "id": "incorrect-outcome", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": event_type, "effective_at": "2004-02-03", "source_document_id": "request-doc",
    }))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "request-doc", "company_id": COMPANY, "document_type": kind,
    }))
    result = dossier(db)
    assert not any(item["event_type"] == event_type for item in all_entries(result))
    assert "EVENT_OUTCOME_NOT_PROVEN" in codes(result)
    assert result["safety"] == {"payment_inferred": False, "requests_submitted": False}


def test_missing_plan_original_is_reported_as_missing_reference_and_not_drive_completion():
    db = run(seed())
    run(db[COLL_TAX_RATE_PLANS].insert_one({
        "id": "plan-1", "company_id": COMPANY, "source_document_id": "not-imported",
        "document_references": [{"document_number": NUMBER}],
    }))
    before = run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    result = dossier(db)
    assert result["coverage"]["unavailable_document_ids"] == ["not-imported"]
    assert "LINKED_DOCUMENT_UNAVAILABLE" in codes(result)
    assert result["coverage"]["drive_inventory_verified"] is False
    assert run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"})) == before
    assert run(db[COLL_TAX_COLLECTION_EVENTS].count_documents({})) == 0


@pytest.mark.parametrize("sentinel", [
    "03/01/0001", "0001-01-03", "0001-01-03T00:00:00Z", "00010103",
    date(1, 1, 3), datetime(1, 1, 3),
])
def test_inps_empty_date_sentinel_is_undated_and_never_replaced_with_import_date(sentinel):
    db = run(seed(source_document_id="inps-document"))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "inps-document", "company_id": COMPANY, "document_type": "NOTA_RETTIFICA_INPS",
        "document_date": sentinel, "created_at": "2026-10-17",
    }))
    result = dossier(db)
    assert result["timeline"] == []
    assert result["undated"][0]["document_id"] == "inps-document"
    assert result["undated"][0]["date"] is None


@pytest.mark.parametrize("kind,event_type", [("SGRAVIO", "RELIEF"), ("SOSPENSIONE", "SUSPENSION_START")])
@pytest.mark.parametrize("review_fields", [
    {"classification": {"requires_review": True}, "review_status": "CLASSIFIED"},
    {"classification": {"requires_review": False}, "review_status": "TO_VERIFY"},
    {"classification": {"requires_review": False, "reasons": ["marker:sgravio"]},
     "review_status": "CLASSIFIED"},
    {"classification": {"requires_review": False,
                        "reasons": ["marker:sospensione legale della riscossione"]},
     "review_status": "CLASSIFIED"},
])
def test_unreviewed_provision_is_preserved_without_documenting_a_granted_outcome(kind, event_type, review_fields):
    db = run(seed(source_document_id="possible-provision"))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "possible-provision", "company_id": COMPANY, "document_type": kind,
        "document_date": "2004-02-03", **review_fields,
    }))
    run(db[COLL_TAX_LEGAL_EVENTS].insert_one({
        "id": "unreviewed-event", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": event_type, "effective_at": "2004-02-03", "source_document_id": "possible-provision",
    }))
    result = dossier(db)
    assert any(item["event_type"] == "POTENTIAL_PROVISION" for item in result["timeline"])
    assert not any(item["event_type"] in {"RELIEF", "SUSPENSION", "SUSPENSION_START"} for item in all_entries(result))
    assert {"EVENT_OUTCOME_NOT_PROVEN", "PROVISION_REVIEW_REQUIRED"}.issubset(codes(result))


def test_canonical_explicit_provision_without_pending_review_retains_documented_nature():
    db = run(seed(source_document_id="reviewed-provision"))
    run(db[COLL_FISCAL_DOCUMENTS].insert_one({
        "id": "reviewed-provision", "company_id": COMPANY, "document_type": "SGRAVIO",
        "classification": {"requires_review": False}, "review_status": "CLASSIFIED",
        "document_date": "2004-02-03",
    }))
    run(db[COLL_TAX_LEGAL_EVENTS].insert_one({
        "id": "reviewed-event", "company_id": COMPANY, "claim_id": "claim-1",
        "event_type": "RELIEF", "effective_at": "2004-02-03", "source_document_id": "reviewed-provision",
    }))
    result = dossier(db)
    assert sum(item["event_type"] == "RELIEF" for item in result["timeline"]) == 2
    assert "EVENT_OUTCOME_NOT_PROVEN" not in codes(result)


def test_official_positive_exact_quietanza_proves_fiscal_payment_without_bank_record():
    from app.services.fiscal_claim_source_reconciliation import build_claim_source_plan

    db = run(with_source(data_formazione_ruolo="2003-09-01"))
    reconciliation = run(build_claim_source_plan(db, company_id=COMPANY))
    assert reconciliation[0]["source_obligation_links"][0]["tax_lines"][0]["payment_evidence_status"] == "PAID_DOCUMENTED"
    result = dossier(db)
    receipt = next(item for item in result["timeline"] if item["event_type"] == "QUIETANZA_F24")
    assert result["evidence_summary"]["documentary_receipts"] == 1
    assert result["evidence_summary"]["bank_movements"] == 0
    assert "SOURCE_PAID_BEFORE_ROLE" in codes(result)
    assert "anche senza movimento bancario disponibile" in receipt["notes"][0]
    assert result["evidence_summary"]["claim_allocated_cents"] == 0  # Source contribution, not a duplicate payment of the cartella.
