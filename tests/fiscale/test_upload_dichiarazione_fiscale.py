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


# ── Una LIPE archiviata deposita anche i suoi periodi IVA ──────────────────
# Fino al 26/09/2026 la LIPE caricata finiva solo in fiscal_documents, e
# `lipe_periodi` (l'unica fonte del confronto col commercialista) restava vuota.

def _ingest_finto(stato):
    async def _fake_ingest(self, *, content, filename, source):
        return {"status": stato, "document_id": "doc-1", "version_id": "v-1"}
    return _fake_ingest


def _deposito_registrato(monkeypatch):
    from app.services import lipe_deposito

    chiamate = []

    async def _fake_deposita(db, contenuto, *, nome_file, origine, drive_file_id=None, dry_run=False):
        chiamate.append({"nome_file": nome_file, "origine": origine,
                         "drive_file_id": drive_file_id, "dry_run": dry_run})
        return {"depositati": ["2026-01"], "scartati": []}

    monkeypatch.setattr(lipe_deposito, "deposita_lipe", _fake_deposita)
    return chiamate


def test_una_lipe_caricata_deposita_i_periodi(monkeypatch):
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _ingest_finto("inserted"))
    chiamate = _deposito_registrato(monkeypatch)

    upload = UploadFile(filename="LIPE_2024_Itrim_358048737.pdf", file=BytesIO(b"%PDF-1.4"))
    upload.source_context = {"channel": "drive_cartella_unica", "drive_file_id": "drv-1"}
    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert chiamate == [{"nome_file": "LIPE_2024_Itrim_358048737.pdf",
                         "origine": "documenti_upload_auto", "drive_file_id": "drv-1",
                         "dry_run": False}]
    assert result["lipe"]["depositati"] == ["2026-01"]
    assert result["success"] is True


def test_una_lipe_gia_archiviata_deposita_comunque_i_periodi(monkeypatch):
    """Il duplicato recupera le LIPE archiviate prima della correzione."""
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _ingest_finto("duplicate"))
    chiamate = _deposito_registrato(monkeypatch)

    upload = UploadFile(filename="LIPE_2026_407141844.pdf", file=BytesIO(b"%PDF-1.4"))
    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert len(chiamate) == 1
    assert result["duplicate"] is True


def test_un_770_non_passa_dal_deposito_lipe(monkeypatch):
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _ingest_finto("inserted"))
    chiamate = _deposito_registrato(monkeypatch)

    upload = UploadFile(filename="770_T251027111246468144_04523831214.pdf", file=BytesIO(b"%PDF-1.4"))
    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert chiamate == []
    assert "lipe" not in result


def test_un_deposito_lipe_fallito_non_annulla_l_archiviazione(monkeypatch):
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "dichiarazione_fiscale")
    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: object()))
    from app.services import lipe_deposito
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    monkeypatch.setattr(FiscalDocumentIngestionService, "ingest", _ingest_finto("inserted"))

    async def _rotto(*_a, **_k):
        raise ValueError("pdf illeggibile")

    monkeypatch.setattr(lipe_deposito, "deposita_lipe", _rotto)
    upload = UploadFile(filename="LIPE_2026_407141844.pdf", file=BytesIO(b"%PDF-1.4"))
    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert result["success"] is True
    assert result["lipe"]["errore"] == "ValueError: pdf illeggibile"
