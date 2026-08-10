import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db_collections import (
    COLL_TAX_ALLOCATIONS,
    COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS,
    COLL_TAX_PAYMENTS,
    COLL_TAX_RATE_INSTALLMENTS,
    COLL_TAX_RATE_PLANS,
)
from app.services.fiscal_payment_reconciliation import (
    find_ader_payment_target,
    reconcile_fiscal_payment,
)


def _plan(*, two_claims=False):
    references = [{"document_number": "07120260000000000001"}]
    if two_claims:
        references.append({"document_number": "07120260000000000002"})
    return {
        "id": "plan-1",
        "company_id": "company-1",
        "plan_reference": "AR071123456",
        "document_references": references,
        "payment_modules": [{
            "document_number": "180071110618697515",
            "installments": [{"number": 18, "due_date": "2026-07-31", "amount": "284.00"}],
        }],
    }


def test_match_rata_ader_richiede_codice_forte_e_importo_esatto():
    assert find_ader_payment_target(
        payment={"identificativo_bolletta": "180071110618697515", "importo": 284},
        rate_plans=[_plan()], settlements=[],
    )["matched"] is True
    assert find_ader_payment_target(
        payment={"identificativo_bolletta": "180071110618697515", "importo": 283.99},
        rate_plans=[_plan()], settlements=[],
    )["matched"] is False
    assert find_ader_payment_target(
        payment={"importo": 284}, rate_plans=[_plan()], settlements=[],
    )["matched"] is False


def test_pagamento_cbill_collega_rata_e_cartelle_senza_duplicare_importo():
    async def scenario():
        db = AsyncMongoMockClient()["fiscal-payment-test"]
        await db[COLL_TAX_RATE_PLANS].insert_one(_plan(two_claims=True))
        for suffix in ("1", "2"):
            await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
                "id": f"claim-{suffix}", "company_id": "company-1",
                "collection_number": f"0712026000000000000{suffix}",
            })

        result = await reconcile_fiscal_payment(
            db, company_id="company-1",
            payment={
                "identificativo_bolletta": "180071110618697515",
                "importo": 284, "data_pagamento": "2026-07-21",
                "movimento_id": "bank-1",
            },
            source_type="RICEVUTA_CBILL", source_id="receipt-1",
        )
        assert result["matched"] is True
        assert set(result["linked_claim_ids"]) == {"claim-1", "claim-2"}
        assert result["bank_verified"] is True

        installment = await db[COLL_TAX_RATE_INSTALLMENTS].find_one({"rate_plan_id": "plan-1"})
        assert installment["status"] == "PAID_DOCUMENTED"
        assert installment["installment_number"] == 18
        assert await db[COLL_TAX_PAYMENTS].count_documents({}) == 1
        assert await db[COLL_TAX_ALLOCATIONS].count_documents({}) == 1
        events = await db[COLL_TAX_COLLECTION_EVENTS].find({}).to_list(10)
        assert len(events) == 2
        assert {event["amount"] for event in events} == {"0.00"}
        claims = await db[COLL_TAX_COLLECTION_CLAIMS].find({}).to_list(10)
        assert all(result["payment_id"] in claim["linked_payment_ids"] for claim in claims)

        # Idempotenza sulla stessa coppia prova/bersaglio.
        await reconcile_fiscal_payment(
            db, company_id="company-1",
            payment={"identificativo_bolletta": "180071110618697515", "importo": 284},
            source_type="RICEVUTA_CBILL", source_id="receipt-1",
        )
        assert await db[COLL_TAX_PAYMENTS].count_documents({}) == 1
        assert await db[COLL_TAX_ALLOCATIONS].count_documents({}) == 1

    asyncio.run(scenario())


def test_upload_auto_cbill_collega_rata_e_cartella(monkeypatch):
    from app.routers import documenti
    from app.services import pagopa_receipts
    from app.utils import upload_validation

    db = AsyncMongoMockClient()["upload-auto-cbill-test"]
    asyncio.run(db[COLL_TAX_RATE_PLANS].insert_one(_plan()))
    asyncio.run(db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": "claim-1", "company_id": "04523831214",
        "collection_number": "07120260000000000001",
    }))
    # Il piano del fixture deve appartenere alla stessa azienda configurata.
    asyncio.run(db[COLL_TAX_RATE_PLANS].update_one(
        {"id": "plan-1"}, {"$set": {"company_id": "04523831214"}},
    ))
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(upload_validation, "verifica_pdf_reale", lambda *_: None)
    monkeypatch.setattr(pagopa_receipts, "parse_receipt_pdf", lambda _content: {
        "identificativo_bolletta": "180071110618697515",
        "importo": 284.0,
        "data_pagamento": "2026-07-21",
        "text_detected": True,
    })

    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("quietanza_CBILL_rata_18.pdf", b"%PDF-1.4 fixture", "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow"] == "PAGOPA_CBILL_CANONICO"
    match = payload["data"]["riconciliazione_fiscale"]
    assert match["matched"] is True
    assert match["target_type"] == "rate_installment"
    assert match["linked_claim_ids"] == ["claim-1"]
    receipt = asyncio.run(db["ricevute_pagopa"].find_one({}))
    assert receipt["cartelle_collegate"] == ["claim-1"]
    claim = asyncio.run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"}))
    assert len(claim["payment_evidence_ids"]) == 1


def test_quietanza_f24_con_identificativo_ader_usa_lo_stesso_motore(monkeypatch):
    from app.services import f24_parser, quietanze_import

    db = AsyncMongoMockClient()["quietanza-f24-ader-test"]
    plan = _plan()
    plan["company_id"] = "04523831214"
    asyncio.run(db[COLL_TAX_RATE_PLANS].insert_one(plan))
    asyncio.run(db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": "claim-quietanza", "company_id": "04523831214",
        "collection_number": "07120260000000000001",
    }))
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: {
        "dati_generali": {
            "protocollo_telematico": "PROTO-F24",
            "identificativo_bolletta": "180071110618697515",
            "saldo_delega": 284.0,
            "data_pagamento": "2026-07-21",
            "codice_fiscale": "CF-ANONIMO",
        },
        "sezione_erario": [{
            "codice_tributo": "1040", "periodo_riferimento": "06/2026",
            "importo_debito": 284.0,
        }],
        "sezione_inps": [], "sezione_regioni": [],
        "sezione_tributi_locali": [], "sezione_inail": [],
        "totali": {"saldo_netto": 284.0},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0},
    })

    result = asyncio.run(quietanze_import.importa_quietanza_bytes(
        db, b"%PDF-quietanza-ader-anonima", "quietanza_f24_rata.pdf",
        fonte="documenti_upload_auto",
    ))

    assert result["riconciliazione_ader"]["matched"] is True
    assert result["riconciliazione_ader"]["target_type"] == "rate_installment"
    assert result["riconciliazione_ader"]["linked_claim_ids"] == ["claim-quietanza"]
