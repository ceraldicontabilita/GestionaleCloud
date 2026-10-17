import asyncio
from decimal import Decimal

import pytest

from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_QUIETANZE_F24,
    COLL_TAX_ALLOCATIONS,
    COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS,
    COLL_TAX_PAYMENTS,
    COLL_TAX_RATE_PLANS,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_collection_payment_context import load_collection_payment_context
from app.services.fiscal_claim_source_reconciliation import build_claim_source_plan
from app.services.fiscal_payment_reconciliation import (
    reconcile_direct_collection_receipt,
    reconcile_fiscal_payment,
)


def _claim(suffix):
    return {
        "id": "claim-" + suffix, "company_id": "company-1",
        "collection_number": "0712026000000000000" + suffix,
        "linked_payment_ids": ["payment-1"],
    }


def _payment(**values):
    return {
        "id": "payment-1", "company_id": "company-1",
        "source_type": "RICEVUTA_CBILL", "source_id": "receipt-1",
        "operation_amount": "284.00", "documentary_evidence": True,
        "bank_verified": False, **values,
    }


async def _context(*, claims, payment=None, allocations=(), events=(), selected=None):
    db = ClientArchivioMemoria()["claim-collection-payments"]
    await db[COLL_TAX_COLLECTION_CLAIMS].insert_many(claims)
    if allocations:
        await db[COLL_TAX_ALLOCATIONS].insert_many([
            {"company_id": "company-1", "payment_id": "payment-1",
             "entity_type": "tax_collection_claim", **allocation}
            for allocation in allocations
        ])
    if events:
        await db[COLL_TAX_COLLECTION_EVENTS].insert_many([
            {"company_id": "company-1", "payment_id": "payment-1", **event}
            for event in events
        ])
    return await load_collection_payment_context(
        db, company_id="company-1", claims=claims if selected is None else selected,
        payments_by_id={"payment-1": payment or _payment()},
    )


def test_ricevuta_legacy_collegata_a_singola_cartella_conserva_importo_e_banca_separata():
    context = asyncio.run(_context(claims=[_claim("1")]))

    assert context["claim-1"]["ambiguous_payment_ids"] == []
    assert context["claim-1"]["documented_payments"] == [{
        "payment_id": "payment-1", "source_type": "RICEVUTA_CBILL",
        "source_id": "receipt-1", "document_id": None, "amount": "284.00",
        "payment_date": None, "bank_verified": False,
    }]


def test_rata_condivisa_senza_quote_non_attribuisce_il_totale_a_nessuna_cartella():
    context = asyncio.run(_context(
        claims=[_claim("1"), _claim("2")],
        payment=_payment(bank_verified=True),
        events=[
            {"claim_id": "claim-1", "amount": "0.00", "shared_plan_payment": True},
            {"claim_id": "claim-2", "amount": "0.00", "shared_plan_payment": True},
        ],
    ))

    assert all(item["documented_payments"] == [] for item in context.values())
    assert all(item["ambiguous_payment_ids"] == ["payment-1"] for item in context.values())


def test_singola_cartella_selezionata_non_nasconde_altre_cartelle_della_ricevuta():
    context = asyncio.run(_context(
        claims=[_claim("1"), _claim("2")], selected=[_claim("1")],
    ))

    assert context == {"claim-1": {
        "documented_payments": [], "ambiguous_payment_ids": ["payment-1"],
    }}


def test_rata_con_altra_cartella_non_importata_rimane_ambigua():
    context = asyncio.run(_context(
        claims=[_claim("1")],
        events=[{"claim_id": "claim-1", "amount": "0.00", "shared_plan_payment": True}],
    ))

    assert context["claim-1"]["documented_payments"] == []
    assert context["claim-1"]["ambiguous_payment_ids"] == ["payment-1"]


def test_quote_esplicite_quadrate_conservano_esattamente_il_totale_della_ricevuta():
    context = asyncio.run(_context(
        claims=[_claim("1"), _claim("2")],
        allocations=[
            {"entity_id": "claim-1", "amount": "100.01"},
            {"entity_id": "claim-2", "amount": "183.99"},
            {"entity_type": "tax_rate_installment", "entity_id": "installment-1", "amount": "284.00"},
        ],
    ))

    receipts = [item for claim in context.values() for item in claim["documented_payments"]]
    assert [item["amount"] for item in receipts] == ["100.01", "183.99"]
    assert sum(Decimal(item["amount"]) for item in receipts) == Decimal("284.00")
    assert all(item["ambiguous_payment_ids"] == [] for item in context.values())


