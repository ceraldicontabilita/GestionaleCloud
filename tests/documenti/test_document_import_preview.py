import hashlib

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.database import Database
from app.routers import documenti


def _pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_preview_non_scrive_e_token_autorizza_solo_file_confermato(monkeypatch):
    db = ClientArchivioMemoria()["document-preview-test"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(documenti.router, prefix="/api/documenti")
    content = _pdf("DOCUMENTO GENERICO DA CLASSIFICARE")
    changed = _pdf("DOCUMENTO DIVERSO")

    with TestClient(app) as client:
        preview = client.post(
            "/api/documenti/upload-auto/preview",
            files={"file": ("generico.pdf", content, "application/pdf")},
        )
        without_token = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("generico.pdf", content, "application/pdf")},
        )
        wrong_file = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("generico.pdf", changed, "application/pdf")},
            headers={"X-Document-Preview-Token": preview.json()["confirmation_token"]},
        )

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["preview_only"] is True
    assert payload["file"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert payload["file"]["page_count"] == 1
    assert payload["confirmation_required"] is True
    assert without_token.status_code == 428
    assert wrong_file.status_code == 428

    import asyncio

    for collection in ("documents_inbox", "f24_unificato", "quietanze_f24", "ricevute_pagopa"):
        assert asyncio.run(db[collection].count_documents({})) == 0

    with TestClient(app) as client:
        confirmed = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("generico.pdf", content, "application/pdf")},
            headers={"X-Document-Preview-Token": payload["confirmation_token"]},
        )

    assert confirmed.status_code == 200
    assert asyncio.run(db["documents_inbox"].count_documents({})) == 1


def test_anteprima_f24_usa_i_lettori_esistenti_e_non_cade_su_un_f24_rotto(monkeypatch):
    """L'anteprima F24 importava una costante inesistente (PARSER_KIND_MODELLO):
    ogni F24 e quietanza mandava in errore Documenti > Import e la simulazione.
    Un F24 illeggibile o non quadrato e' un errore bloccante, non un'eccezione."""
    from app.services import document_import_preview as dip
    from app.services import f24_fiscal_evidence as ev

    visti = []

    def rotto(content, *, document_kind):
        visti.append(document_kind)
        raise ValueError("F24 non quadrato: importazione fiscale sospesa")

    monkeypatch.setattr(ev, "parse_f24_evidence", rotto)
    for tipo in ("f24", "quietanza_f24"):
        assert dip._f24_preview(b"%PDF", tipo) == {
            "error": "F24 non quadrato: importazione fiscale sospesa"}
    assert visti == [ev.PARSER_KIND_PRINTABLE, ev.PARSER_KIND_QUIETANZA]


def test_nome_cedolino_vale_solo_per_i_pdf():
    """«Indice_Cedolini_Gestionale.xlsx» e' un indice, non una busta paga."""
    from app.routers.documenti import detect_document_type

    assert detect_document_type("Indice_Cedolini_Gestionale.xlsx", b"PK\x03\x04") != "cedolino"
