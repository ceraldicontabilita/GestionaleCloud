import asyncio

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

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
    db = AsyncMongoMockClient()["upload-auto-cbill"]
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
