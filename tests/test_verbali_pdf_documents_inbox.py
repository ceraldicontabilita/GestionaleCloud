import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.routers import verbali_noleggio, verbali_noleggio_api
from app.services.verbali_pdf_service import collect_verbale_pdfs, pdf_metadata


def _database():
    db = AsyncMongoMockClient()["verbali-pdf"]
    verbale = {
        "id": "verbale-test",
        "numero_verbale": "VV/24990121765",
        "source_document_id": "documento-test",
        "document_ids": ["documento-test"],
    }
    asyncio.run(db["verbali_noleggio"].insert_one(dict(verbale)))
    asyncio.run(db["documents_inbox"].insert_one({
        "id": "documento-test",
        "filename": "verbale-asia.pdf",
        "file_hash": "hash-test",
        "pdf_data": base64.b64encode(b"%PDF-1.4 test").decode("ascii"),
        "verbale_id": "verbale-test",
        "tipo_documento": "verbale",
        "created_at": "2026-05-13T10:00:00+00:00",
    }))
    return db, verbale


def test_documento_inbox_compare_nel_dettaglio_senza_base64():
    db, verbale = _database()
    items = asyncio.run(collect_verbale_pdfs(db, verbale, include_content=False))
    metadata = pdf_metadata(items)

    assert len(metadata) == 1
    assert metadata[0]["document_id"] == "documento-test"
    assert metadata[0]["filename"] == "verbale-asia.pdf"
    assert "content_base64" not in metadata[0]


def test_endpoint_pdf_legge_documents_inbox_e_numero_con_slash(monkeypatch):
    db, _ = _database()
    monkeypatch.setattr(verbali_noleggio.Database, "get_db", lambda: db)

    result = asyncio.run(verbali_noleggio.get_pdf_verbale("VV/24990121765", 0))

    assert result["document_id"] == "documento-test"
    assert base64.b64decode(result["content_base64"]).startswith(b"%PDF")


def test_endpoint_dettaglio_path_include_pdf_inbox(monkeypatch):
    db, _ = _database()
    monkeypatch.setattr(verbali_noleggio_api.Database, "get_db", lambda: db)

    result = asyncio.run(
        verbali_noleggio_api.get_verbale_dettaglio("VV/24990121765")
    )

    assert len(result["pdf_disponibili"]) == 1
    assert result["pdf_disponibili"][0]["source"] == "documents_inbox"
