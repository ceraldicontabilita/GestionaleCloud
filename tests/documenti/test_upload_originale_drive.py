"""Import da Drive: originale riusato, contenitore ZIP mai aperto come PDF."""
import asyncio
import hashlib
import io
from unittest.mock import AsyncMock, Mock

import fitz
import pytest
from fastapi import UploadFile

from app.routers import documenti
from app.services import bonifici_pdf_ingest, pdf_drive_only
from app.services.archivio_documenti_memoria import ClientArchivioMemoria, CollezioneDocumenti


@pytest.fixture
def ingresso(monkeypatch):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Documento di collaudo")
        content = pdf.tobytes()
    db = ClientArchivioMemoria()["originali_isolati"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    context = {"channel": "drive_cartella_unica", "drive_file_id": "originale-drive",
               "source_sha256": hashlib.sha256(content).hexdigest(),
               "drive_path": "DA ELABORARE/bonifico.pdf"}

    def upload(kind, source=None):
        file = UploadFile(filename="documento.pdf", file=io.BytesIO(content))
        file.tipo_rilevato_noto = kind
        file.source_context = context if source is None else source
        return file

    return db, content, context, upload


@pytest.mark.parametrize("kind,module,function", [
    ("f24", "app.services.f24_canonico", "importa_modello_bytes"),
    ("quietanza_f24", "app.services.f24_canonico", "importa_quietanza"),
    ("dichiarazione_fiscale", "app.services.fiscal_document_ingestion.FiscalDocumentIngestionService", "ingest"),
])
def test_routing_fiscale_conserva_originale(ingresso, monkeypatch, kind, module, function):
    db, content, context, upload = ingresso
    ingest = AsyncMock(return_value={"success": True, "status": "saved"})
    monkeypatch.setattr(f"{module}.{function}", ingest)
    result = asyncio.run(documenti.upload_documento_automatico(file=upload(kind)))
    assert result["success"] is True
    metadata = ingest.call_args.kwargs["source_metadata"]
    assert metadata["drive_file_id"] == "originale-drive"
    assert metadata["drive_md5"] == hashlib.md5(content).hexdigest()


def test_bonifico_salvato_e_duplicato_riusano_originale(ingresso, monkeypatch):
    db, content, context, upload = ingresso
    # Stessa frontiera della persistenza reale, senza alcuna connessione cloud.
    insert = CollezioneDocumenti.insert_one

    async def insert_with_drive(self, record, *args, **kwargs):
        await pdf_drive_only.externalize_documents(self.name, [record])
        return await insert(self, record, *args, **kwargs)

    monkeypatch.setattr(CollezioneDocumenti, "insert_one", insert_with_drive)
    monkeypatch.setattr("app.services.email_drive_archive.archive_binary_copy",
                        lambda *a, **kw: pytest.fail("Tentativo di ricopiare il PDF su Drive"))
    reader = Mock(return_value=(
        "Banco BPM\nRicevuta di bonifico\nData esecuzione: 15/09/2026\n"
        "Beneficiario: ROSSI MARIO\nImporto: EUR 122,00\n"
        "Causale: stipendio agosto 2026\nCRO: 05034123456789012345\n"
    ))
    monkeypatch.setattr(bonifici_pdf_ingest, "read_pdf_bytes", reader)
    monkeypatch.setattr(bonifici_pdf_ingest, "associa_transfer_documento",
                        AsyncMock(return_value={"associato": False}))
    monkeypatch.setattr("app.services.hr_pagamenti_deposito.deposita_bonifico_transfer_in_hr",
                        AsyncMock(return_value={"esito": "da_verificare"}))

    async def scenario():
        first = await documenti.upload_documento_automatico(file=upload("bonifici"))
        assert first["success"] is True, first
        second = await documenti.upload_documento_automatico(file=upload("bonifici"))
        assert second["duplicate"] is True, second
        assert reader.call_count == 2, "Il lettore PDF deve girare una volta per caricamento"
        assert await db.bonifici_transfers.count_documents({}) == 1
        assert await db.documents_inbox.count_documents({}) == 1
        for collection in ("bonifici_transfers", "documents_inbox"):
            record = await db[collection].find_one({})
            assert "pdf_data" not in record
            assert record["_drive_payloads"]["pdf_data"]["drive_file_id"] == "originale-drive"
        transfer = await db.bonifici_transfers.find_one({})
        assert transfer["source_path"] == context["drive_path"]
        assert transfer["importo"] == 122
        assert (transfer["periodo_mese"], transfer["periodo_anno"]) == (8, 2026)

    asyncio.run(scenario())


def test_cedolino_dentro_zip_non_riceve_id_del_contenitore(ingresso, monkeypatch):
    db, content, context, upload = ingresso
    parser = AsyncMock(return_value={"esito": "presenze", "motivo": "foglio presenze"})
    monkeypatch.setattr("app.services.cedolini_manager.processa_tutti_cedolini_pdf", parser)
    result = asyncio.run(documenti.upload_documento_automatico(file=upload(
        "cedolino", {**context, "drive_file_id": "zip", "archive_member": "busta.pdf"})))
    assert result["success"] is True
    assert parser.call_args.kwargs["drive_file_id"] == ""


def test_pdf_inbox_non_letto_resta_in_errore(ingresso):
    db, content, context, upload = ingresso

    async def scenario():
        await db.documents_inbox.insert_one({"id": "senza-pdf", "category": "bonifico",
                                            "processed": False})
        result = await bonifici_pdf_ingest.processa_inbox_bonifici(db)
        assert result["errori"] == 1
        record = await db.documents_inbox.find_one({"id": "senza-pdf"})
        assert record["processed"] is False
        assert record["status"] == "errore_processing"
        assert await db.bonifici_transfers.count_documents({}) == 0

    asyncio.run(scenario())
