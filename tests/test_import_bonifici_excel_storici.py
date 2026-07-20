"""Import storico bonifici: colonna corretta, idempotenza e zero falsi match."""

import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook


class _InsertResult:
    inserted_id = "test"


class _Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _InsertResult()


class _Db:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, name):
        assert name == "prima_nota_salari"
        return self.collection


def _xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def _upload(content):
    return UploadFile(filename="bonifici.xlsx", file=BytesIO(content))


def test_importa_importo_acconto_non_importo_busta_ed_e_idempotente(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        [
            "ANNO", "MESE", "NOME DIPENDENTE", "IMPORTO BUSTA",
            "DATA ACCONTO", "IMPORTO ACCONTO",
        ],
        [
            [2025, "Gennaio", "Mario Rossi", 9999, "10/02/2025", 1200.50],
            [2025, "Gennaio", "Mario Rossi", 9999, "10/02/2025", 1200.50],
            [2025, "Gennaio", "Mario Rossi", 9999, "20/02/2025", 1200.50],
            [2025, "Febbraio", "Lucia Verdi", 1500, None, None],
        ],
    )

    primo = asyncio.run(modulo.import_bonifici(_upload(content)))
    secondo = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert primo["created"] == 2
    assert primo["duplicates"] == 1
    assert primo["skipped"] == 1
    assert primo["totale_documentato"] == 2401.0
    assert secondo["created"] == 0
    assert secondo["duplicates"] == 3
    assert len(db.collection.docs) == 2
    assert {d["data_bonifico_documentata"] for d in db.collection.docs} == {
        "2025-02-10", "2025-02-20",
    }
    for doc in db.collection.docs:
        assert doc["dipendente"] == "MARIO ROSSI"
        assert doc["importo_busta"] == 0
        assert doc["importo_bonifico"] == 0
        assert doc["importo_bonifico_documentato"] == 1200.50
        assert doc["riconciliato"] is False
        assert doc["source"] == "excel_bonifici_storici"
        assert "cedolino_id" not in doc


def test_import_generico_senza_data_bonifico(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        ["Dipendente", "Mese", "Anno", "Importo erogato"],
        [["Dipendente Test", "Marzo", 2024, "1.234,56"]],
    )

    esito = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert esito["created"] == 1
    assert db.collection.docs[0]["importo_bonifico_documentato"] == 1234.56
    assert db.collection.docs[0]["data_bonifico_documentata"] is None


def test_importo_busta_da_solo_non_e_un_bonifico(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        ["Dipendente", "Mese", "Anno", "Importo Busta"],
        [["Dipendente Test", "Marzo", 2024, 1500]],
    )

    with pytest.raises(HTTPException) as errore:
        asyncio.run(modulo.import_bonifici(_upload(content)))

    assert errore.value.status_code == 400
    assert not db.collection.docs
