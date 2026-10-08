"""Regressioni dell'aggancio NC sul vero archivio locale, senza servizi esterni."""
import ast
import importlib.util
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


memory = load_file("ceraldi_test_memory", "app/services/archivio_documenti_memoria.py")
states = load_file("ceraldi_test_states", "app/services/stato_pagamento_fattura.py")
active = load_file("ceraldi_test_active", "app/constants/fattura_attiva.py")
ids = load_file("ceraldi_test_ids", "app/utils/id_fattura.py")
source = ROOT / "app/routers/invoices/fatture_upload.py"
node = next(node for node in ast.parse(source.read_text()).body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_collega_nota_credito")
namespace = {
    "Any": Any, "Dict": Dict, "Optional": Optional,
    "Decimal": Decimal, "InvalidOperation": InvalidOperation, "ROUND_HALF_UP": ROUND_HALF_UP,
    "Collections": SimpleNamespace(INVOICES="invoices"),
    "NOTE_CREDITO_TIPI_DOCUMENTO": {"TD04", "TD08"},
    "FILTRO_FATTURA_ATTIVA": active.FILTRO_FATTURA_ATTIVA,
    "fattura_attiva": active.fattura_attiva,
    "e_pagata": states.e_pagata, "e_annullata": states.e_annullata,
    "filtro_id": ids.filtro_id, "logger": logging.getLogger("ceraldi-nc-test"),
}
# Il router importa parser e servizi opzionali; si compila il suo stesso corpo
# senza avviare quei servizi. Ledger, filtri e helper sono il codice reale.
exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
link = namespace["_collega_nota_credito"]


class CreditNoteTests(unittest.IsolatedAsyncioTestCase):
    async def seed(self, *originals, credit_amount="0.20", **credit_fields):
        db = memory.ArchivioDocumenti()
        invoice = {
            "id": "fattura-con-zero-001", "invoice_number": "001/26",
            "supplier_vat": "00123456789", "tipo_documento": "TD01",
            "total_amount": "0.30", "stato": "da_pagare",
        }
        credit = {
            "id": "nc-uuid", "invoice_number": "NC/1",
            "supplier_vat": "00123456789", "tipo_documento": "TD04",
            "total_amount": credit_amount,
            "dati_fatture_collegate": [{"id_documento": "001/26"}],
            **credit_fields,
        }
        for item in (invoice, *originals, credit):
            await db["invoices"].insert_one(item.copy())
        return db, credit

    async def test_unique_link_is_idempotent_and_preserves_decimal_and_ids(self):
        db, credit = await self.seed()
        first = await link(db, credit)
        second = await link(db, credit)
        self.assertEqual(first, second)
        self.assertEqual(first["importo_netto_originale"], "0.10")
        original = await db["invoices"].find_one({"id": "fattura-con-zero-001"})
        self.assertEqual(original["note_credito_collegate"], ["nc-uuid"])
        self.assertEqual(original["stato"], "da_pagare")
        stored_credit = await db["invoices"].find_one({"id": "nc-uuid"})
        self.assertEqual(stored_credit["fattura_collegata_id"], "fattura-con-zero-001")

    async def test_ambiguous_reference_changes_neither_document(self):
        other = {"id": "altra-fattura", "invoice_number": "001/26", "supplier_vat": "00123456789", "total_amount": "9.00", "tipo_documento": "TD01"}
        db, credit = await self.seed(other)
        self.assertIsNone(await link(db, credit))
        for item in await db["invoices"].find({}).to_list(20):
            self.assertNotIn("fattura_collegata_id", item)
            self.assertNotIn("note_credito_collegate", item)

    async def test_paid_original_and_manual_exclusion_are_preserved(self):
        for paid_field in ({"stato": "pagata"}, {"payment_status": "paid"}, {"pagato": True}):
            db, credit = await self.seed()
            await db["invoices"].update_one({"id": "fattura-con-zero-001"}, {"$set": paid_field})
            self.assertIsNone(await link(db, credit))
        db, credit = await self.seed(notes="testo", note="[NC-NO-AUTO]")
        self.assertIsNone(await link(db, credit))

    async def test_missing_supplier_or_amount_never_invents_a_match_or_zero(self):
        for fields in ({"supplier_vat": ""}, {"total_amount": None}, {"total_amount": "NaN"}):
            db, credit = await self.seed(**fields)
            self.assertIsNone(await link(db, credit))

    async def test_multiple_xml_targets_are_ambiguous_and_existing_link_is_not_moved(self):
        other = {"id": "seconda", "invoice_number": "002/26", "supplier_vat": "00123456789", "total_amount": "10.00", "tipo_documento": "TD01"}
        db, credit = await self.seed(other, dati_fatture_collegate=[{"id_documento": "001/26"}, {"id_documento": "002/26"}])
        self.assertIsNone(await link(db, credit))
        db, credit = await self.seed(fattura_collegata_id="collegamento-manuale")
        self.assertIsNone(await link(db, credit))

    async def test_original_import_recovers_earlier_notes_once_and_respects_exclusion(self):
        db, credit = await self.seed()
        original = await db["invoices"].find_one({"id": "fattura-con-zero-001"})
        result = await link(db, original)
        self.assertEqual(result["note_credito_collegate"], ["nc-uuid"])
        self.assertEqual(result["importo_netto"], "0.10")
        self.assertIsNone(await link(db, original))
        db, _ = await self.seed(note="[NC-NO-AUTO]")
        original = await db["invoices"].find_one({"id": "fattura-con-zero-001"})
        self.assertIsNone(await link(db, original))
        db, _ = await self.seed()
        await db["invoices"].update_one({"id": "fattura-con-zero-001"}, {"$set": {"stato": "pagata"}})
        original = await db["invoices"].find_one({"id": "fattura-con-zero-001"})
        self.assertIsNone(await link(db, original))


if __name__ == "__main__":
    unittest.main()
