"""Le operazioni amministrative distruttive richiedono guardie e audit."""
import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.database import Database
from app.routers.admin import reset_collections


def test_reset_non_puo_cancellare_collezioni_di_sicurezza(monkeypatch):
    db = MemorySheetsClient()["admin_guard_test"]
    monkeypatch.setattr(Database, "db", db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(reset_collections(
            selected=["audit_log"],
            confirmation="RESET_SELECTED_COLLECTIONS",
            current_user={"sub": "admin-test"},
        ))
    assert exc.value.status_code == 403


def test_reset_operativo_lascia_prova_di_audit(monkeypatch):
    db = MemorySheetsClient()["admin_guard_test"]
    monkeypatch.setattr(Database, "db", db)
    asyncio.run(db["cache_operativa"].insert_one({"id": "x"}))

    result = asyncio.run(reset_collections(
        selected=["cache_operativa"],
        confirmation="RESET_SELECTED_COLLECTIONS",
        current_user={"sub": "admin-test"},
    ))

    assert result["deleted_collections"]["cache_operativa"]["deleted"] == 1
    assert asyncio.run(db["admin_destructive_audit"].count_documents({})) == 1
