import asyncio
import io
import zipfile

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti
from tests.document_preview_helpers import confirmed_preview_headers
from app.services.administrative_document_parser import (
    parse_ader, parse_dimissioni, parse_tari,
)


def _pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 40
    for line in text.splitlines():
        page.insert_text((35, y), line, fontsize=9)
        y += 18
    content = doc.tobytes()
    doc.close()
    return content


def test_parser_dimissioni_usa_cf_lavoratore_e_non_muta_lo_stato():
    parsed = parse_dimissioni(
        "Sezione 1 - Lavoratore Codice Fiscale RSSMRA80A01F839X Cognome ROSSI Nome MARIO "
        "E-Mail mario@example.it Sezione 2 - Datore di Lavoro Codice Fiscale 04523831214 "
        "Sezione 3 - Rapporto di Lavoro Data Inizio 01/02/2020 Tipo Contratto TEMPO INDETERMINATO "
        "Sezione 4 - Recesso dal rapporto di lavoro Data Decorrenza 31/07/2026 "
        "Tipo Comunicazione Dimissioni volontarie Sezione 5 - Dati Invio "
        "Codice Identificativo Modulo 20260730123456789 Data Trasmissione 30/07/2026"
    )
    assert parsed["lavoratore_cf"] == "RSSMRA80A01F839X"
    assert parsed["datore_cf"] == "04523831214"
    assert parsed["data_decorrenza_recesso"] == "2026-07-31"
    assert parsed["mutates_employee_status"] is False
    assert parsed["requires_review"] is False


def test_parser_ader_collega_numeri_cartella_ma_non_prova_pagamento():
    parsed = parse_ader(
        "SOSPENSIONE LEGALE DELLA RISCOSSIONE del/della CERALDI GROUP SRL "
        "codice fiscale 04523831214 Cartella di pagamento 07120220089305113000 "
        "Avviso di addebito 37120120004764848000 22/07/2022",
        "ader_sospensione",
    )
    assert parsed["contribuente_cf"] == "04523831214"
    assert parsed["numeri_cartella"] == ["07120220089305113000", "37120120004764848000"]
    assert parsed["is_payment_evidence"] is False


def test_parser_tari_preserva_contribuente_anno_e_fase():
    parsed = parse_tari(
        "AREA ENTRATE Prot. n 768681/353483 Cod. Contribuente: 1917342 "
        "P.IVA/C.F. 04523831214 AVVISO DI PAGAMENTO TARI - SALDO 2022 "
        "Scadenza 16/12/2022 totale euro 1.234,56"
    )
    assert parsed["contribuente_cf"] == "04523831214"
    assert parsed["anno_tributo"] == 2022
    assert parsed["fase"] == "SALDO"
    assert parsed["is_payment_evidence"] is False


def test_upload_dimissioni_archivia_e_propone_dipendente_senza_modificarlo(monkeypatch):
    db = AsyncMongoMockClient()["upload-dimissioni"]
    asyncio.run(db["dipendenti"].insert_one({
        "id": "dip-1", "codice_fiscale": "RSSMRA80A01F839X",
        "nome": "Mario", "cognome": "Rossi", "stato": "attivo",
    }))
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _pdf(
        "Sezione 1 - Lavoratore\nCodice Fiscale RSSMRA80A01F839X Cognome ROSSI Nome MARIO E-Mail x@y.it\n"
        "Sezione 2 - Datore di Lavoro\nCodice Fiscale 04523831214\n"
        "Sezione 3 - Rapporto di Lavoro Data Inizio 01/02/2020\n"
        "Sezione 4 - Recesso dal rapporto di lavoro Data Decorrenza 31/07/2026\n"
        "Tipo Comunicazione Dimissioni volontarie\nSezione 5 - Dati Invio\n"
        "Codice Identificativo Modulo 20260730123456789 Data Trasmissione 30/07/2026\n"
        "Modulo Recesso Rapporto di Lavoro"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("dimissione.pdf", content, "application/pdf")},
            headers=confirmed_preview_headers(content, "dimissioni_telematiche"),
        )

    payload = response.json()
    assert payload["tipo_rilevato"] == "dimissioni_telematiche"
    assert payload["payment_evidence"] is False
    assert payload["association_candidates"][0]["id"] == "dip-1"
    employee = asyncio.run(db["dipendenti"].find_one({"id": "dip-1"}))
    assert employee["stato"] == "attivo"


def test_upload_zip_preserva_percorso_e_gruppo_per_associare_allegati(monkeypatch):
    db = AsyncMongoMockClient()["upload-zip-provenienza"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    tari = _pdf(
        "AREA ENTRATE Prot. n 1/2 Cod. Contribuente: 1917342\n"
        "P.IVA/C.F. 04523831214\nAVVISO DI PAGAMENTO TARI - SALDO 2026"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("raccolta/email-2026-01/allegato-tari.pdf", tari)

    with TestClient(app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("raccolta.zip", archive.getvalue(), "application/zip")},
            headers=confirmed_preview_headers(archive.getvalue(), "archivio_zip"),
        )

    assert response.status_code == 200
    assert response.json()["details"][0]["archive_path"] == "raccolta/email-2026-01/allegato-tari.pdf"
    saved = asyncio.run(db["documents_inbox"].find_one({"document_type": "tari_avviso"}))
    assert saved["source_context"]["archive_group"] == "raccolta/email-2026-01"
    assert saved["source_context"]["archive_filename"] == "raccolta.zip"