def test_quota_unica_pari_al_totale_non_nasconde_destinatario_conosciuto_senza_riparto():
    context = asyncio.run(_context(
        claims=[_claim("1"), _claim("2")],
        payment=_payment(direct_collection_numbers=[_claim("1")["collection_number"],
                                                    _claim("2")["collection_number"]]),
        allocations=[{"entity_id": "claim-1", "amount": "284.00"}],
        events=[{"claim_id": "claim-1", "amount": "0.00", "shared_plan_payment": True},
                {"claim_id": "claim-2", "amount": "0.00", "shared_plan_payment": True}],
    ))
    assert all(item["documented_payments"] == [] for item in context.values())
    assert all(item["ambiguous_payment_ids"] == ["payment-1"] for item in context.values())


def test_quote_non_coprono_cartella_nominata_nella_ricevuta_ma_non_importata():
    context = asyncio.run(_context(
        claims=[_claim("1")],
        payment=_payment(direct_collection_numbers=[_claim("1")["collection_number"],
                                                    _claim("2")["collection_number"]]),
        allocations=[{"entity_id": "claim-1", "amount": "284.00"}],
    ))
    assert context["claim-1"]["documented_payments"] == []
    assert context["claim-1"]["ambiguous_payment_ids"] == ["payment-1"]


def test_evento_di_altra_cartella_impedisce_assegnazione_integrale_anche_con_quota():
    context = asyncio.run(_context(
        claims=[_claim("1")],
        allocations=[{"entity_id": "claim-1", "amount": "284.00"}],
        events=[{"claim_id": "claim-1", "amount": "0.00", "shared_plan_payment": True},
                {"claim_id": "claim-2", "amount": "0.00", "shared_plan_payment": True}],
    ))
    assert context["claim-1"]["documented_payments"] == []
    assert context["claim-1"]["ambiguous_payment_ids"] == ["payment-1"]


def test_riferimento_a_ricevuta_non_risolta_rimane_da_verificare():
    async def scenario():
        db = ClientArchivioMemoria()["unresolved-receipt-reference"]
        return await load_collection_payment_context(
            db, company_id="company-1", claims=[_claim("1")], payments_by_id={},
        )
    assert asyncio.run(scenario()) == {"claim-1": {
        "documented_payments": [], "ambiguous_payment_ids": ["payment-1"],
    }}


@pytest.mark.parametrize("allocations", [
    [{"entity_id": "claim-1", "amount": "284.00"},
     {"entity_id": "claim-2", "amount": "284.00"}],
    [{"entity_id": "claim-1", "amount": "100.00"},
     {"entity_id": "claim-2", "amount": "183.99"}],
    [{"entity_id": "claim-1", "amount": "100.00"},
     {"entity_id": "claim-1", "amount": "184.00"}],
    [{"entity_id": "claim-1", "amount": "285.00"},
     {"entity_id": "claim-2", "amount": "-1.00"}],
])
def test_quote_duplicate_negative_o_non_quadrate_non_documentano_un_pagamento(allocations):
    context = asyncio.run(_context(
        claims=[_claim("1"), _claim("2")], allocations=allocations,
    ))

    assert all(item["documented_payments"] == [] for item in context.values())
    assert all(item["ambiguous_payment_ids"] == ["payment-1"] for item in context.values())


@pytest.mark.parametrize("payment", [
    _payment(source_kind="F24_DOCUMENT_EVIDENCE"),
    _payment(documentary_evidence=False, bank_verified=True),
])
def test_modello_f24_e_sola_banca_non_sono_ricevute_di_pagamento_della_cartella(payment):
    context = asyncio.run(_context(claims=[_claim("1")], payment=payment))

    assert context["claim-1"] == {"documented_payments": [], "ambiguous_payment_ids": []}


async def _paid_source(db, *, business_status="RELIEVED"):
    claims = [{**_claim("1"), "linked_payment_ids": [],
               "business_status": business_status,
               "documentary_payment_status": "PAID_DOCUMENTED"},
              {**_claim("2"), "linked_payment_ids": []}]
    await db[COLL_TAX_COLLECTION_CLAIMS].insert_many(claims)
    await db[COLL_DOCUMENTS_INBOX].insert_one({
        "id": "notice-1", "tax_collection_claim_id": "claim-1",
        "parsed_metadata": {
            "numero_atto": claims[0]["collection_number"],
            "matricola_inps": "5124776507",
            "testo_estratto": """
001       8050-Modello DM 10
CONTRIBUTI                           DA 11/2024 A 11/2024                3.921,00                   0,00               3.921,00
""",
        },
    })
    await db[COLL_QUIETANZE_F24].insert_one({
        "id": "quietanza-originaria", "codice_fiscale": "company-1",
        "protocollo_telematico": "PROTO-ORIGINALE", "data_pagamento": "2025-06-25",
        "sezione_inps": [{
            "causale": "RC01", "matricola": "5124776507",
            "periodo_riferimento": "11/2024", "importo_debito_cents": 409000,
        }],
    })
    return claims


