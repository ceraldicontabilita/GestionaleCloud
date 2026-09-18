import asyncio
import hashlib
import io
import zipfile
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException, UploadFile
from app.services.sheets_document_store import MemorySheetsClient
from openpyxl import Workbook

from app.routers import documenti


def test_pdf_agenzia_entrate_non_diventa_f24_senza_codici_tributo(monkeypatch):
    monkeypatch.setattr(
        documenti,
        "_pdf_text_for_detection",
        lambda *_: "AGENZIA DELLE ENTRATE COMUNICAZIONE DI IRREGOLARITA",
    )
    assert documenti.detect_document_type("avviso.pdf", b"%PDF-1.4") == "auto"


def test_pdf_f24_richiede_una_prova_specifica(monkeypatch):
    monkeypatch.setattr(
        documenti,
        "_pdf_text_for_detection",
        lambda *_: "MODELLO DI PAGAMENTO UNIFICATO F24 SEZIONE ERARIO CODICE TRIBUTO",
    )
    assert documenti.detect_document_type("documento.pdf", b"%PDF-1.4") == "f24"


def test_csv_generico_non_viene_importato_come_estratto_conto():
    generic = b"prodotto,quantita,prezzo\ncaffe,2,10.00\n"
    bank = b"data,causale,descrizione,importo\n2026-01-02,bonifico,test,12.00\n"
    assert documenti.detect_document_type("magazzino.csv", generic) == "auto"
    assert documenti.detect_document_type("operazioni.csv", bank) == "estratto_conto"


def test_xlsx_distinta_stipendi_legge_le_intestazioni_reali():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Beneficiario", "IBAN", "Importo"])
    sheet.append(["Dipendente Test", "IT00TEST", 1000])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert (
        documenti.detect_document_type("distinta_stipendi.xlsx", buffer.getvalue())
        == "distinte_bpm"
    )


def test_xml_generico_non_viene_spacciato_per_fattura():
    assert documenti.detect_document_type("dati.xml", b"<DocumentoGenerico />") == "auto"
    assert (
        documenti.detect_document_type(
            "dati.xml", b"<FatturaElettronica><FatturaElettronicaHeader />"
        )
        == "fattura"
    )


def test_p7m_viene_classificato_solo_dopo_estrazione_xml(monkeypatch):
    import app.services.xml_invoice_processor as processor

    monkeypatch.setattr(
        processor,
        "extract_xml_from_p7m",
        lambda _content: b"<FatturaElettronica><FatturaElettronicaHeader /></FatturaElettronica>",
    )
    assert documenti.detect_document_type("fattura.xml.p7m", b"busta-cades") == "fattura"

    monkeypatch.setattr(processor, "extract_xml_from_p7m", lambda _content: None)
    assert documenti.detect_document_type("firma.p7m", b"non-valido") == "auto"


