import asyncio
from mongomock_motor import AsyncMongoMockClient

from app.database import Database
from app.routers import fiscal_control
from app.services import drive_document_index


def test_summary_exposes_verified_drive_counts_without_turning_them_into_db_records(monkeypatch):
    db = AsyncMongoMockClient()["fiscal-drive-summary"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(drive_document_index, "get_overview", lambda: {
        "validation": {"all_true": True, "counts": {
            "documents": 941, "f24_documents": 320,
            "f24_rows": 1297, "declarations": 60,
        }},
        "semantics": {"f24_model_is_not_bank_payment": True},
    })

    payload = asyncio.run(fiscal_control.summary(_admin={}))
    assert payload["counts"]["documents"] == 0
    assert payload["drive_index"]["verified"] is True
    assert payload["drive_index"]["counts"]["f24_rows"] == 1297


def test_f24_rows_read_through_drive_and_keep_payment_unverified(monkeypatch):
    db = AsyncMongoMockClient()["fiscal-drive-f24"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(drive_document_index, "list_f24_rows", lambda **_kwargs: {
        "items": [{
            "id": "drive-row-1", "document_id": "DOC-F24", "ordinal": 1,
            "source_kind": "DRIVE_EXCEL_INDEX_F24_ROW", "tax_code": "1704",
            "reference_period": "2026", "debit_amount": 51.64, "credit_amount": 0,
            "evidence_state": "MODELLO_F24_NON_PROVA_BANCARIA",
        }],
        "total": 1,
    })

    payload = asyncio.run(fiscal_control.f24_rows(
        tax_code="1704", document_id=None, year=2026, credits_only=False,
        offset=0, limit=200, _admin={},
    ))
    assert payload["total"] == 1
    assert payload["sources"] == {
        "drive_excel_index": 1, "database": 0, "drive_warning": None,
    }
    assert payload["items"][0]["evidence_state"] == "MODELLO_F24_NON_PROVA_BANCARIA"


def test_declarations_read_through_drive_when_transitional_db_is_empty(monkeypatch):
    db = AsyncMongoMockClient()["fiscal-drive-declarations"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(drive_document_index, "list_declarations", lambda **_kwargs: {
        "results": [{
            "id": "DOC-770", "document_id": "DOC-770", "sha256": "a" * 64,
            "source_kind": "DRIVE_EXCEL_INDEX_DECLARATION",
            "document_type": "MODELLO_770", "filing_year": 2026,
            "tax_year": 2025, "filename": "770_2026.pdf", "f24_links": [],
        }],
        "total_matching": 1,
    })

    payload = asyncio.run(fiscal_control.declarations(
        year=2026, declaration_type="MODELLO_770", _admin={},
    ))
    assert payload["total"] == 1
    assert payload["sources"]["drive_excel_index"] == 1
    assert payload["items"][0]["filename"] == "770_2026.pdf"
