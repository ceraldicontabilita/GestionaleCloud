import asyncio
import hashlib
import io
import unittest
import zipfile
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
from fastapi import HTTPException, UploadFile

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
        self.acconti_dipendenti = EmptyPaymentsCollection()  # lo stato del mese conta gli acconti del registro
        self.pagamenti_storico = HistoricalPaymentsCollection()


class SafeEmployeeCollection:
    def __init__(self):
        self.documents = [{
            "id": "employee-safe",
            "nome": "Mario",
            "cognome": "Rossi",
            "nome_completo": "Rossi Mario",
            "codice_fiscale": "RSSMRA80A01H501U",
            "iban": "IT02L1234567890123456789012",
            "stato": "attivo",
        }]
        self.updates = []

    def find(self, *args, **kwargs):
        return AsyncCursor(self.documents)

    async def update_one(self, query, update, **kwargs):
        self.updates.append((query, update))
        document = next(d for d in self.documents if d["id"] == query["id"])
        document.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)


class SafeAnagraficaDatabase:
    def __init__(self):
        self.dipendenti = SafeEmployeeCollection()


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


def anagrafica_con_riepilogo_bytes():
    workbook = openpyxl.Workbook()
    riepilogo = workbook.active
    riepilogo.title = "Riepilogo Consulente"
    riepilogo.append(["Dipendente", "Codice fiscale", "IBAN (per il bonifico)", "Paga giorn. (€)"])
    riepilogo.append(["ROSSI MARIO", "RSSMRA80A01H501U", "IT60X0542811101000000123456", 55])
    anagrafica = workbook.create_sheet("Anagrafiche Dipendenti")
    anagrafica.append(["Dipendente", "Codice fiscale", "IBAN", "Data assunzione", "Ferie residue"])
    anagrafica.append(["ROSSI MARIO", "RSSMRA80A01H501U", "IT60X0542811101000000123456", date(2024, 3, 21), 2.2])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class GestionaleCloudImportCompatibilityTests(unittest.TestCase):
    def test_anagrafica_preview_uses_named_sheet_and_never_writes(self):
        data = anagrafica_con_riepilogo_bytes()
        database = SafeAnagraficaDatabase()
        upload = UploadFile(filename="anagrafiche.xlsx", file=io.BytesIO(data))

        with patch.object(dipendenti_cloud, "get_db", return_value=database):
            result = asyncio.run(dipendenti_cloud.importa_anagrafica(upload, applica=False))

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["foglio"], "Anagrafiche Dipendenti")
        self.assertEqual(result["conteggi"]["aggiornabile"], 1)
        self.assertEqual(result["aggiornati"], 0)
        self.assertEqual(result["righe"][0]["campi"], ["data_assunzione", "iban"])
        self.assertIn("Ferie residue", result["colonne_ignorate"])
        self.assertEqual(database.dipendenti.updates, [])

    def test_anagrafica_apply_requires_same_file_hash_and_updates_only_allowed_fields(self):
        data = anagrafica_con_riepilogo_bytes()
        database = SafeAnagraficaDatabase()

        with patch.object(dipendenti_cloud, "get_db", return_value=database):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(dipendenti_cloud.importa_anagrafica(
                    UploadFile(filename="anagrafiche.xlsx", file=io.BytesIO(data)),
                    applica=True,
                    conferma_hash="hash-diverso",
                ))
            self.assertEqual(caught.exception.status_code, 409)
            result = asyncio.run(dipendenti_cloud.importa_anagrafica(
                UploadFile(filename="anagrafiche.xlsx", file=io.BytesIO(data)),
                applica=True,
                conferma_hash=hashlib.sha256(data).hexdigest(),
            ))

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["aggiornati"], 1)
        self.assertEqual(len(database.dipendenti.updates), 1)
        written = database.dipendenti.updates[0][1]["$set"]
        self.assertEqual(written, {
            "iban": "IT60X0542811101000000123456",
            "data_assunzione": "2024-03-21",
        })
        self.assertEqual(database.dipendenti.documents[0]["nome_completo"], "Rossi Mario")

    def test_anagrafica_without_named_sheet_rejects_payroll_summary(self):
        data = workbook_bytes(
            ["Dipendente", "Codice fiscale", "IBAN", "Paga giornaliera"],
            [["ROSSI MARIO", "RSSMRA80A01H501U", "IT60X0542811101000000123456", 55]],
            sheet_name="Riepilogo Consulente",
        )
        upload = UploadFile(filename="riepilogo.xlsx", file=io.BytesIO(data))
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(dipendenti_cloud.importa_anagrafica(upload, applica=False))
        self.assertEqual(caught.exception.status_code, 400)

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