def test_upload_generico_duplicato_non_crea_una_seconda_copia(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["documenti_import_sicuro"]
        payload = b"documento generico"
        file_hash = hashlib.md5(payload).hexdigest()
        await db.documents_inbox.insert_one({
            "id": "doc-esistente",
            "filename": "originale.bin",
            "file_hash": file_hash,
        })
        monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
        upload = UploadFile(filename="copia.bin", file=io.BytesIO(payload))

        result = await documenti.upload_documento_automatico(file=upload)

        assert result["action"] == "duplicate"
        assert result["imported"] == 0
        assert await db.documents_inbox.count_documents({}) == 1

    asyncio.run(scenario())


def test_zip_sospetto_viene_bloccato_prima_della_decompressione():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("enorme.csv", "A" * 2_000_000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(documenti._process_zip_upload("documenti.zip", buffer.getvalue()))

    assert exc.value.status_code == 400
    assert "Compressione ZIP sospetta" in exc.value.detail


def test_zip_valido_riusa_il_flusso_canonico_per_ogni_file(monkeypatch):
    calls = []

    async def fake_upload(*, file, preview_token=None):
        calls.append((file.filename, await file.read()))
        return {
            "success": True,
            "tipo_rilevato": "fattura",
            "imported": 1,
            "message": "Importato",
        }

    monkeypatch.setattr(documenti, "upload_documento_automatico", fake_upload)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cartella/fattura.xml", "<FatturaElettronica />")
        archive.writestr("note.txt", "non supportato")

    result = asyncio.run(documenti._process_zip_upload("documenti.zip", buffer.getvalue()))

    assert calls == [("fattura.xml", b"<FatturaElettronica />")]
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert result["partial"] is True


def test_categoria_fiscale_zip_accetta_solo_documento_completo():
    root = "ARCHIVIO/01_DICHIARAZIONI_FISCALI"
    assert documenti._fiscal_category_from_archive_path(
        f"{root}/LIPE/2026/LIPE_2026_407141844.pdf"
    ) == "lipe"
    assert documenti._fiscal_category_from_archive_path(
        f"{root}/770/2025/770_2025_imposta_2024.pdf"
    ) == "modello_770"
    assert documenti._fiscal_category_from_archive_path(
        f"{root}/770/2025/componenti_originali/protocollo/01_Frontespizio.pdf"
    ) is None
    assert documenti._fiscal_category_from_archive_path(
        f"{root}/Percipienti/2025/Percipienti_2025.csv"
    ) is None


def test_zip_invia_lipe_al_registro_fiscale(monkeypatch):
    calls = []
    db = MemorySheetsClient()["documenti_import_fiscale_zip"]

    class FakeFiscalIngestion:
        def __init__(self, received_db):
            assert received_db is db

        async def ingest(self, **kwargs):
            calls.append(kwargs)
            return {"status": "inserted", "document_id": "doc-lipe"}

    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    import app.services.fiscal_document_ingestion as fiscal_ingestion
    import app.services.drive_declaration_upload as drive_upload
    monkeypatch.setattr(fiscal_ingestion, "FiscalDocumentIngestionService", FakeFiscalIngestion)
    monkeypatch.setattr(drive_upload, "upload_declaration", lambda **_kwargs: {
        "success": True,
        "duplicate": True,
        "document_id": "DRIVE-LIPE",
        "drive_path": "01_DICHIARAZIONI_FISCALI/LIPE/2026/LIPE_2026.pdf",
    })

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "ARCHIVIO/01_DICHIARAZIONI_FISCALI/LIPE/2026/LIPE_2026.pdf",
            b"%PDF-1.4 documento lipe",
        )

    result = asyncio.run(documenti._process_zip_upload("fiscale.zip", buffer.getvalue()))

    assert result["imported"] == 1
    assert calls[0]["category_hint"] == "lipe"
    assert calls[0]["source_metadata"]["archive_path"].endswith("LIPE_2026.pdf")
    assert calls[0]["source_metadata"]["drive_document_id"] == "DRIVE-LIPE"


def test_upload_zip_usa_batch_writes_del_runtime(monkeypatch):
    state = {"active": False, "processed": False}

    class RuntimeDb:
        @asynccontextmanager
        async def batch_writes(self):
            state["active"] = True
            try:
                yield
            finally:
                state["active"] = False

    async def fake_process(filename, content):
        assert filename == "archivio.zip"
        assert content.startswith(b"PK")
        assert state["active"] is True
        state["processed"] = True
        return {"success": True, "imported": 1}

    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: RuntimeDb()))
    monkeypatch.setattr(documenti, "_process_zip_upload", fake_process)
    payload = b"PK\x03\x04archivio"
    upload = UploadFile(filename="archivio.zip", file=io.BytesIO(payload))

    result = asyncio.run(documenti.upload_documento_automatico(file=upload))

    assert result["success"] is True
    assert state == {"active": False, "processed": True}
