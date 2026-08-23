import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.routers.operazioni_module import smart
from app.routers.bank import estratto_conto
from app.services.bank_payment_allocations import (
    reconcile_deterministic_invoice_allocations,
)
from app.services.bank_reconciliation_rules import classify_bank_movement
from app.services.riconciliazione_smart import semanticizza_risultato


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.mark.parametrize(
    "description,expected_rule,expected_type",
    [
        ("INC.POS NUMIA-AMEX DEL 10/08/2026 PDV 123", "bank.pos_credit.v1", "incasso_pos"),
        ("VERS. CONTANTI", "bank.cash_deposit.v1", "versamento_contanti"),
        ("SPESE - RILASCIO CARNET ASSEGNI", "bank.cheque_book_fee.v1", "commissione_bancaria"),
        ("INT. E COMP. - COMPETENZE", "bank.account_fee.v1", "commissione_bancaria"),
        ("ADDEBITO DIRETTO SDD MANDATO AB12", "bank.sdd_debit.v1", "fattura_sdd"),
    ],
)
def test_deterministic_bank_rules_expose_versioned_evidence(description, expected_rule, expected_type):
    movement = {"id": "M1", "descrizione": description, "importo": -10.25, "data": "2026-08-10"}
    result = classify_bank_movement(movement)
    assert result["rule_id"] == expected_rule
    assert result["rule_version"]
    assert result["tipo"] == expected_type
    assert result["evidenze"]


def test_semantic_contract_separates_automatic_classification_from_ambiguous_target():
    movement = {"id": "M1", "descrizione": "VERS. CONTANTI", "importo": 500, "data": "2026-08-10"}
    result = semanticizza_risultato({"suggerimenti": [], "associazione_automatica": False}, movement)
    assert result["decisione"] == "automatica"
    assert result["regola"]["id"] == "bank.cash_deposit.v1"
    assert result["target_ids"] == []
    assert result["quadratura"]["stato"] == "non_applicabile"


def test_manual_bank_payment_supports_many_invoices_and_is_idempotent(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["bank_many"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M1", "data": "2026-07-17", "importo": -300.00,
            "descrizione": "LEASYS SALDO FATTURE 000001 000002",
        })
        await db.invoices.insert_many([
            {"id": "F1", "invoice_number": "000001", "invoice_date": "2026-07-01", "supplier_name": "Leasys", "supplier_vat": "0123", "total_amount": 100.0},
            {"id": "F2", "invoice_number": "000002", "invoice_date": "2026-07-02", "supplier_name": "Leasys", "supplier_vat": "0123", "total_amount": 200.0},
        ])
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        request = smart.RiconciliaManuale(
            movimento_id="M1", tipo="fattura_sdd",
            associazioni=[
                {"id": "F1", "quota_cents": 10000},
                {"id": "F2", "quota_cents": 20000},
            ],
        )
        result = await smart.riconcilia_manuale(request)
        assert result["quadratura"] == {
            "movimento_cents": 30000, "allocato_cents": 30000, "stato": "verificata",
        }
        movement = await db.estratto_conto_movimenti.find_one({"id": "M1"}, {"_id": 0})
        assert movement["fattura_ids"] == ["F1", "F2"]
        assert await db.bank_payment_allocations.count_documents({}) == 2
        assert await db.prima_nota_banca.count_documents({}) == 1
        pn = await db.prima_nota_banca.find_one({}, {"_id": 0})
        assert pn["importo"] == 300
        assert pn["fattura_ids"] == ["F1", "F2"]
        for invoice_id in ("F1", "F2"):
            invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
            assert invoice["pagato"] is True
            assert invoice["payment_allocation_status"] == "valid"

        second = await smart.riconcilia_manuale(request)
        assert second["idempotent"] is True
        assert await db.bank_payment_allocations.count_documents({}) == 2
        assert await db.prima_nota_banca.count_documents({}) == 1

    run(scenario())


