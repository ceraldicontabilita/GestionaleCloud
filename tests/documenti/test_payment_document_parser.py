import asyncio

import fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.sheets_document_store import MemorySheetsClient

from app.routers import documenti
from app.services.pagopa_receipts import parse_receipt_pdf
from tests.document_preview_helpers import confirmed_preview_headers


def _pdf(*lines: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    y = 40
    for line in lines:
        page.insert_text((35, y), line, fontsize=9)
        y += 16
    content = document.tobytes()
    document.close()
    return content


def _cbill_pdf() -> bytes:
    return _pdf(
        "Identificativo bolletta:", "Numero bolletta:", "Importo:",
        "Commissioni:", "Totale:", "180071502664980543", "8007150266",
        "126,68 EUR", "2,85 EUR", "129,53 EUR", "Stato operazione:",
        "Confermata - Eseguita", "Data esecuzione:", "11/09/2023",
        "Informaz. aggiuntive:", "CBILL - pagoPA", "Beneficiario:",
        "AGENZIA DELLE ENTRATE - RISCOSSIONE", "Codice benef.:", "AJZ8Z",
        "N. versamento:", "IW3254069973",
    )


def test_cbill_separa_operazione_commissione_e_totale():
    parsed = parse_receipt_pdf(_cbill_pdf(), "documento_bancario.pdf")

    assert parsed["document_kind"] == "RICEVUTA_CBILL"
    assert parsed["identificativo_bolletta"] == "180071502664980543"
    assert parsed["operation_amount_cents"] == 12668
    assert parsed["fee_amount_cents"] == 285
    assert parsed["bank_debit_total_cents"] == 12953
    assert parsed["data_pagamento"] == "2023-09-11"
    assert parsed["beneficiario"] == "AGENZIA DELLE ENTRATE - RISCOSSIONE"
    assert parsed["is_payment_receipt"] is True
    assert parsed["field_evidence"]["importo_operazione"]["page_number"] == 1
    assert parsed["field_evidence"]["importo_operazione"]["source_text"] == "126,68 EUR"
    assert len(parsed["field_evidence"]["importo_operazione"]["bbox"]) == 4


@pytest.mark.parametrize(
    ("code", "operation", "fee", "total"),
    [
        ("301001500092427141", "80,00", "2,85", "82,85"),
        ("180071502664980543", "126,68", "2,85", "129,53"),
        ("180071108057937558", "46,92", "2,85", "49,77"),
        ("180071108462062586", "122,48", "2,85", "125,33"),
        ("301000000013560150", "1.400,00", "2,85", "1.402,85"),
    ],
)
def test_cinque_layout_cbill_audit_restano_esatti_al_centesimo(code, operation, fee, total):
    content = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "CBILL - pagoPA",
        "CODICE IDENTIFICATIVO CBILL", code,
        "IMPORTO OPERAZIONE", operation, "COMMISSIONI", fee, "TOTALE", total,
        "CODICE TRANSAZIONE CBILL 03575825444", "CODICE SIA BILLER AJZ8Z",
    )

    parsed = parse_receipt_pdf(content, "nome_generico.pdf")

    expected_operation = int(operation.replace(".", "").replace(",", ""))
    expected_fee = int(fee.replace(".", "").replace(",", ""))
    expected_total = int(total.replace(".", "").replace(",", ""))
    assert parsed["document_kind"] == "RICEVUTA_CBILL"
    assert parsed["operation_amount_cents"] == expected_operation
    assert parsed["fee_amount_cents"] == expected_fee
    assert parsed["bank_debit_total_cents"] == expected_total
    assert parsed["identifiers"]["identificativo_bolletta"] == {
        "raw": code, "normalized": code,
    }
    assert parsed["transaction_code"] == "03575825444"


@pytest.mark.parametrize(
    ("operation", "total"),
    [("917,10", "919,95"), ("34,90", "37,75"), ("8,86", "11,71"), ("147,72", "150,57")],
)
def test_quattro_bollettini_postali_audit_separano_obbligo_e_addebito(operation, total):
    content = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "BOLLETTINO POSTALE",
        "C/C POSTALE N. 123456789", "IMPORTO OPERAZIONE", operation,
        "COMMISSIONI", "2,85", "TOTALE ADDEBITO", total,
        "COD.RIF ABC123456789", "ID. POSTE 06209227663", "N.op PVV427665443",
    )

    parsed = parse_receipt_pdf(content, "documento.pdf")

    assert parsed["document_kind"] == "RICEVUTA_BOLLETTINO_POSTALE"
    assert parsed["operation_amount_cents"] == int(operation.replace(".", "").replace(",", ""))
    assert parsed["fee_amount_cents"] == 285
    assert parsed["bank_debit_total_cents"] == int(total.replace(".", "").replace(",", ""))
    assert parsed["identificativo_bolletta"] == "ABC123456789"
    assert parsed["postal_account_number"] == "123456789"
    assert parsed["identifiers"]["postal_account_number"]["raw"] == "123456789"


