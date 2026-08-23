import asyncio

import pytest
from fastapi import HTTPException

from app.database import Database
from app.routers import lotti_integration
from app.services.sheets_document_store import SheetDatabase


@pytest.fixture()
def sheet_db():
    original = Database.db
    db = SheetDatabase("test-lotti")
    Database.db = db
    try:
        yield db
    finally:
        Database.db = original


def run(coro):
    return asyncio.run(coro)


def test_projection_reads_invoices_and_is_stable(sheet_db, monkeypatch):
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    run(sheet_db["invoices"].insert_one({
        "id": "inv-1",
        "invoice_number": "44/A",
        "invoice_date": "2026-08-20",
        "supplier_name": "Molino Test",
        "supplier_vat": "01234567890",
        "total_amount": 122,
        "linee": [{"descrizione": "Farina 00", "quantita": "2", "unita_misura": "KG", "prezzo_unitario": "10"}],
        "xml_raw": "<FatturaElettronica />",
    }))
    run(sheet_db["fatture_ricevute"].insert_one({"id": "sbagliata"}))

    first = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=200, x_lotti_key="secret-test"
    ))
    second = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=200, x_lotti_key="secret-test"
    ))

    assert first == second
    assert first["total"] == 1
    assert first["data"][0]["source_id"] == "inv-1"
    assert first["data"][0]["has_xml"] is True
    assert "xml_raw" not in first["data"][0]
    assert len(first["data"][0]["source_hash"]) == 64

    detail = run(lotti_integration.get_invoice_for_lotti("inv-1", "secret-test"))
    assert detail["xml_raw"] == "<FatturaElettronica />"
    assert detail["lines"][0]["descrizione"] == "Farina 00"


def test_projection_filters_year_and_deleted(sheet_db, monkeypatch):
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    run(sheet_db["invoices"].insert_many([
        {"id": "old", "invoice_date": "2025-01-01"},
        {"id": "deleted", "invoice_date": "2026-01-01", "status": "deleted"},
        {"id": "current", "invoice_date": "23/08/2026"},
    ]))
    result = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=50, x_lotti_key="secret-test"
    ))
    assert [item["source_id"] for item in result["data"]] == ["current"]


def test_projection_fails_closed_without_secret(sheet_db, monkeypatch):
    monkeypatch.delenv("LOTTI_INTEGRATION_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        run(lotti_integration.list_invoices_for_lotti(
            anno=2026, skip=0, limit=50, x_lotti_key="anything"
        ))
    assert exc.value.status_code == 503
