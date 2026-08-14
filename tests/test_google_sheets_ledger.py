import asyncio
import json

from mongomock_motor import AsyncMongoMockClient

from app.services import google_sheets_ledger as ledger


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_manifest_ha_fogli_collezioni_e_prefissi_unici():
    manifest = ledger.sheet_manifest()
    assert len(manifest) >= 18
    assert len({row["foglio"] for row in manifest}) == len(manifest)
    assert len({row["collezione"] for row in manifest}) == len(manifest)
    assert len({row["prefisso"] for row in manifest}) == len(manifest)
    assert {"Cedolini", "Estratti conto", "Movimenti bancari", "Bonifici"} <= {
        row["foglio"] for row in manifest
    }


def test_progressivo_e_operation_id_restano_separati():
    document = {
        "id": "EC-2026-1", "data": "2026-08-14", "tipo": "entrata",
        "importo": 5000.0, "trasferimento_operation_id": "trasferimento-contanti:EC-2026-1",
        "descrizione": "VERSAMENTO CONTANTI",
    }
    row = ledger.row_for_document(document, "ECM-00000042")
    assert row[0] == "ECM-00000042"
    assert row[1] == "EC-2026-1"
    assert row[2] == "trasferimento-contanti:EC-2026-1"
    assert row[3] == "2026-08-14"
    assert row[6] == 5000.0
    assert json.loads(row[15])["id"] == "EC-2026-1"
    assert ledger.next_progressive("ECM", ["ECM-00000002", "ALT-999", "ECM-00000009"]) == 10


def test_sync_mantiene_progressivi_e_righe_storiche(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.estratto_conto_movimenti.insert_many([
            {"id": "EC-1", "data": "2026-01-01", "importo": 10},
            {"id": "EC-2", "data": "2026-01-02", "importo": 20},
        ])
        existing = [
            ["ECM-00000007", "EC-1"] + [""] * 14,
            ["ECM-00000008", "EC-STORICO"] + [""] * 13
            + [json.dumps({"id": "EC-STORICO"})],
        ]
        captured = {}
        monkeypatch.setattr(ledger, "_read_existing_sync", lambda *_: existing)
        monkeypatch.setattr(ledger, "_write_rows_sync", lambda _sid, _sheet, rows: captured.setdefault("rows", rows))

        result = await ledger.sync_collection(
            db, next(item for item in ledger.SHEETS if item.title == "Movimenti bancari"), "SHEET-1",
        )

        assert result["righe"] == 3
        by_id = {row[1]: row for row in captured["rows"]}
        assert by_id["EC-1"][0] == "ECM-00000007"
        assert by_id["EC-2"][0] == "ECM-00000009"
        assert by_id["EC-STORICO"][0] == "ECM-00000008"

    run(scenario())


def test_restore_default_e_solo_validazione(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        sheet = ledger.SHEETS[0]
        payload = {"id": "DOC-1", "filename": "prova.pdf"}
        row = ledger.row_for_document(payload, "DOC-00000001")
        monkeypatch.setattr(
            ledger, "ensure_workbook",
            lambda _config=None: asyncio.sleep(0, result={
                "spreadsheet_id": "SHEET-1", "spreadsheet_url": "https://example.invalid/sheet",
            }),
        )
        monkeypatch.setattr(
            ledger, "_read_sheet_rows_sync",
            lambda _sid, candidate: [row] if candidate == sheet else [],
        )

        result = await ledger.restore_all(db, apply=False)

        assert result["apply"] is False
        assert result["fogli"][0]["valide"] == 1
        assert await db.documents_inbox.count_documents({}) == 0

    run(scenario())
