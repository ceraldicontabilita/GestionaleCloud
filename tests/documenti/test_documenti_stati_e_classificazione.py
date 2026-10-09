"""Archivio Documenti: stati normalizzati, classificazione che non si
sovrascrive, dedup per SHA-256, anteprima che riconosce le fatture gia'
importate.

Dati del 27/09/2026: 376 documenti `errore_parser` e 1.417 `elaborato` (la
card «Errori» diceva 0); DOC_DUPLICATO cercava `hash_file` (0 documenti);
DOC_NON_CLASSIFICATO riclassificava dal nome del file anche i documenti con
una categoria; un XML gia' importato risultava «Nuovo» in anteprima.
"""
import asyncio
import hashlib

from app.database import Database
from app.routers import documenti
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.document_import_preview import _duplicate_sources
from app.services.handlers.documento_handlers import on_documento_acquisito


def test_query_archivio_usa_le_varianti_dello_stato():
    assert documenti._archive_query(status="errore") == {
        "status": {"$in": ["errore", "errore_parser"]},
    }
    assert documenti._archive_query(status="processato") == {
        "status": {"$in": ["processato", "elaborato"]},
    }


def test_metadati_normalizzano_lo_stato():
    item = documenti._archive_document_metadata({"id": "d1", "status": "errore_parser"})
    assert item["status"] == "errore"
    assert item["status_originale"] == "errore_parser"
    assert "errore_elaborazione" in item["anomalies"]
    assert documenti._archive_document_metadata({"id": "d2", "status": "elaborato"})["status"] == "processato"


def test_lista_conta_errori_e_processati_con_le_varianti(monkeypatch):
    db = ArchivioDocumenti()

    async def scenario():
        await db["documents_inbox"].insert_many([
            {"id": "e1", "status": "errore_parser", "category": "f24"},
            {"id": "e2", "status": "errore", "category": "f24"},
            {"id": "p1", "status": "elaborato", "category": "f24"},
            {"id": "n1", "status": "nuovo", "category": "f24"},
        ])
        tutti = await documenti.lista_documenti(
            categoria=None, status=None, anno=None, search=None, limit=50, skip=0,
        )
        errori = await documenti.lista_documenti(
            categoria=None, status="errore", anno=None, search=None, limit=50, skip=0,
        )
        return tutti, errori

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    tutti, errori = asyncio.run(scenario())
    assert tutti["by_status"] == {"errore": 2, "processato": 1, "nuovo": 1}
    assert errori["total"] == 2
    assert {d["status"] for d in errori["documents"]} == {"errore"}


def _evento(doc_id, filename, hash_file=""):
    return {"documento_id": doc_id, "filename": filename, "origine": "gmail",
            "mime_type": "application/pdf", "hash_file": hash_file}


def test_documento_con_categoria_non_si_riclassifica_ne_apre_alert():
    async def scenario():
        db = ArchivioDocumenti()
        await db["documents_inbox"].insert_one(
            {"id": "d1", "category": "cedolini", "tipo_documento": "cedolino_zucchetti"},
        )
        esito = await on_documento_acquisito(_evento("d1", "scansione_0001.pdf"), db)
        doc = await db["documents_inbox"].find_one({"id": "d1"}, {"_id": 0})
        alert = await db["alerts"].find({}, {"_id": 0}).to_list(None)
        return esito, doc, alert

    esito, doc, alert = asyncio.run(scenario())
    assert esito["action"] == "documento_gia_classificato"
    assert doc["tipo_documento"] == "cedolino_zucchetti"
    assert alert == []


def test_documento_senza_categoria_resta_segnalato():
    async def scenario():
        db = ArchivioDocumenti()
        await db["documents_inbox"].insert_one({"id": "d1", "category": "altro"})
        await on_documento_acquisito(_evento("d1", "scansione_0001.pdf"), db)
        return await db["alerts"].find({}, {"_id": 0}).to_list(None)

    assert [a["codice"] for a in asyncio.run(scenario())] == ["DOC_NON_CLASSIFICATO"]


def test_duplicato_riconosciuto_per_sha256_non_per_md5():
    contenuto = b"%PDF-1.4 stesso file"
    sha = hashlib.sha256(contenuto).hexdigest()
    md5 = hashlib.md5(contenuto).hexdigest()

    async def scenario():
        db = ArchivioDocumenti()
        await db["documents_inbox"].insert_many([
            {"id": "orig", "sha256": sha, "category": "altro"},
            {"id": "copia", "file_hash": sha, "category": "altro"},
            {"id": "md5", "file_hash": md5, "category": "altro"},
        ])
        await on_documento_acquisito(_evento("copia", "a.pdf", hash_file=sha), db)
        # Un MD5 nell'evento non basta a dichiarare un doppione
        await on_documento_acquisito(_evento("md5", "b.pdf", hash_file=md5), db)
        return await db["alerts"].find({"codice": "DOC_DUPLICATO"}, {"_id": 0}).to_list(None)

    alert = asyncio.run(scenario())
    assert [a["entita_id"] for a in alert] == ["copia"]
    assert "orig" in alert[0]["dettaglio"]


XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<p:FatturaElettronica versione="FPR12" xmlns:p="x"><Body>1</Body></p:FatturaElettronica>'
)


def test_anteprima_riconosce_la_fattura_gia_importata():
    contenuto = XML.encode("utf-8")
    sha = hashlib.sha256(contenuto).hexdigest()
    md5 = hashlib.md5(contenuto).hexdigest()
    con_bom = b"\xef\xbb\xbf" + contenuto

    async def scenario():
        db = ArchivioDocumenti()
        vuoto = await _duplicate_sources(db, sha, md5, contenuto)
        # L'import salva lo SHA-256 del testo XML decodificato in content_hash
        await db["invoices"].insert_one({"id": "inv-1", "content_hash": sha, "invoice_number": "1"})
        stesso = await _duplicate_sources(db, sha, md5, contenuto)
        bom = await _duplicate_sources(
            db, hashlib.sha256(con_bom).hexdigest(), hashlib.md5(con_bom).hexdigest(), con_bom,
        )
        return vuoto, stesso, bom

    vuoto, stesso, bom = asyncio.run(scenario())
    assert vuoto == []
    assert [d["collection"] for d in stesso] == ["invoices"]
    assert stesso[0]["id"] == "inv-1"
    # Lo stesso XML con un BOM davanti e' la stessa fattura
    assert [d["collection"] for d in bom] == ["invoices"]
