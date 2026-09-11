import hashlib

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.sheets_document_store import MemorySheetsClient

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
    db = MemorySheetsClient()["document-preview-test"]
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



def test_preview_tipo_riconosciuto_non_diventa_verificato_solo_per_il_tipo(monkeypatch):
    import asyncio
    from app.services import document_import_preview as preview_service

    db = MemorySheetsClient()["document-preview-evidence-test"]
    monkeypatch.setattr(preview_service, "_specialist_preview", lambda *_: {})
    payload = asyncio.run(preview_service.build_import_preview(
        db, content=b"cedolino generico", filename="cedolino.pdf", document_type="cedolino"
    ))

    assert payload["evidence_status"] == "probabile"
    assert payload["classification"]["evidence_status"] == "probabile"
    assert payload["classification"]["confidence"] < 1.0


def test_preview_con_errore_di_validazione_e_conflitto():
    from app.services import document_import_preview as preview_service

    status, confidence, _ = preview_service._preview_evidence_state(
        "f24", {}, {"saldo_quadrato": False}, ["F24 non quadrato o non validato"]
    )
    assert status == "conflitto"
    assert confidence == 0.0
