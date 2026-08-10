from datetime import date

from app.services.fiscal_domain import (
    build_evidence, classify_document, classify_f24_line, evaluate_payment_status,
    evaluate_ravvedimento, fiscal_control_findings, match_ader_payment,
    rebuild_vat_credit_chain, reconstruct_collection_state,
)


def test_residuo_zero_non_significa_pagata():
    result = evaluate_payment_status(due_amount=0, allocations=[])
    assert result["payment_status"] == "TO_VERIFY"
    assert "residuo_zero_senza_causa_probatoria" in result["reasons"]


def test_pdf_f24_senza_prova_pagamento_non_chiude_obbligo():
    result = evaluate_payment_status(
        due_amount=100, allocations=[{"id": "a", "amount": 100, "evidence_types": ["F24"]}])
    assert result["payment_status"] == "DUE"
    assert result["rejected_allocations"][0]["reason"] == "payment_evidence_missing"


def test_prova_pagamento_con_date_determina_stato():
    result = evaluate_payment_status(
        due_amount=100, due_date=date(2026, 6, 16),
        allocations=[{"id": "a", "amount": 100, "payment_date": "2026-06-15",
                      "evidence_types": ["QUIETANZA_F24"]}])
    assert result["payment_status"] == "PAID_ON_TIME"


def test_matching_ader_esige_identita_forte_e_importo():
    weak = match_ader_payment({"cartella_number": "ABC", "amount": 10},
                              {"cartella_number": "ABC", "amount": 10})
    assert weak["matched"] is False
    strong = match_ader_payment({"cartella_number": "ABC", "amount": 10, "iuv": "I1"},
                                {"cartella_number": "ABC", "amount": 10, "iuv": "I1"})
    assert strong["matched"] is True


def test_chiusura_cartella_conserva_causa_separata():
    state = reconstruct_collection_state([
        {"id": "1", "effective_at": "2026-01-01", "event_type": "RELIEF", "amount": 50},
        {"id": "2", "effective_at": "2026-01-02", "event_type": "CLOSURE",
         "amount": 0, "closure_cause": "RELIEF"},
    ])
    assert state["collection_status"] == "CLOSED"
    assert state["total_paid"] == "0.00"
    assert state["total_relief"] == "50.00"


def test_ravvedimento_senza_regola_ufficiale_versionata_non_determinabile():
    result = evaluate_ravvedimento(due_date=date(2026, 1, 1), payment_date=date(2026, 1, 11),
                                   tax_amount=100, penalty_paid=0, interest_paid=0, rule=None)
    assert result["status"] == "NOT_DETERMINABLE"


def test_ravvedimento_usa_regola_con_hash_fonte():
    result = evaluate_ravvedimento(
        due_date=date(2026, 1, 1), payment_date=date(2026, 1, 11), tax_amount=1000,
        penalty_paid=10, interest_paid=1,
        rule={"id": "rule-v1", "valid_from": "2026-01-01", "source_hash": "abc",
              "penalty_rate": "0.01", "annual_interest_rate": "0.02"})
    assert result["status"] == "COMPLETE"
    assert result["rule_source_hash"] == "abc"


def test_ciclo_iva_e_f24_non_duplicano_costo():
    assert classify_f24_line("6012", 1)["vat_cycle"] == "monthly_december"
    assert classify_f24_line("6013", 1)["vat_cycle"] == "annual_advance"
    assert classify_f24_line("6099", 1)["vat_cycle"] == "annual_balance"
    assert classify_f24_line("6099", 1)["is_accounting_cost"] is False


def test_credito_iva_rileva_lineage_rotta_e_doppio_uso():
    result = rebuild_vat_credit_chain([
        {"id": "o", "year": 2025, "movement_type": "ORIGIN", "amount": 100, "evidence_ids": ["e"]},
        {"id": "o", "year": 2026, "movement_type": "OFFSET", "amount": 120, "evidence_ids": ["e2"]},
        {"id": "x", "year": 2026, "movement_type": "OFFSET", "amount": 1, "evidence_ids": []},
    ], 2025, 2026)
    codes = {item["code"] for item in result["errors"]}
    assert {"CREDIT_USED_TWICE", "CREDIT_LINEAGE_BREAK"} <= codes


def test_classifier_e_prova_pagina_sono_deterministici():
    classified = classify_document("cartella.pdf", "Agenzia Entrate Riscossione cartella di pagamento")
    assert classified["document_type"] == "CARTELLA_ADE_R"
    evidence = build_evidence(document_id="d", version_id="v", page_number=2,
                              field_name="numero", raw_value=" A-1 ", normalized_value="A1",
                              parser_version="p1", confidence=.9, reason="parser")
    assert evidence["page_number"] == 2
    assert evidence["normalized_value"] == "A1"


def test_controllo_segnala_pretese_non_revisionate():
    findings = fiscal_control_findings([], [{"id": "c", "current_due": 0}])
    assert {item["code"] for item in findings} == {
        "ZERO_WITHOUT_PAYMENT_EVIDENCE", "ORIGINAL_CLAIM_NOT_REVIEWED"}
