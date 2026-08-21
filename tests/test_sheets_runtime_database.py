import asyncio

import pytest

from app.services import sheets_runtime_database as runtime_module
from app.services.sheets_runtime_database import SheetsRuntimeDatabase


def run(coro):
    return asyncio.run(coro)


def test_runtime_idrata_e_persistenza_write_through(monkeypatch):
    calls = []

    async def fake_restore(db, config, apply=False, provision=True):
        assert apply is True
        assert provision is False
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

    async def fake_upsert(sheet, spreadsheet_id, documents):
        calls.append((
            sheet.collection, spreadsheet_id,
            [document["id"] for document in documents],
        ))
        return {"foglio": sheet.title, "aggiunte": len(documents)}

    monkeypatch.setattr(runtime_module, "restore_all", fake_restore)
    monkeypatch.setattr(runtime_module, "upsert_documents", fake_upsert)
    runtime = SheetsRuntimeDatabase("test", {
        "GOOGLE_SHEETS_LEDGER_ID": "SHEET-1",
    })

    run(runtime.hydrate())
    assert run(runtime["invoices"].count_documents({})) == 1
    run(runtime["invoices"].insert_one({"id": "INV-2", "total_amount": 20}))

    assert calls == [("invoices", "SHEET-1", ["INV-2"])]


def test_runtime_non_nasconde_i_dati_validi_per_una_riga_anomala(monkeypatch):
    async def fake_restore(db, config, apply=False, provision=True):
        await db["invoices"].insert_one({"id": "INV-VALIDA", "total_amount": 10})
        return {
            "spreadsheet_id": "SHEET-1",
            "fogli": [
                {
                    "foglio": "Fatture",
                    "collezione": "invoices",
                    "prefisso": "FAT",
                    "valide": 1,
                    "numero_errori": 1,
                    "errori": [{"riga": 7, "errore": "payload non valido"}],
                }
            ],
        }

    monkeypatch.setattr(runtime_module, "restore_all", fake_restore)
    runtime = SheetsRuntimeDatabase(
        "test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"},
    )

    result = run(runtime.hydrate())

    assert run(runtime["invoices"].count_documents({})) == 1
    assert result["fogli"][0]["numero_errori"] == 1
    assert runtime.hydration_result == result


def test_runtime_predispone_foglio_drive_per_collezione_operativa(monkeypatch):
    ensured = []
    synced = []

    async def fake_ensure(spreadsheet_id, collection):
        ensured.append((spreadsheet_id, collection))
        return runtime_module.LedgerSheet("DB_users", collection, "D123456")

    async def fake_upsert(sheet, spreadsheet_id, documents):
        synced.append((sheet.collection, spreadsheet_id, len(documents)))
        return {"foglio": sheet.title, "aggiunte": len(documents)}

    monkeypatch.setattr(runtime_module, "ensure_collection_sheet", fake_ensure)
    monkeypatch.setattr(runtime_module, "upsert_documents", fake_upsert)
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})

    assert run(runtime["users"].find_one({})) is None
    run(runtime["users"].insert_one({"id": "USR-1"}))

    assert ensured == [("SHEET-1", "users")]
    assert synced == [("users", "SHEET-1", 1)]
    assert run(runtime["users"].count_documents({})) == 1


def test_runtime_ripristina_header_di_foglio_dinamico_precreato(monkeypatch):
    ensured = []

    async def fake_ensure(spreadsheet_id, collection):
        ensured.append((spreadsheet_id, collection))
        return runtime_module.LedgerSheet("DB_users", collection, "D123456")

    async def fake_upsert(sheet, spreadsheet_id, documents):
        return {"foglio": sheet.title, "aggiunte": len(documents)}

    monkeypatch.setattr(runtime_module, "ensure_collection_sheet", fake_ensure)
    monkeypatch.setattr(runtime_module, "upsert_documents", fake_upsert)
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})
    runtime._by_collection["users"] = runtime_module.LedgerSheet(
        "DB_users", "users", "D123456",
    )

    run(runtime["users"].insert_one({"id": "USR-1"}))
    run(runtime["users"].insert_one({"id": "USR-2"}))

    assert ensured == [("SHEET-1", "users")]


def test_runtime_espone_stato_sistema_per_checkpoint_import():
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})

    assert runtime["sistema_stato"] is not None


def test_runtime_espone_la_transazione_atomica_del_registro():
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})
    runtime.loading = True
    async def scenario():
        async with runtime.transaction():
            await runtime["sistema_stato"].insert_one({"id": "atomic-1"})
    run(scenario())
    assert run(runtime["sistema_stato"].count_documents({"id": "atomic-1"})) == 1


def test_runtime_memorizza_il_foglio_scoperto_per_le_scritture(monkeypatch):
    calls = []

    async def fake_restore(db, config, apply=False, provision=True):
        assert apply is True
        assert provision is True
        return {
            "spreadsheet_id": "SHEET-DISCOVERED",
            "fogli": [
                {"foglio": sheet.title, "collezione": sheet.collection,
                 "prefisso": sheet.prefix, "valide": 0, "numero_errori": 0}
                for sheet in runtime_module.SHEETS
            ],
        }

    async def fake_upsert(sheet, spreadsheet_id, documents):
        calls.append((sheet.collection, spreadsheet_id, len(documents)))
        return {"foglio": sheet.title, "aggiunte": len(documents)}

    monkeypatch.setattr(runtime_module, "restore_all", fake_restore)
    monkeypatch.setattr(runtime_module, "upsert_documents", fake_upsert)
    runtime = SheetsRuntimeDatabase("test", {
        "GOOGLE_SHEETS_LEDGER_FOLDER_ID": "FOLDER-1",
    })

    run(runtime.hydrate())
    run(runtime["invoices"].insert_one({"id": "INV-1"}))

    assert calls == [("invoices", "SHEET-DISCOVERED", 1)]


def test_runtime_update_persistisce_solo_il_documento_modificato(monkeypatch):
    calls = []

    async def fake_upsert(sheet, spreadsheet_id, documents):
        calls.append([document["id"] for document in documents])
        return {"foglio": sheet.title, "aggiunte": len(documents)}

    monkeypatch.setattr(runtime_module, "upsert_documents", fake_upsert)
    runtime = SheetsRuntimeDatabase("test", {"GOOGLE_SHEETS_LEDGER_ID": "SHEET-1"})
    run(runtime["invoices"].insert_many([
        {"id": "INV-1", "total_amount": 10},
        {"id": "INV-2", "total_amount": 20},
    ]))
    calls.clear()

    run(runtime["invoices"].update_one(
        {"id": "INV-2"}, {"$set": {"total_amount": 25}},
    ))

    assert calls == [["INV-2"]]