def test_many_invoice_allocation_rejects_non_square_total_before_writes(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["bank_many_invalid"]
        await db.estratto_conto_movimenti.insert_one({"id": "M1", "importo": -300.0})
        await db.invoices.insert_many([
            {"id": "F1", "supplier_vat": "0123", "total_amount": 100.0},
            {"id": "F2", "supplier_vat": "0123", "total_amount": 200.0},
        ])
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await smart.riconcilia_manuale(smart.RiconciliaManuale(
                movimento_id="M1", tipo="fattura",
                associazioni=[
                    {"id": "F1", "quota_cents": 10000},
                    {"id": "F2", "quota_cents": 19000},
                ],
            ))
        assert exc.value.status_code == 409
        assert "Quadratura" in exc.value.detail
        assert await db.bank_payment_allocations.count_documents({}) == 0
        movement = await db.estratto_conto_movimenti.find_one({"id": "M1"}, {"_id": 0})
        assert not movement.get("riconciliato")

    run(scenario())


def test_bank_api_reports_loaded_rows_separately_from_real_total(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["bank_totals"]
        await db.estratto_conto_movimenti.insert_many([
            {"id": f"M{i}", "data": "2026-08-10", "importo": i + 1}
            for i in range(60)
        ])
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        result = await smart.banca_veloce(limit=50, anno=2026)
        assert result["stats"]["totale_righe"] == 60
        assert result["stats"]["righe_caricate"] == 50
        assert len(result["movimenti"]) == 50

    run(scenario())


def test_import_orchestrator_can_apply_unique_referenced_invoice_set(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["bank_auto_many"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M1", "data": "2026-07-17", "importo": -300,
            "descrizione": "ADDEBITO DIRETTO SDD LEASYS SALDO FATTURE 000001 000002",
        })
        await db.invoices.insert_many([
            {"id": "F1", "invoice_number": "000001", "invoice_date": "2026-07-01", "supplier_name": "Leasys", "supplier_vat": "0123", "total_amount": 100},
            {"id": "F2", "invoice_number": "000002", "invoice_date": "2026-07-02", "supplier_name": "Leasys", "supplier_vat": "0123", "total_amount": 200},
        ])
        result = await reconcile_deterministic_invoice_allocations(db, movement_ids=["M1"])
        assert result["allocati"] == 1
        movement = await db.estratto_conto_movimenti.find_one({"id": "M1"}, {"_id": 0})
        assert movement["fattura_ids"] == ["F1", "F2"]

    run(scenario())


def test_auto_match_unique_supplier_amount_reconciles_without_operator():
    async def scenario():
        db = MemorySheetsClient()["bank_auto_supplier"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M-FERRANTINI", "data": "2026-08-06", "importo": -1332.24,
            "tipo": "uscita", "descrizione": "BONIFICO FULVIO FERRANTINI",
        })
        await db.invoices.insert_one({
            "id": "F-FERRANTINI", "invoice_number": "FPR 105/26",
            "invoice_date": "2026-08-06", "supplier_name": "FULVIO FERRANTINI",
            "supplier_vat": "04997201217", "total_amount": 1332.24,
        })

        result = await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["M-FERRANTINI"],
        )

        assert result["allocati_identita"] == 1
        invoice = await db.invoices.find_one({"id": "F-FERRANTINI"}, {"_id": 0})
        movement = await db.estratto_conto_movimenti.find_one({"id": "M-FERRANTINI"}, {"_id": 0})
        assert invoice["pagato"] is True
        assert movement["fattura_id"] == "F-FERRANTINI"
        assert movement["tipo_riconciliazione"] == "automatico_fattura_identita"

    run(scenario())