def test_mav_e_bollettino_postale_restano_tipi_distinti():
    mav = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "07/03/2023", "IMPORTO OPERAZIONE",
        "57,09-", "COMMISSIONI", "0,00-", "NUMERO BOLLETTINO 06230735214799405",
        ">> PAGAMENTO MAV TRAMITE INTERNET BANKING",
        ">> CODICE OPERAZIONE: IW3066035681", "Rinnovo servizio annuale",
    )
    postal = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "02/10/2024", "IMPORTO TOTALE", "37,75- EUR",
        "COMMISSIONI", "2,85-", "IMPORTO OPERAZIONE", "34,90-",
        ">> COD.RIF - 660002024057741522", ">> ID. POSTE - 06209227663",
        ">> BOLLETTINO POSTALE - N.op PVV427665443", "COMUNE TEST", "EUR148",
    )

    parsed_mav = parse_receipt_pdf(mav, "pagamento.pdf")
    parsed_postal = parse_receipt_pdf(postal, "pagamento.pdf")
    assert documenti.detect_document_type("pagamento.pdf", mav) == "ricevuta_mav"
    assert parsed_mav["document_kind"] == "RICEVUTA_MAV"
    assert parsed_mav["numero_bollettino"] == "06230735214799405"
    assert parsed_mav["operation_amount_cents"] == parsed_mav["bank_debit_total_cents"] == 5709
    assert documenti.detect_document_type("pagamento.pdf", postal) == "ricevuta_bollettino_postale"
    assert parsed_postal["document_kind"] == "RICEVUTA_BOLLETTINO_POSTALE"
    assert parsed_postal["operation_amount_cents"] == 3490
    assert parsed_postal["fee_amount_cents"] == 285
    assert parsed_postal["bank_debit_total_cents"] == 3775


def test_rav_non_viene_confuso_con_mav_o_pagopa():
    rav = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "20/12/2023", "IMPORTO OPERAZIONE",
        "46,92-", "COMMISSIONI", "2,85-", "TOTALE", "49,77-",
        "NUMERO BOLLETTINO 180071108057937558",
        ">> PAGAMENTO RAV TRAMITE INTERNET BANKING",
        ">> CODICE OPERAZIONE: IW3354000001",
    )

    parsed = parse_receipt_pdf(rav, "pagamento.pdf")
    assert documenti.detect_document_type("pagamento.pdf", rav) == "ricevuta_rav"
    assert parsed["document_kind"] == "RICEVUTA_RAV"
    assert parsed["operation_amount_cents"] == 4692
    assert parsed["fee_amount_cents"] == 285
    assert parsed["bank_debit_total_cents"] == 4977


def test_upload_auto_cbill_e_idempotente_e_non_inventa_la_banca(monkeypatch):
    db = MemorySheetsClient()["upload-auto-cbill"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _cbill_pdf()

    with TestClient(app) as client:
        first = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("pagamento_bancario.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "ricevuta_cbill"),
        )
        second = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("pagamento_bancario.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "ricevuta_cbill"),
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["tipo_rilevato"] == "ricevuta_cbill"
    assert first.json()["workflow"] == "PAGOPA_CBILL_CANONICO"
    receipt = first.json()["data"]["receipt"]
    assert receipt["operation_amount"] == 126.68
    assert receipt["fee_amount"] == 2.85
    assert receipt["bank_debit_total"] == 129.53
    assert receipt["versato_documentalmente"] is True
    assert receipt["banca_verificata"] is False
    assert receipt["movimento_id"] is None
    assert second.json()["duplicate"] is True
    assert asyncio.run(db["ricevute_pagopa"].count_documents({})) == 1


def test_upload_auto_bollettino_postale_usa_codice_forte_e_importo_operazione(monkeypatch):
    db = MemorySheetsClient()["upload-auto-postal"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _pdf(
        "UTENZE E SERVIZI: ADDEBITO", "BOLLETTINO POSTALE", "01/03/2023",
        "C/C POSTALE N. 123456789", "IMPORTO OPERAZIONE", "917,10",
        "COMMISSIONI", "2,85", "TOTALE ADDEBITO", "919,95",
        "COD.RIF ABC123456789", "ID. POSTE 06209227663", "N.op PVV427665443",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("addebito_bpm.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "ricevuta_bollettino_postale"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "PAGAMENTO_DOCUMENTALE_CANONICO"
    receipt = payload["data"]["receipt"]
    assert receipt["operation_amount"] == 917.10
    assert receipt["fee_amount"] == 2.85
    assert receipt["bank_debit_total"] == 919.95
    assert receipt["identificativo_bolletta"] == "ABC123456789"
    assert receipt["movimento_id"] is None


@pytest.mark.parametrize("document_kind", [
    "RICEVUTA_CBILL", "RICEVUTA_MAV", "RICEVUTA_RAV", "RICEVUTA_BOLLETTINO_POSTALE",
])
def test_riconciliazione_pagopa_non_perde_il_sottotipo(document_kind, monkeypatch):
    from app.routers import pagopa
    from app.services import fiscal_payment_reconciliation

    captured = {}

    async def fake_reconcile(_db, **kwargs):
        captured.update(kwargs)
        return {"matched": False}

    monkeypatch.setattr(fiscal_payment_reconciliation, "reconcile_fiscal_payment", fake_reconcile)
    asyncio.run(pagopa.riconcilia_ricevuta_fiscale(
        object(), {"id": "receipt-1", "document_kind": document_kind, "importo": 57.09},
    ))

    assert captured["source_type"] == document_kind
