from datetime import date
import io
import zipfile

from app.services.fiscal_domain import (
    build_evidence,
    build_evidence_package_zip,
    classify_document,
    evaluate_payment_status,
    match_ader_payment,
    rebuild_vat_credit_chain,
    reconstruct_collection_state,
)


def test_pdf_f24_predisposto_non_prova_pagamento():
    result = evaluate_payment_status(
        due_amount="100.00",
        due_date=date(2026, 3, 16),
        allocations=[{"id": "a1", "amount": "100", "evidence_types": ["F24"]}],
    )
    assert result["payment_status"] == "DUE"
    assert result["rejected_allocations"][0]["reason"] == "payment_evidence_missing"


def test_quietanza_con_data_puo_provare_pagamento_puntuale():
    result = evaluate_payment_status(
        due_amount="100.00",
        due_date=date(2026, 3, 16),
        allocations=[{"id": "a1", "amount": "100", "payment_date": "2026-03-16", "evidence_types": ["QUIETANZA_F24"]}],
    )
    assert result["payment_status"] == "PAID_ON_TIME"
    assert result["residual_amount"] == "0.00"


def test_ader_matching_forte_usa_identificativo_e_importo():
    claim = {"cartella_number_original": "071-2024-001", "amount": "51.36", "payment_module_code": "180071110413418009"}
    payment = {"cartella_number": "0712024001", "amount": "51.36", "payment_module_code": "180071110413418009"}
    result = match_ader_payment(claim, payment)
    assert result["matched"] is True
    assert result["confidence_score"] == 100


def test_eventi_rendono_spiegabile_chiusura_e_sospensione():
    suspended = reconstruct_collection_state([
        {"id": "1", "event_type": "SUSPENSION_START", "effective_at": "2026-01-01", "amount": 0}
    ])
    assert suspended["collection_status"] == "SUSPENDED"
    closed = reconstruct_collection_state([
        {"id": "1", "event_type": "CLOSURE", "effective_at": "2026-01-02", "closure_cause": "RELIEF", "amount": 0}
    ])
    assert closed["collection_status"] == "CLOSED"
    assert "RELIEF" in closed["closure_causes"]


def test_credito_iva_non_puo_essere_usato_due_volte():
    movements = [
        {"id": "origin", "year": 2025, "movement_type": "ORIGIN", "amount": "100", "evidence_ids": ["e1"]},
        {"id": "use", "year": 2026, "movement_type": "OFFSET", "amount": "40", "evidence_ids": ["e2"]},
        {"id": "use", "year": 2026, "movement_type": "OFFSET", "amount": "40", "evidence_ids": ["e2"]},
    ]
    result = rebuild_vat_credit_chain(movements, 2025, 2026)
    assert result["balance"] == "60.00"
    assert {error["code"] for error in result["errors"]} == {"CREDIT_USED_TWICE"}


def test_classificazione_ed_evidenza_con_pagina():
    classification = classify_document("cartella.pdf", "Agenzia Entrate Riscossione cartella di pagamento")
    assert classification["document_type"] == "CARTELLA_ADE_R"
    evidence = build_evidence(
        document_id="doc", version_id="v1", page_number=3, field_name="importo",
        raw_value="1.234,56", normalized_value="1234.56", parser_version="test-v1",
        confidence=1, reason="fixture",
    )
    assert evidence["page_number"] == 3
    assert evidence["id"].startswith("evidence_")


def test_pacchetto_prove_preserva_hash_e_non_invia():
    payload = build_evidence_package_zip(
        claim={"id": "c1", "cartella_number_original": "071"},
        dossier_pdf=b"%PDF-test",
        originals=[{"filename": "originale.pdf", "content": b"originale"}],
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "BOZZA_RICHIESTA_RIESAME.txt" in names
        assert archive.read("originali/originale.pdf") == b"originale"
