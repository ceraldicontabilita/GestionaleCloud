import asyncio
import base64

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers import verbali_noleggio
from app.services.verbali_pdf_service import collect_verbale_pdfs, pdf_metadata


def _database():
    db = ClientArchivioMemoria()["verbali-pdf"]
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
    monkeypatch.setattr(verbali_noleggio.Database, "get_db", lambda: db)

    result = asyncio.run(
        verbali_noleggio.get_dettaglio_verbale("VV/24990121765")
    )

    assert len(result["pdf_disponibili"]) == 1
    assert result["pdf_disponibili"][0]["source"] == "documents_inbox"
    assert result["fascicolo"]["verbale"]["presente"] is True


def test_endpoint_dettaglio_riunisce_quietanza_partenopay_e_banca(monkeypatch):
    db, _ = _database()
    asyncio.run(db["verbali_noleggio"].update_one(
        {"numero_verbale": "VV/24990121765"},
        {"$set": {
            "movimento_banca_id": "mov-1",
            "banca_verificata": True,
            "quietanza_ricevuta": True,
            "pagato_documentalmente": True,
            "psp": "PartenoPay (Comune di Napoli)",
            "source_files": ["documenti/02_quietanze/quietanza-verbale.pdf"],
        }},
    ))
    asyncio.run(db["estratto_conto_movimenti"].insert_one({
        "id": "mov-1", "data_contabile": "2026-03-30",
        "importo": -51.64, "descrizione": "Pagamento verbale VV/24990121765",
    }))
    monkeypatch.setattr(verbali_noleggio.Database, "get_db", lambda: db)

    result = asyncio.run(verbali_noleggio.get_dettaglio_verbale("VV/24990121765"))

    assert result["fascicolo"]["pagamento_banca"]["presente"] is True
    assert result["fascicolo"]["pagamento_banca"]["movimento"]["id"] == "mov-1"
    assert result["fascicolo"]["quietanza"]["presente"] is True
    assert result["fascicolo"]["quietanza"]["fonte"] == "PartenoPay (Comune di Napoli)"
