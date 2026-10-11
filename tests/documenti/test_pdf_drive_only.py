import asyncio
import base64
import hashlib

import pytest

from app.services import email_drive_archive, pdf_drive_only


PDF = b"%PDF-1.4\noriginale\n%%EOF"


def test_externalizza_pdf_e_conserva_solo_il_riferimento(monkeypatch):
    def archive(content, filename, **kwargs):
        assert content == PDF
        assert filename.endswith(".pdf")
        return {
            "status": "archived",
            "drive_file_id": "drive-1",
            "md5": hashlib.md5(PDF, usedforsecurity=False).hexdigest(),
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "bytes": len(PDF),
        }

    monkeypatch.setattr(email_drive_archive, "archive_binary_copy", archive)
    doc = {"_id": "doc-1", "pdf_data": base64.b64encode(PDF).decode()}

    asyncio.run(pdf_drive_only.externalize_documents("documents_inbox", [doc]))

    assert "pdf_data" not in doc
    assert doc["drive_file_id"] == "drive-1"
    assert doc["_payload_stato"]["pdf_data"] == "pieno"
    assert doc["_drive_payloads"]["pdf_data"]["bytes"] == len(PDF)


def test_non_pdf_nel_vecchio_campo_non_viene_toccato(monkeypatch):
    monkeypatch.setattr(
        email_drive_archive,
        "archive_binary_copy",
        lambda *_args, **_kwargs: pytest.fail("non deve archiviare un non-PDF"),
    )
    encoded = base64.b64encode(b"PK\x03\x04archivio").decode()
    doc = {"_id": "zip-1", "pdf_data": encoded}

    asyncio.run(pdf_drive_only.externalize_documents("documents_inbox", [doc]))

    assert doc["pdf_data"] == encoded


def test_upload_non_verificato_blocca_la_scrittura(monkeypatch):
    monkeypatch.setattr(
        email_drive_archive,
        "archive_binary_copy",
        lambda *_args, **_kwargs: {"status": "error", "reason": "quota"},
    )
    doc = {"_id": "doc-1", "pdf_data": base64.b64encode(PDF).decode()}

    with pytest.raises(RuntimeError, match="quota"):
        asyncio.run(pdf_drive_only.externalize_documents("documents_inbox", [doc]))
    assert "pdf_data" in doc


def test_idrata_pdf_da_drive_solo_in_memoria(monkeypatch):
    async def scarica(file_id, md5=None):
        assert file_id == "drive-1"
        assert md5 == hashlib.md5(PDF, usedforsecurity=False).hexdigest()
        return PDF

    monkeypatch.setattr("app.services.drive_download.scarica_originale", scarica)
    doc = {
        "_id": "doc-1",
        "_drive_payloads": {"pdf_data": {
            "drive_file_id": "drive-1",
            "md5": hashlib.md5(PDF, usedforsecurity=False).hexdigest(),
        }},
    }

    asyncio.run(pdf_drive_only.hydrate_document("documents_inbox", doc))

    assert base64.b64decode(doc["pdf_data"]) == PDF


def test_originale_drive_riusato_senza_copia_e_riaperto(monkeypatch):
    monkeypatch.setattr(email_drive_archive, "archive_binary_copy",
                        lambda *a, **kw: pytest.fail("L'originale e' gia' su Drive"))
    doc = {"pdf_data": base64.b64encode(PDF).decode(), "source_context": {
        "drive_file_id": "originale", "source_sha256": hashlib.sha256(PDF).hexdigest(),
    }}

    async def download(file_id, md5=None):
        assert file_id == "originale"
        assert md5 == hashlib.md5(PDF).hexdigest()
        return PDF

    monkeypatch.setattr("app.services.drive_download.scarica_originale", download)

    async def scenario():
        await pdf_drive_only.externalize_documents("documents_inbox", [doc])
        assert "pdf_data" not in doc
        await pdf_drive_only.hydrate_document("documents_inbox", doc)
        assert base64.b64decode(doc["pdf_data"]) == PDF

    asyncio.run(scenario())


@pytest.mark.parametrize("context", [
    {"drive_file_id": "zip", "archive_member": "busta.pdf"},
    {"drive_file_id": "id-senza-impronta"},
])
def test_contenitore_o_riferimento_non_provato_non_diventa_pdf(monkeypatch, context):
    def archive(content, filename, **kwargs):
        assert content == PDF
        return {"status": "archived", "drive_file_id": "pdf-singolo"}

    monkeypatch.setattr(email_drive_archive, "archive_binary_copy", archive)
    doc = {"pdf_data": base64.b64encode(PDF).decode(), "source_context": context}
    asyncio.run(pdf_drive_only.externalize_documents("documents_inbox", [doc]))
    assert doc["drive_file_id"] == "pdf-singolo"


def test_impronta_drive_diversa_non_elimina_il_pdf(monkeypatch):
    monkeypatch.setattr(email_drive_archive, "archive_binary_copy",
                        lambda *a, **kw: pytest.fail("Impronta incoerente"))
    doc = {"pdf_data": base64.b64encode(PDF).decode(), "source_context": {
        "drive_file_id": "altro-file", "source_sha256": "0" * 64,
    }}
    with pytest.raises(ValueError, match="impronta"):
        asyncio.run(pdf_drive_only.externalize_documents("documents_inbox", [doc]))
    assert base64.b64decode(doc["pdf_data"]) == PDF
