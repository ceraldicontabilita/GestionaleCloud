import asyncio

from app.services import sheets_runtime_database as runtime_module
from app.services.sheets_runtime_database import SheetsRuntimeDatabase


def run(coro):
    return asyncio.run(coro)


def test_runtime_idrata_e_persistenza_write_through(monkeypatch):
    calls = []

    async def fake_restore(db, config, apply=False):
        assert apply is True
        await db["invoices"].insert_one({"id": "INV-1", "total_amount": 10})
        return {
            "fogli": [
                {"foglio": sheet.title, "collezione": sheet.collection,
                 "prefisso": sheet.prefix,
                 "valide": 1 if sheet.collection == "invoices" else 0,
                 "numero_errori": 0}
                for sheet in runtime_module.SHEETS
            ]
        }

    async def fake_sync(db, sheet, spreadsheet_id, *, preserve_missing=True):
        assert preserve_missing is False
        calls.append((sheet.collection, spreadsheet_id,
                      await db[sheet.collection].count_documents({})))
        return {"foglio": sheet.title, "righe": calls[-1][2]}

    monkeypatch.setattr(runtime_module, "restore_all", fake_restore)
    monkeypatch.setattr(runtime_module, "sync_collection", fake_sync)
    runtime = SheetsRuntimeDatabase("test", {
        "GOOGLE_SHEETS_LEDGER_ID": "SHEET-1",
    })

    run(runtime.hydrate())
    assert run(runtime["invoices"].count_documents({})) == 1
    run(runtime["invoices"].insert_one({"id": "INV-2", "total_amount": 20}))

    assert calls == [("invoices", "SHEET-1", 2)]


def test_runtime_blocca_collezione_non_migrata():
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})
    try:
        runtime["users"]
    except RuntimeError as exc:
        assert "non ancora migrata" in str(exc)
    else:
        raise AssertionError("Una collezione fuori manifest non deve usare storage implicito")


def test_runtime_memorizza_il_foglio_scoperto_per_le_scritture(monkeypatch):
    calls = []

    async def fake_restore(db, config, apply=False):
        assert apply is True
        return {
            "spreadsheet_id": "SHEET-DISCOVERED",
            "fogli": [
                {"foglio": sheet.title, "collezione": sheet.collection,
                 "prefisso": sheet.prefix, "valide": 0, "numero_errori": 0}
                for sheet in runtime_module.SHEETS
            ],
        }

    async def fake_sync(db, sheet, spreadsheet_id, *, preserve_missing=True):
        calls.append((sheet.collection, spreadsheet_id, preserve_missing))
        return {"foglio": sheet.title, "righe": 0}

    monkeypatch.setattr(runtime_module, "restore_all", fake_restore)
    monkeypatch.setattr(runtime_module, "sync_collection", fake_sync)
    runtime = SheetsRuntimeDatabase("test", {
        "GOOGLE_SHEETS_LEDGER_FOLDER_ID": "FOLDER-1",
    })

    run(runtime.hydrate())
    run(runtime["invoices"].insert_one({"id": "INV-1"}))

    assert calls == [("invoices", "SHEET-DISCOVERED", False)]