def test_auto_match_amount_only_stays_unconfirmed():
    async def scenario():
        db = MemorySheetsClient()["bank_auto_amount_only"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M1", "data": "2026-08-06", "importo": -1332.24,
            "tipo": "uscita", "descrizione": "BONIFICO GENERICO",
        })
        await db.invoices.insert_one({
            "id": "F1", "invoice_number": "FPR 105/26",
            "invoice_date": "2026-08-06", "supplier_name": "FULVIO FERRANTINI",
            "total_amount": 1332.24,
        })

        result = await reconcile_deterministic_invoice_allocations(db, movement_ids=["M1"])

        assert result["allocati_identita"] == 0
        assert not (await db.invoices.find_one({"id": "F1"})).get("pagato")
        assert not (await db.estratto_conto_movimenti.find_one({"id": "M1"})).get("riconciliato")

    run(scenario())


def test_auto_match_duplicate_same_supplier_amount_stays_ambiguous():
    async def scenario():
        db = MemorySheetsClient()["bank_auto_ambiguous"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M1", "data": "2026-08-06", "importo": -100,
            "tipo": "uscita", "descrizione": "BONIFICO ALFA FORNITURE",
        })
        await db.invoices.insert_many([
            {"id": "F1", "invoice_number": "A-1", "invoice_date": "2026-08-01", "supplier_name": "ALFA FORNITURE", "total_amount": 100},
            {"id": "F2", "invoice_number": "A-2", "invoice_date": "2026-08-02", "supplier_name": "ALFA FORNITURE", "total_amount": 100},
        ])

        result = await reconcile_deterministic_invoice_allocations(db, movement_ids=["M1"])

        assert result["allocati_identita"] == 0
        assert result["ambigui_identita"] == 1
        assert not (await db.estratto_conto_movimenti.find_one({"id": "M1"})).get("riconciliato")

    run(scenario())


def test_auto_match_withholding_closes_supplier_net_and_leaves_tax_due():
    async def scenario():
        db = MemorySheetsClient()["bank_auto_withholding"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "M-NETTO", "data": "2026-08-06", "importo": -3206.40,
            "tipo": "uscita", "descrizione": "BONIFICO STUDIO ALFA FPR 105/26",
        })
        await db.invoices.insert_one({
            "id": "F-RIT", "invoice_number": "FPR 105/26",
            "invoice_date": "2026-08-01", "supplier_name": "STUDIO ALFA",
            "total_amount": 3806.40, "ritenuta_importo": 600.0,
            "pagamento_rate_totale": 3206.40,
        })
        await db.ritenute_acconto.insert_one({
            "id": "RIT-F-RIT", "fattura_id": "F-RIT", "importo": 600.0,
            "periodo_ritenuta": "2026-08", "stato": "da_pagare",
        })

        result = await reconcile_deterministic_invoice_allocations(
            db, movement_ids=["M-NETTO"],
        )

        assert result["allocati_identita"] == 1
        invoice = await db.invoices.find_one({"id": "F-RIT"}, {"_id": 0})
        withholding = await db.ritenute_acconto.find_one({"id": "RIT-F-RIT"}, {"_id": 0})
        assert invoice["pagato"] is True
        assert invoice["totale_pagabile_fornitore"] == 3206.40
        assert invoice["ritenuta_non_pagabile_fornitore"] == 600.0
        assert invoice["importo_residuo"] == 0
        assert withholding["stato"] == "da_pagare"
        assert not withholding.get("data_pagamento")

    run(scenario())


def test_anomaly_analysis_is_read_only(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["bank_anomalies"]
        await db.estratto_conto_movimenti.insert_many([
            {"id": "M1", "data": "2026-01-01", "fingerprint": "same", "importo": -10},
            {"id": "M2", "data": "2026-01-02", "fingerprint": "same", "importo": -10},
        ])
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        before = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(10)
        report = await smart.analizza_anomalie_banca(anno=2026)
        after = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(10)
        assert report["sola_lettura"] is True
        assert report["totale_anomalie"] == 1
        assert before == after

    run(scenario())


def test_bank_statement_delete_endpoints_are_blocked():
    with pytest.raises(HTTPException) as single:
        run(estratto_conto.elimina_singolo_movimento("M1"))
    assert single.value.status_code == 409
    with pytest.raises(HTTPException) as clear:
        run(estratto_conto.clear_estratto_conto(anno=2026))
    assert clear.value.status_code == 409
