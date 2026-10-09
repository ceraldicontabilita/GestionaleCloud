"""Import storico bonifici: colonna corretta, idempotenza e zero falsi match."""

import asyncio
from io import BytesIO

from fastapi import UploadFile
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

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if doc is not None:
            doc.update(update.get("$set", {}))


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


def test_importa_busta_e_acconto_separati_ed_e_idempotente(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        [
            "ANNO", "MESE", "NOME DIPENDENTE", "IMPORTO BUSTA",
            "DATA ACCONTO", "IMPORTO ACCONTO",
        ],
        [
            [2025, "Dicembre", "Mario Rossi", 9999, "10/12/2025", 1200.50],
            [2025, "Dicembre", "Mario Rossi", 9999, "10/12/2025", 1200.50],
            [2025, "Dicembre", "Mario Rossi", None, "20/12/2025", 1200.50],
            [2026, "Gennaio", "Lucia Verdi", 1500, None, None],
        ],
    )

    primo = asyncio.run(modulo.import_bonifici(_upload(content)))
    secondo = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert primo["created"] == 3
    assert primo["duplicates"] == 1
    assert primo["skipped"] == 0
    assert primo["totale_documentato"] == 2401.0
    assert primo["totale_buste_documentato"] == 11499.0
    assert primo["righe_con_busta"] == 2
    assert secondo["created"] == 0
    assert secondo["duplicates"] == 4
    assert len(db.collection.docs) == 3
    assert {d["data_bonifico_documentata"] for d in db.collection.docs} == {
        "2025-12-10", "2025-12-20", None,
    }
    mario = [d for d in db.collection.docs if d["dipendente"] == "MARIO ROSSI"]
    assert sorted(d["importo_busta"] for d in mario) == [0, 9999]
    assert sorted(d["importo_bonifico_documentato"] for d in mario) == [1200.50, 1200.50]
    lucia = next(d for d in db.collection.docs if d["dipendente"] == "LUCIA VERDI")
    assert lucia["importo_busta"] == 1500
    assert lucia["importo_bonifico_documentato"] == 0
    for doc in db.collection.docs:
        assert doc["importo_bonifico"] == 0
        assert doc["riconciliato"] is False
        assert doc["source"] == "excel_bonifici_storici"
        assert "cedolino_id" not in doc


def test_import_generico_senza_data_bonifico(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        ["Dipendente", "Mese", "Anno", "Importo erogato"],
        [["Dipendente Test", "Gennaio", 2026, "1.234,56"]],
    )

    esito = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert esito["created"] == 1
    assert db.collection.docs[0]["importo_bonifico_documentato"] == 1234.56
    assert db.collection.docs[0]["data_bonifico_documentata"] is None


def test_importo_busta_da_solo_viene_importato_ma_non_diventa_bonifico(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        ["Dipendente", "Mese", "Anno", "Importo Busta"],
        [["Dipendente Test", "Gennaio", 2026, 1500]],
    )

    esito = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert esito["created"] == 1
    assert esito["totale_buste_documentato"] == 1500
    assert db.collection.docs[0]["importo_busta"] == 1500
    assert db.collection.docs[0]["importo_bonifico"] == 0
    assert db.collection.docs[0]["importo_bonifico_documentato"] == 0
    assert db.collection.docs[0]["riconciliato"] is False


def test_secondo_import_aggiorna_la_busta_su_bonifico_gia_importato(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        [
            "ANNO", "MESE", "NOME DIPENDENTE", "IMPORTO BUSTA",
            "DATA ACCONTO", "IMPORTO ACCONTO",
        ],
        [[2025, "Dicembre", "Mario Rossi", 1350, "10/12/2025", 1200.50]],
    )
    key = modulo._chiave_bonifico_excel(
        "MARIO ROSSI", 2025, 12, "2025-12-10", 1200.50,
    )
    db.collection.docs.append({
        "import_key": key,
        "importo_busta": 0,
        "importo_bonifico_documentato": 1200.50,
        "source": "excel_bonifici_storici",
    })

    esito = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert esito["created"] == 0
    assert esito["updated"] == 1
    assert esito["duplicates"] == 0
    assert db.collection.docs[0]["importo_busta"] == 1350
    assert db.collection.docs[0]["importo_busta_documentato"] == 1350


def test_import_ignora_competenze_precedenti_dicembre_2025(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    content = _xlsx(
        ["Dipendente", "Mese", "Anno", "Importo Busta"],
        [["Dipendente Storico", "Novembre", 2025, 1500]],
    )

    esito = asyncio.run(modulo.import_bonifici(_upload(content)))

    assert esito["created"] == 0
    assert esito["skipped"] == 1
    assert db.collection.docs == []
