"""15/09/2026 (richiesta del titolare): l'import di una dichiarazione fiscale
(770/IVA/IRAP/LIPE/Redditi SC) deve funzionare identico sia che il PDF arrivi
dalla cartella Drive "DICHIARAZIONI FISCALI" sia che venga caricato a mano da
Documenti > Import — stesso classificatore (fiscal_domain.classify_document),
stesso motore di archiviazione (FiscalDocumentIngestionService), un solo
sistema per funzione.
"""
import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.routers import documenti as documenti_mod


def test_detect_document_type_riconosce_lipe(monkeypatch):
    monkeypatch.setattr(
        documenti_mod,
        "_pdf_text_for_detection",
        lambda *_: "COMUNICAZIONE LIQUIDAZIONI PERIODICHE IVA I TRIMESTRE 2026",
    )
    assert documenti_mod.detect_document_type("LIPE_2026_407141844.pdf", b"%PDF-1.4") == "dichiarazione_fiscale"


def test_detect_document_type_riconosce_770(monkeypatch):
    monkeypatch.setattr(
        documenti_mod,
        "_pdf_text_for_detection",
        lambda *_: "MODELLO 770 SEMPLIFICATO ANNO 2025",
    )
    assert documenti_mod.detect_document_type("770_2025_imposta_2024.pdf", b"%PDF-1.4") == "dichiarazione_fiscale"


def test_detect_document_type_non_confonde_una_quietanza_f24_con_una_dichiarazione(monkeypatch):
    monkeypatch.setattr(
        documenti_mod,
        "_pdf_text_for_detection",
        lambda *_: "QUIETANZA RICEVUTA DI VERSAMENTO F24 PROTOCOLLO TELEMATICO",
    )
    assert documenti_mod.detect_document_type("f24.pdf", b"%PDF-1.4") != "dichiarazione_fiscale"


def test_upload_auto_dichiarazione_fiscale_usa_il_motore_canonico(monkeypatch):
    """Stesso servizio del canale Drive: FiscalDocumentIngestionService."""
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))

    chiamata = {}

    async def _fake_ingest(self, *, content, filename, source):
        chiamata["content"] = content
        chiamata["filename"] = filename
        chiamata["source"] = source
        return {"status": "inserted", "document_id": "doc-1", "version_id": "v-1"}

    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _fake_ingest)

    upload = UploadFile(filename="LIPE_2026.pdf", file=BytesIO(b"%PDF-1.4 contenuto finto"))

    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert chiamata["filename"] == "LIPE_2026.pdf"
    assert chiamata["source"] == "documenti_upload_auto"
    assert result["success"] is True
    assert result["duplicate"] is False
    assert result["imported"] == 1
    assert result["workflow"] == "FISCAL_DOCUMENT_INGESTION"


def test_upload_auto_dichiarazione_fiscale_duplicata_non_reimporta(monkeypatch):
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))

    async def _fake_ingest(self, *, content, filename, source):
        return {"status": "duplicate", "document_id": "doc-1", "version_id": "v-1"}

    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _fake_ingest)

    upload = UploadFile(filename="LIPE_2026.pdf", file=BytesIO(b"%PDF-1.4 contenuto finto"))

    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert result["duplicate"] is True
    assert result["imported"] == 0
