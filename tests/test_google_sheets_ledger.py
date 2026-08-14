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


def test_fogli_dinamici_hanno_nome_e_prefisso_stabili():
    first = ledger.dynamic_sheet("sumup_transactions")
    second = ledger.dynamic_sheet("sumup_transactions")

    assert first == second
    assert first.title == "DB_sumup_transactions"
    assert first.collection == "sumup_transactions"
    assert first.prefix.startswith("D")
    assert len(first.prefix) == 7


def test_payload_grande_viene_diviso_e_ricostruito(monkeypatch):
    monkeypatch.setattr(ledger, "MAX_SHEETS_CELL_CHARS", 80)
    monkeypatch.setattr(ledger, "PAYLOAD_CHUNK_COUNT", 1000)
    payload = {"id": "BIG-1", "contenuto": "".join(f"{i:08x}" for i in range(2000))}

    chunks = ledger.payload_chunks(payload)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert ledger.decode_payload("".join(chunks)) == payload


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


def test_identita_canonica_accetta_le_chiavi_reali_degli_archivi():
    for field in (
        "invoice_id", "document_id", "cedolino_id", "movement_id",
        "bonifico_id", "quietanza_id", "estratto_id",
    ):
        document = {field: f"chiave-{field}"}
        assert ledger.canonical_id(document) == f"chiave-{field}"
        assert ledger.canonical_filter(document) == {field: f"chiave-{field}"}


def test_payload_grande_viene_compresso_e_ricostruito_senza_perdite():
    payload = {"id": "DOC-GRANDE", "testo": "documento fiscale " * 10000}
    encoded = ledger.encode_payload(payload)

    assert encoded.startswith(ledger.GZIP_PREFIX)
    assert len(encoded) <= ledger.MAX_SHEETS_CELL_CHARS
    assert ledger.decode_payload(encoded) == payload


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


def test_sync_esporta_anche_documenti_storici_con_solo_objectid(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        inserted = await db.cedolini.insert_one({"periodo": "2026-07", "netto": 1000})
        captured = {}
        monkeypatch.setattr(ledger, "_read_existing_sync", lambda *_: [])
        monkeypatch.setattr(
            ledger, "_write_rows_sync",
            lambda _sid, _sheet, rows: captured.setdefault("rows", rows),
        )

        result = await ledger.sync_collection(
            db, next(item for item in ledger.SHEETS if item.title == "Cedolini"), "SHEET-1",
        )

        assert result["righe"] == 1
        assert captured["rows"][0][1] == str(inserted.inserted_id)
        assert json.loads(captured["rows"][0][15])["_mongo_id"] == str(inserted.inserted_id)

    run(scenario())


def test_restore_default_e_solo_validazione(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        sheet = ledger.SHEETS[0]
        payload = {"id": "DOC-1", "filename": "prova.pdf"}
        row = ledger.row_for_document(payload, "DOC-00000001")
        monkeypatch.setattr(
            ledger, "ensure_workbook",
            lambda _config=None, _collections=(): asyncio.sleep(0, result={
                "spreadsheet_id": "SHEET-1", "spreadsheet_url": "https://example.invalid/sheet",
                "sheet_definitions": ledger.SHEETS,
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


def test_audit_migrazione_blocca_collezioni_non_coperte(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_one({"id": "INV-1"})
        await db.users.insert_one({"id": "USR-1"})

        async def fake_restore(*_args, **_kwargs):
            return {
                "spreadsheet_id": "SHEET-1",
                "fogli": [
                    {"collezione": sheet.collection,
                     "valide": 1 if sheet.collection == "invoices" else 0,
                     "numero_errori": 0}
                    for sheet in ledger.SHEETS
                ],
            }

        monkeypatch.setattr(ledger, "restore_all", fake_restore)
        result = await ledger.migration_audit(db)

        assert result["pronto_cutover"] is False
        assert result["collezioni_non_migrate"] == [
            {"collezione": "users", "righe": 1}
        ]

    run(scenario())


def test_copia_canonica_preferisce_nome_originale_e_piu_antico():
    files = [
        {"id": "COPY", "name": "Fattura (2).pdf", "createdTime": "2020-01-01"},
        {"id": "NEW", "name": "Fattura.pdf", "createdTime": "2022-01-01"},
        {"id": "OLD", "name": "Fattura.pdf", "createdTime": "2021-01-01"},
    ]
    assert sorted(files, key=ledger._canonical_duplicate_key)[0]["id"] == "OLD"


def test_anteprima_pulizia_considera_solo_md5_e_permessi(monkeypatch):
    monkeypatch.setattr(ledger, "_drive_folder_duplicate_audit_sync", lambda _ids: {
        "radici_richieste": 1,
        "duplicati": [
            {"metodo": "md5", "file": [
                {"id": "KEEP", "name": "Cedolino.pdf", "createdTime": "2020", "md5Checksum": "abc"},
                {"id": "TRASH", "name": "Cedolino (2).pdf", "createdTime": "2021", "md5Checksum": "abc", "capabilities": {"canTrash": True}},
                {"id": "LOCKED", "name": "Cedolino (3).pdf", "createdTime": "2022", "md5Checksum": "abc", "capabilities": {"canTrash": False}},
            ]},
            {"metodo": "nome_dimensione", "file": [
                {"id": "A", "name": "stesso.pdf"}, {"id": "B", "name": "stesso.pdf"},
            ]},
        ],
    })

    result = ledger._trash_exact_duplicates_sync(["ROOT"], apply=False)

    assert result["gruppi_md5"] == 1
    assert result["copie_selezionate"] == 1
    assert result["copie_senza_permesso"] == 1
    assert result["anteprima"][0]["file_id"] == "TRASH"
