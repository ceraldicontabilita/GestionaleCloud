import asyncio
import hashlib
import io

import openpyxl
from app.services.sheets_document_store import MemorySheetsClient

from app.services.pos_commissioni_import import (
    importa_pos_commissioni_file,
    parse_pos_commissioni_file,
)


def _xlsx(rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sintesi giornaliera commissioni"
    sheet.append(["Sintesi Aprile 2026 - Tutti i punti vendita"])
    sheet.append([])
    sheet.append([
        "Data", "Numero transazioni", "Importo lordo", "Importo netto",
        "Importo commissioni", "% commissioni",
    ])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parser_commissioni_quadra_lordo_netto():
    result = parse_pos_commissioni_file(
        _xlsx([["30/03/2026", 156, 1775.10, 1763.26, -11.84, -0.00667]]),
        "Commissioni_Aprile_2026.xlsx",
    )
    operation_key = hashlib.sha256(
        b"pos:numia:commissioni:v1:2026-03-30"
    ).hexdigest()
    assert result["days"] == [{
        "id": f"POS-COMMISSIONI-{operation_key[:32]}",
        "operation_id": f"pos:numia:commissioni:{operation_key}",
        "operation_key": operation_key,
        "identity_version": "pos_numia_commissioni_v1",
        "data": "2026-03-30", "numero_transazioni": 156,
        "importo_lordo": 1775.10, "importo_netto": 1763.26,
        "commissioni": 11.84, "importo_commissioni_originale": -11.84,
        "quadratura": 0.0, "quadrato": True,
        "source_filename": "Commissioni_Aprile_2026.xlsx",
    }]


def test_parser_commissioni_esclude_la_riga_totale_excel():
    result = parse_pos_commissioni_file(
        _xlsx([
            ["30/03/2026", 156, 1775.10, 1763.26, -11.84, -0.00667],
            [0, 156, 1775.10, 1763.26, -11.84, -0.00667],
        ]),
        "Commissioni_Aprile_2026.xlsx",
    )

    assert result["rows"] == 1
    assert result["days"][0]["data"] == "2026-03-30"


def test_import_sovrapposto_tiene_la_fotografia_piu_completa():
    async def scenario():
        db = MemorySheetsClient()["pos_commissioni"]
        small = _xlsx([["30/03/2026", 16, 252.10, 251.37, -0.73, -0.0029]])
        complete = _xlsx([["30/03/2026", 156, 1775.10, 1763.26, -11.84, -0.00667]])
        await importa_pos_commissioni_file(db, small, "Commissioni_Marzo_2026.xlsx")
        result = await importa_pos_commissioni_file(db, complete, "Commissioni_Aprile_2026.xlsx")
        saved = await db["pos_commissioni_giornaliere"].find_one({"data": "2026-03-30"})
        assert result["updated"] == 1
        assert saved["numero_transazioni"] == 156
        assert saved["importo_netto"] == 1763.26

        duplicate = await importa_pos_commissioni_file(
            db, complete, "Commissioni_Aprile_2026.xlsx"
        )
        assert duplicate["duplicates"] == 1

    asyncio.run(scenario())


def test_import_commissioni_usa_un_solo_batch_per_file():
    async def scenario():
        db = MemorySheetsClient()["pos_commissioni_batch"]
        calls = 0

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def batch_writes():
            nonlocal calls
            calls += 1
            yield

        db.batch_writes = batch_writes
        rows = [
            [f"{day:02d}/04/2026", day, 100 + day, 99 + day, -1, -0.01]
            for day in range(1, 31)
        ]
        result = await importa_pos_commissioni_file(
            db, _xlsx(rows), "Commissioni_Aprile_2026.xlsx",
        )
        return calls, result

    calls, result = asyncio.run(scenario())
    assert calls == 1
    assert result["inserted"] == 30


def test_import_commissioni_runtime_flusha_una_volta_per_foglio():
    async def scenario():
        from app.services.sheets_runtime_database import SheetsRuntimeDatabase

        db = SheetsRuntimeDatabase(
            "pos_commissioni_runtime", {"GOOGLE_SHEETS_LEDGER_ID": "test-ledger"},
        )
        persisted = []

        async def persist_documents(collection_name, documents):
            persisted.append((collection_name, len(documents)))
            return {"aggiornati": 0, "inseriti": len(documents)}

        async def remove_documents(_collection_name, _canonical_ids):
            return {"rimossi": 0}

        db.persist_documents = persist_documents
        db.remove_documents = remove_documents
        rows = [
            [f"{day:02d}/04/2026", day, 100 + day, 99 + day, -1, -0.01]
            for day in range(1, 31)
        ]
        await importa_pos_commissioni_file(
            db, _xlsx(rows), "Commissioni_Aprile_2026.xlsx",
        )
        return persisted

    persisted = asyncio.run(scenario())
    assert persisted == [
        ("pos_commissioni_giornaliere", 30),
        ("pos_commissioni_imports", 1),
    ]
