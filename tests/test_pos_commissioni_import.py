import asyncio
import io

import openpyxl
from mongomock_motor import AsyncMongoMockClient

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
    assert result["days"] == [{
        "data": "2026-03-30", "numero_transazioni": 156,
        "importo_lordo": 1775.10, "importo_netto": 1763.26,
        "commissioni": 11.84, "importo_commissioni_originale": -11.84,
        "quadratura": 0.0, "quadrato": True,
        "source_filename": "Commissioni_Aprile_2026.xlsx",
    }]


def test_import_sovrapposto_tiene_la_fotografia_piu_completa():
    async def scenario():
        db = AsyncMongoMockClient()["pos_commissioni"]
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
