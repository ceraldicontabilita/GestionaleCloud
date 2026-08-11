import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti


def _run(awaitable):
    return asyncio.run(awaitable)


def _db(monkeypatch):
    db = AsyncMongoMockClient()["archivio_documenti_test"]
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    return db


def test_archivio_pagina_sul_server_e_non_espone_payload(monkeypatch):
    db = _db(monkeypatch)
    _run(db.documents_inbox.insert_many([
        {
            "id": f"doc-{index}",
            "filename": f"fattura-{index}.pdf",
            "category": "fattura",
            "category_label": "Fatture",
            "status": "processato",
            "processed": True,
            "processed_to": "fatture",
            "document_date": f"2026-07-{index + 1:02d}",
            "downloaded_at": f"2026-07-{index + 1:02d}T10:00:00+00:00",
            "pdf_data": "A" * 10_000,
            "file_base64": "B" * 10_000,
        }
        for index in range(4)
    ]))

    result = _run(documenti.lista_documenti(
        categoria=None,
        status=None,
        anno=2026,
        search=None,
        limit=2,
        skip=2,
    ))

    assert result["total"] == 4
    assert result["skip"] == 2
    assert result["limit"] == 2
    assert result["has_more"] is False
    assert len(result["documents"]) == 2
    assert all("pdf_data" not in item for item in result["documents"])
    assert all("file_base64" not in item for item in result["documents"])
    assert all(item["linked_to"] == "fatture" for item in result["documents"])


def test_archivio_filtra_anno_e_ricerca_letterale(monkeypatch):
    db = _db(monkeypatch)
    _run(db.documents_inbox.insert_many([
        {
            "id": "target-2025",
            "filename": "F24 [saldo].pdf",
            "category": "f24",
            "status": "nuovo",
            "periodo": "2025-06",
            "source": "email",
        },
        {
            "id": "other-2025",
            "filename": "F24 saldo.pdf",
            "category": "f24",
            "status": "nuovo",
            "periodo": "2025-06",
        },
        {
            "id": "target-2026",
            "filename": "F24 [saldo].pdf",
            "category": "f24",
            "status": "nuovo",
            "periodo": "2026-06",
        },
    ]))

    result = _run(documenti.lista_documenti(
        categoria="f24",
        status="nuovo",
        anno=2025,
        search="[saldo]",
        limit=50,
        skip=0,
    ))

    assert result["total"] == 1
    assert result["documents"][0]["id"] == "target-2025"
    assert result["documents"][0]["source_label"] == "email"


def test_archivio_espone_anomalie_senza_correggere_record(monkeypatch):
    db = _db(monkeypatch)
    _run(db.documents_inbox.insert_one({
        "id": "errore-1",
        "filename": "sconosciuto.pdf",
        "category": "altro",
        "status": "errore",
        "processed": True,
        "processing_error": "parser fallito",
        "downloaded_at": "2026-08-01T10:00:00+00:00",
    }))

    result = _run(documenti.lista_documenti(
        categoria=None,
        status=None,
        anno=None,
        search=None,
        limit=50,
        skip=0,
    ))

    item = result["documents"][0]
    assert set(item["anomalies"]) == {
        "errore_elaborazione",
        "classificazione_da_verificare",
        "collegamento_mancante",
        "periodo_da_verificare",
    }
    persisted = _run(db.documents_inbox.find_one({"id": "errore-1"}))
    assert "anomalies" not in persisted
    assert persisted["status"] == "errore"


@pytest.mark.parametrize(
    ("categoria", "status"),
    [("inesistente", None), (None, "pagato")],
)
def test_archivio_rifiuta_filtri_non_validi(monkeypatch, categoria, status):
    _db(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _run(documenti.lista_documenti(
            categoria=categoria,
            status=status,
            anno=2026,
            search=None,
            limit=50,
            skip=0,
        ))
    assert exc.value.status_code == 400
