import io
import zipfile

import pytest

from app.services import ader_snapshot_import as ader


COMPANY = "04523831214"
DATASET_SHA = "a" * 64


def _pdf(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_textbox(fitz.Rect(24, 24, 818, 571), text, fontsize=8)
    result = document.tobytes()
    document.close()
    return result


def test_current_layout_keeps_portal_and_business_status_separate():
    number = "07120240057143449000"
    filename = f"2026-08-10_{COMPANY}_{number}_Analitica_DaSaldare.pdf"
    content = _pdf(
        f"CARTELLA N. {number}\n"
        "Rateiz. Proc. Attive Def. age. NA AGENZIA ENTRATE "
        "01-01-2026 9.378,64 0,00 9.378,64 0,00 0,14 0,00 0,00 0,14 0,00 0,14 No No No"
    )

    row = ader.parse_analytic_pdf(
        content=content,
        filename=filename,
        source_archive_id="source",
        dataset_sha256=DATASET_SHA,
        threshold_cents=500,
    )

    assert row["portal_status"] == "DA_SALDARE"
    assert row["calculated_business_status"] == "MICRO_RESIDUAL_REVIEW"
    assert row["amounts_cents"]["net"] == 14
    assert row["payment_evidence"] is False


def test_suspended_position_is_not_marked_paid():
    status, reason = ader._business_status(
        net_cents=0,
        suspended_cents=409336,
        paid_cents=0,
        portal_bucket="SALDATI",
        threshold_cents=500,
    )
    assert status == "SUSPENDED_NO_CURRENT_PAYMENT"
    assert reason is None


def test_legacy_layout_preserves_unavailable_amounts_as_null():
    number = "07120140122231507000"
    filename = f"2026-08-10_{COMPANY}_{number}_Analitica_Saldati.pdf"
    content = _pdf(
        f"CARTELLA N. {number}\n"
        "NA COMUNE DI NAPOLI 01-01-2020 100,00 0,00 99,95 0,00 0,05 Ente/Ufficio: COMUNE"
    )
    row = ader.parse_analytic_pdf(
        content=content,
        filename=filename,
        source_archive_id="source",
        dataset_sha256=DATASET_SHA,
        threshold_cents=500,
    )
    assert row["source_layout"] == "LEGACY_5_AMOUNT"
    assert row["interest_amount"] is None
    assert row["suspended_amount"] is None
    assert row["net_payable_amount"] == 0.05


def test_rate_plan_resolves_only_unique_document_prefix(monkeypatch):
    monkeypatch.setattr(ader, "_pdf_text", lambda _content: (
        "identificativo 071812706 del 05/12/2024 Numero rate accordato: 18 "
        "07120240057143449 Importo Prima Rata imponibile € 5,88 € 777,98 17/12/2024 "
        "Successive scadenze Totale piano € 14.065,29 Per i carichi"
    ))
    plan = ader.parse_rate_plan(
        content=b"pdf",
        filename="Accoglimento_AR071812706.pdf",
        company_id=COMPANY,
        document_numbers=["07120240057143449000"],
        dataset_sha256=DATASET_SHA,
    )
    assert plan["plan_reference"] == "AR071812706"
    assert plan["first_installment_amount"] == 777.98
    assert plan["first_installment_due_date"] == "2024-12-17"
    assert plan["document_references"][0]["document_number"] == "07120240057143449000"
    assert plan["requires_review"] is False


def test_settlement_does_not_treat_offer_as_payment(monkeypatch):
    monkeypatch.setattr(ader, "_pdf_text", lambda _content: (
        "Documento rif. AT - 07190202302172623180 Documento 07190202302172623000 "
        "Cartella 07120220089305113000 Debito oggetto di definizione agevolata euro 202,18 "
        "Debito da pagare per la definizione euro 126,68"
    ))
    settlement = ader.parse_settlement(
        content=b"pdf",
        filename="07190202302172623000.pdf",
        company_id=COMPANY,
        dataset_sha256=DATASET_SHA,
    )
    assert settlement["collection_document_number"] == "07120220089305113000"
    assert settlement["amount_due"] == 126.68
    assert settlement["payment_evidence"] is False
    assert settlement["closure_reason"] == "SETTLEMENT_OFFER_WITHOUT_PAYMENT_PROOF"


def test_payment_module_rejoins_split_plan_reference(monkeypatch):
    monkeypatch.setattr(ader, "_pdf_text", lambda _content: (
        "DOCUMENTO N. 07198308127062530701 "
        "ISTANZA DI RATEIZZAZIONE N. AR071 - 812706 "
        "18 RATA entro il 17/05/2026 Euro 781,60"
    ))
    module = ader.parse_payment_module(
        content=b"pdf",
        filename="Modulo_pagamento_AR071812706_rata_6.pdf",
        company_id=COMPANY,
        dataset_sha256=DATASET_SHA,
    )
    assert module["plan_reference"] == "AR071812706"
    assert module["installment_numbers"] == [18]


def test_unsafe_zip_member_is_rejected():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.pdf", b"not-a-pdf")
    with pytest.raises(ValueError, match="Percorso non sicuro"):
        ader._safe_zip(payload.getvalue())