@pytest.mark.parametrize("business_status", ["PAYABLE", "RELIEVED"])
def test_rata_condivisa_senza_riparto_non_genera_istanze_di_rimborso_o_sgravio(business_status):
    async def scenario():
        db = ClientArchivioMemoria()["shared-installment-source-plan"]
        claims = await _paid_source(db, business_status=business_status)
        await db[COLL_TAX_RATE_PLANS].insert_one({
            "id": "plan-1", "company_id": "company-1",
            "document_references": [
                {"document_number": claim["collection_number"]} for claim in claims
            ],
            "payment_modules": [{
                "document_number": "180071110618697515",
                "installments": [{"number": 18, "amount": "284.00"}],
            }],
        })
        result = await reconcile_fiscal_payment(
            db, company_id="company-1",
            payment={"identificativo_bolletta": "180071110618697515", "importo": "284.00"},
            source_type="RICEVUTA_CBILL", source_id="receipt-shared-1",
        )

        assert result["matched"] is True
        assert set(result["linked_claim_ids"]) == {"claim-1", "claim-2"}
        plan = await build_claim_source_plan(db, company_id="company-1")

        assert plan[0]["source_obligation_links"][0]["tax_lines"][0][
            "payment_evidence_status"
        ] == "PAID_DOCUMENTED"
        assert plan[0]["remediation_alert"] is None
        payments = await db[COLL_TAX_PAYMENTS].find({}).to_list(None)
        assert len(payments) == 1
        assert payments[0]["operation_amount"] == "284.00"
        events = await db[COLL_TAX_COLLECTION_EVENTS].find({}).to_list(None)
        assert sum(Decimal(event["amount"]) for event in events) == 0

    asyncio.run(scenario())


def test_rimborso_proposto_mostra_solo_quota_documentata_della_cartella():
    async def scenario():
        db = ClientArchivioMemoria()["allocated-receipt-source-plan"]
        claims = await _paid_source(db)
        result = await reconcile_direct_collection_receipt(
            db, company_id="company-1",
            payment={
                "amount": "284.00",
                "documenti": [
                    {"numero": claims[0]["collection_number"], "totale": "100.01", "quadra": True},
                    {"numero": claims[1]["collection_number"], "totale": "183.99", "quadra": True},
                ],
            },
            source_type="RICEVUTA_PAGOPA", source_id="receipt-split-1",
            document_id="receipt-original", version_id="receipt-version",
        )

        assert result["matched"] is True
        plan = await build_claim_source_plan(db, company_id="company-1")
        remediation = plan[0]["remediation_alert"]

        assert remediation["action"] == "VERIFY_REFUND_REQUEST"
        assert remediation["direct_collection_payments"][0]["amount"] == "100.01"
        assert remediation["direct_collection_payments"][0]["bank_verified"] is False
        claims = await db[COLL_TAX_COLLECTION_CLAIMS].find({}).to_list(None)
        payments = await db[COLL_TAX_PAYMENTS].find({}).to_list(None)
        context = await load_collection_payment_context(
            db, company_id="company-1", claims=claims,
            payments_by_id={payment["id"]: payment for payment in payments},
        )
        assert sum(
            Decimal(payment["amount"])
            for claim in context.values() for payment in claim["documented_payments"]
        ) == Decimal("284.00")

    asyncio.run(scenario())


def test_stato_documentale_senza_ricevuta_attribuita_non_genera_rimborso():
    async def scenario():
        db = ClientArchivioMemoria()["stale-documentary-paid-source-plan"]
        await _paid_source(db)

        plan = await build_claim_source_plan(db, company_id="company-1")

        assert plan[0]["source_obligation_links"][0]["tax_lines"][0][
            "payment_evidence_status"
        ] == "PAID_DOCUMENTED"
        assert plan[0]["remediation_alert"] is None

    asyncio.run(scenario())
