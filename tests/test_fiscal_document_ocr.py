import asyncio
import hashlib

import fitz

from app.services import fiscal_document_ingestion as ingestion
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
from app.services.sheets_document_store import MemorySheetsClient


def _blank_pdf() -> bytes:
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return content


def test_pagina_fiscale_raster_usa_ocr_locale_con_confidenza(monkeypatch):
    monkeypatch.setattr(
        ingestion, "_ocr_page",
        lambda _page: (
            "VP1 Mese 7\nVP4 100,00\nVP5 20,00\nVP14 80,00", 0.93,
            [{"x0": 10, "y0": 10, "x1": 20, "y1": 20, "text": "VP1"}],
        ),
    )

    pages = ingestion.extract_pdf_pages(_blank_pdf())

    assert pages == [{
        "page_number": 1,
        "text": "VP1 Mese 7\nVP4 100,00\nVP5 20,00\nVP14 80,00",
        "text_source": "rapidocr_locale",
        "ocr_used": True,
        "ocr_confidence": 0.93,
        "layout_words": [{"x0": 10, "y0": 10, "x1": 20, "y1": 20, "text": "VP1"}],
        "requires_ocr": False,
    }]


def test_duplicato_legacy_rigenera_solo_il_testo_derivato(monkeypatch):
    async def scenario():
        db = MemorySheetsClient().db
        content = b"%PDF-LIPE-LEGACY"
        digest = hashlib.sha256(content).hexdigest()
        await db.fiscal_document_versions.insert_one({
            "id": "VERSION-1", "document_id": "DOC-1",
            "company_id": "CERALDI", "sha256": digest,
        })
        await db.fiscal_pages.insert_one({
            "id": "PAGE-1", "document_id": "DOC-1", "version_id": "VERSION-1",
            "company_id": "CERALDI", "page_number": 1, "text": "",
            "requires_ocr": True,
        })
        monkeypatch.setattr(ingestion, "extract_pdf_pages", lambda _content: [{
            "page_number": 1, "text": "VP1 Mese 7\nVP4 100,00\nVP5 20,00",
            "text_source": "rapidocr_locale", "ocr_used": True,
            "ocr_confidence": 0.91, "requires_ocr": False,
        }])

        result = await FiscalDocumentIngestionService(db, "CERALDI").ingest(
            content=content, filename="LIPE_2026.pdf", source="documenti",
        )
        page = await db.fiscal_pages.find_one({"version_id": "VERSION-1"})

        assert result["status"] == "duplicate"
        assert result["derived_text_refreshed"] is True
        assert page["ocr_used"] is True
        assert page["text_source"] == "rapidocr_locale"
        assert page["text"].startswith("VP1 Mese 7")

    asyncio.run(scenario())


def test_documento_fiscale_drive_non_duplica_il_pdf_nel_foglio():
    async def scenario():
        db = MemorySheetsClient().db
        content = _blank_pdf()
        result = await FiscalDocumentIngestionService(db, "CERALDI").ingest(
            content=content,
            filename="LIPE_2026.pdf",
            source="documenti_upload_auto_zip",
            category_hint="lipe",
            source_metadata={
                "drive_document_id": "DOC-DRIVE-LIPE",
                "drive_file_id": "FILE-DRIVE-LIPE",
                "drive_path": "01_DICHIARAZIONI_FISCALI/LIPE/2026/LIPE_2026.pdf",
            },
        )
        inbox = await db.documents_inbox.find_one({"sha256": result["sha256"]})

        assert inbox["drive_document_id"] == "DOC-DRIVE-LIPE"
        assert inbox["drive_file_id"] == "FILE-DRIVE-LIPE"
        assert "pdf_data" not in inbox

    asyncio.run(scenario())


def test_duplicato_parziale_riceve_il_riferimento_drive(monkeypatch):
    async def scenario():
        db = MemorySheetsClient().db
        content = b"%PDF-LIPE-PARTIAL"
        digest = hashlib.sha256(content).hexdigest()
        await db.fiscal_document_versions.insert_one({
            "id": "VERSION-PARTIAL", "document_id": "DOC-PARTIAL",
            "company_id": "CERALDI", "sha256": digest,
        })
        await db.documents_inbox.insert_one({
            "id": "INBOX-PARTIAL", "company_id": "CERALDI", "sha256": digest,
            "pdf_data": "payload-temporaneo-non-persistibile",
        })
        monkeypatch.setattr(ingestion, "extract_pdf_pages", lambda _content: [{
            "page_number": 1, "text": "VP1 VP4 VP14", "text_source": "pdf_text",
            "ocr_used": False, "ocr_confidence": None, "layout_words": [],
            "requires_ocr": False,
        }])

        result = await FiscalDocumentIngestionService(db, "CERALDI").ingest(
            content=content,
            filename="LIPE_2026.pdf",
            source="documenti_upload_auto_zip",
            category_hint="lipe",
            source_metadata={"drive_document_id": "DRIVE-PARTIAL"},
        )
        inbox = await db.documents_inbox.find_one({"sha256": digest})

        assert result["status"] == "duplicate"
        assert inbox["fiscal_document_id"] == "DOC-PARTIAL"
        assert inbox["drive_document_id"] == "DRIVE-PARTIAL"
        assert "pdf_data" not in inbox

    asyncio.run(scenario())
