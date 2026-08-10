import asyncio
import hashlib
import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient
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
        db = AsyncMongoMockClient()["documenti_import_sicuro"]
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
