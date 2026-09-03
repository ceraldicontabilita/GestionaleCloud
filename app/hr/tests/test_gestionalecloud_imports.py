import asyncio
import io
import unittest
import zipfile
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
from fastapi import UploadFile

from app.hr.routers import dipendenti_cloud


class AsyncCursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.position = 0

    async def to_list(self, limit):
        return self.documents[:limit]

    def __aiter__(self):
        self.position = 0
        return self

    async def __anext__(self):
        if self.position >= len(self.documents):
            raise StopAsyncIteration
        document = self.documents[self.position]
        self.position += 1
        return document


class EmployeeCollection:
    def __init__(self):
        self.documents = [{
            "id": "employee-test",
            "nome": "Mario",
            "cognome": "Rossi",
            "nome_completo": "Mario Rossi",
        }]

    def find(self, *args, **kwargs):
        return AsyncCursor(self.documents)


class MonthlyPayrollCollection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *args, **kwargs):
        return "test-index"

    async def find_one(self, query, *args, **kwargs):
        key = (query["dipendente_id"], query["anno"], query["mese"])
        return self.documents.get(key)

    async def update_one(self, query, update, upsert=False):
        key = (query["dipendente_id"], query["anno"], query["mese"])
        created = key not in self.documents
        document = self.documents.setdefault(key, {})
        if created:
            document.update(update.get("$setOnInsert", {}))
        document.update(update.get("$set", {}))
        return SimpleNamespace(upserted_id="created" if created else None)


class EmptyPaymentsCollection:
    def find(self, *args, **kwargs):
        return AsyncCursor([])


class HistoricalPaymentsCollection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *args, **kwargs):
        return "test-index"

    async def update_one(self, query, update, upsert=False):
        key = (
            query["dipendente_id"],
            query["data"],
            query["busta"],
            query["pagato"],
        )
        created = key not in self.documents
        if created:
            self.documents[key] = dict(update["$setOnInsert"])
        return SimpleNamespace(upserted_id="created" if created else None)


class FakeDatabase:
    def __init__(self):
        self.dipendenti = EmployeeCollection()
        self.paghe_mensili = MonthlyPayrollCollection()
        self.pagamenti_esiti = EmptyPaymentsCollection()
        self.pagamenti_storico = HistoricalPaymentsCollection()


def workbook_bytes(headers, rows, sheet_name="Prima Nota"):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class GestionaleCloudImportCompatibilityTests(unittest.TestCase):
    def test_numeric_month_and_separate_payments_are_aggregated(self):
        data = workbook_bytes(
            ["Dipendente", "Mese", "Anno", "Stipendio Netto", "Importo Erogato"],
            [
                ["MARIO ROSSI", 3, 2026, 1000.00, 200.00],
                ["MARIO ROSSI", 3, 2026, 1000.00, 800.00],
            ],
        )
        database = FakeDatabase()
        upload = UploadFile(filename="prima_nota_salari.xlsx", file=io.BytesIO(data))

        with patch.object(dipendenti_cloud, "get_db", return_value=database):
            result = asyncio.run(dipendenti_cloud.importa_excel_salari(upload))

        stored = database.paghe_mensili.documents[("employee-test", 2026, 3)]
        self.assertEqual(result["righe_lette"], 2)
        self.assertEqual(result["righe_aggregate"], 1)
        self.assertEqual(result["importati"], 1)
        self.assertEqual(result["scartati"], [])
        self.assertEqual(stored["importo_busta"], 1000.0)
        self.assertEqual(stored["bonifico_importo"], 1000.0)
        self.assertEqual(stored["erogato_atteso"], 1000.0)
        self.assertEqual(stored["stato_pagamento"], "pagato")
        self.assertEqual(stored["saldo"], 0.0)

    def test_historical_workbook_uses_true_excel_dates_and_numeric_amounts(self):
        data = workbook_bytes(
            ["Data bonifico", "Nome dipendente", "Importo di busta", "Importo effettivamente pagato"],
            [
                [date(2022, 6, 10), "MARIO ROSSI", 900.25, 300.10],
                [date(2022, 6, 20), "MARIO ROSSI", 900.25, 600.15],
            ],
            sheet_name="ROSSI",
        )
        database = FakeDatabase()
        upload = UploadFile(filename="storico_pagamenti.xlsx", file=io.BytesIO(data))

        with patch.object(dipendenti_cloud, "get_db", return_value=database):
            result = asyncio.run(dipendenti_cloud.importa_storico_pagamenti(upload))

        self.assertEqual(result["righe_lette"], 2)
        self.assertEqual(result["importati"], 2)
        self.assertEqual(result["gia_presenti"], 0)
        self.assertEqual(result["dipendenti_non_in_anagrafica"], [])
        self.assertEqual(len(database.pagamenti_storico.documents), 2)

    def test_payroll_zip_preserves_original_pdf_bytes(self):
        original = b"%PDF-1.4\noriginal-payroll-bytes\n%%EOF"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("export_cedolini/2026-03_ROSSI_MARIO.pdf", original)

        items, errors = dipendenti_cloud._espandi_in_pdf("export_cedolini.zip", output.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0][0].endswith("2026-03_ROSSI_MARIO.pdf"))
        self.assertEqual(items[0][1], original)


if __name__ == "__main__":
    unittest.main()
