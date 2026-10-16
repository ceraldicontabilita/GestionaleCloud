import asyncio
import hashlib

import fitz

from app.services import fiscal_document_ingestion as ingestion
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _blank_pdf() -> bytes:
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return content


def test_occorrenza_documento_fiscale_conserva_la_provenienza_email():
    occurrence = ingestion._source_occurrence("posta", {
        "email_account": "archivio@example.it",
        "email_from": "mittente@example.it",
        "email_to": "destinatario@example.it",
        "email_subject": "Piano rateale",
        "email_date": "2026-10-01",
        "email_message_id": "<messaggio@example.it>",
    }, "a" * 64)

    assert occurrence["email_account"] == "archivio@example.it"
    assert occurrence["email_from"] == "mittente@example.it"
    assert occurrence["email_to"] == "destinatario@example.it"
    assert occurrence["email_subject"] == "Piano rateale"
    assert occurrence["email_message_id"] == "<messaggio@example.it>"


def _raster_pdf() -> bytes:
    import io
    from PIL import Image

    image = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(image, format="PNG")
    with fitz.open() as document:
        page = document.new_page()
        page.insert_image(page.rect, stream=image.getvalue())
        return document.tobytes()


def test_pagina_fiscale_raster_usa_ocr_locale_con_confidenza(monkeypatch):
    import contextlib

    monkeypatch.setattr(ingestion, "motore", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(
        ingestion, "_ocr_page",
        lambda _page, _engine: (
            "VP1 Mese 7\nVP4 100,00\nVP5 20,00\nVP14 80,00", 0.93,
            [{"x0": 10, "y0": 10, "x1": 20, "y1": 20, "text": "VP1"}],
        ),
    )

    pages = ingestion.extract_pdf_pages(_raster_pdf())

    assert pages == [{
        "page_number": 1,
        "text": "VP1 Mese 7\nVP4 100,00\nVP5 20,00\nVP14 80,00",
        "text_source": "rapidocr_locale",
        "ocr_used": True,
        "ocr_confidence": 0.93,
        "layout_words": [{"x0": 10, "y0": 10, "x1": 20, "y1": 20, "text": "VP1"}],
        "requires_ocr": False,
    }]


def test_retro_vuoto_e_numero_pagina_non_avviano_ocr(monkeypatch):
    def non_avviare():
        raise AssertionError("OCR non necessario su pagine digitali vuote")

    monkeypatch.setattr(ingestion, "motore", non_avviare)
    with fitz.open() as document:
        document.new_page()
        page = document.new_page()
        page.insert_text((50, 50), "10")
        pages = ingestion.extract_pdf_pages(document.tobytes())
    assert len(pages) == 2
    assert pages[1]["text"].strip() == "10"
    assert all(p["ocr_not_required"] and not p["requires_ocr"] for p in pages)


def test_reimport_non_rilegge_retro_vuoto_gia_verificato(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria().db
        content = _blank_pdf()
        digest = hashlib.sha256(content).hexdigest()
        await db.fiscal_document_versions.insert_one({
            "id": "V-BLANK", "document_id": "D-BLANK",
            "company_id": "CERALDI", "sha256": digest,
        })
        await db.fiscal_pages.insert_one({
            "id": "P-BLANK", "version_id": "V-BLANK", "document_id": "D-BLANK",
            "company_id": "CERALDI", **ingestion.extract_pdf_pages(content)[0],
        })

        def non_rileggere(_content):
            raise AssertionError("Il retro bianco non deve causare una nuova lettura")

        monkeypatch.setattr(ingestion, "extract_pdf_pages", non_rileggere)
        result = await FiscalDocumentIngestionService(db, "CERALDI").ingest(
            content=content, filename="cartella.pdf", source="documenti",
        )
        assert result["status"] == "duplicate"
        assert result["derived_text_refreshed"] is False

    asyncio.run(scenario())


def test_pdf_chiuso_anche_se_ocr_rinviato(monkeypatch):
    import pytest

    document = fitz.open(stream=_raster_pdf(), filetype="pdf")
    monkeypatch.setattr(ingestion.fitz, "open", lambda **_kwargs: document)

    def senza_memoria():
        raise ingestion.MemoriaInsufficiente(1400, 2048)

    monkeypatch.setattr(ingestion, "motore", senza_memoria)
    with pytest.raises(ingestion.MemoriaInsufficiente):
        ingestion.extract_pdf_pages(b"non viene riaperto")
    assert document.is_closed


def test_duplicato_legacy_rigenera_solo_il_testo_derivato(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria().db
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
        db = ClientArchivioMemoria().db
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
        assert inbox["source_occurrences"] == [{
            "source": "documenti_upload_auto_zip",
            "drive_file_id": "FILE-DRIVE-LIPE",
            "drive_document_id": "DOC-DRIVE-LIPE",
            "source_path": "01_DICHIARAZIONI_FISCALI/LIPE/2026/LIPE_2026.pdf",
            "sha256": result["sha256"],
        }]
        assert "pdf_data" not in inbox

    asyncio.run(scenario())


def test_duplicato_parziale_riceve_il_riferimento_drive(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria().db
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
        assert inbox["source_occurrences"][0]["drive_document_id"] == "DRIVE-PARTIAL"
        assert "pdf_data" not in inbox

    asyncio.run(scenario())
