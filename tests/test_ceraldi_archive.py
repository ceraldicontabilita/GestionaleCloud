"""Paginazione del reader canonico oltre il precedente tetto di 5000 righe."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ceraldi_archive_memory", ROOT / "app/services/archivio_documenti_memoria.py")
memory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = memory
spec.loader.exec_module(memory)
source = ROOT / "app/routers/invoices/invoices_main.py"
functions = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name.startswith("_")]
namespace = {"Any": Any, "Dict": Dict, "List": List,
             "Collections": SimpleNamespace(INVOICES="invoices")}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)


class ArchivePaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_later_pages_are_complete_and_do_not_overlap(self):
        db = memory.ArchivioDocumenti()
        await db["invoices"].insert_many([
            {"id": str(index), "invoice_number": str(index),
             "supplier_vat": "00123456789", "invoice_date": "2026-10-08",
             "total_amount": "10.00"} for index in range(6503)
        ])
        namespace["Database"] = SimpleNamespace(get_db=lambda: db)
        load = namespace["_load_invoices"]
        pages = []
        for skip in range(0, 7000, 500):
            pages.extend(await load({}, 500, skip))
        self.assertEqual(len(pages), 6503)
        self.assertEqual(len({row["id"] for row in pages}), 6503)
        self.assertEqual((await load({}, 500, 6500))[-1]["id"], "6502")

    async def test_deduplication_precedes_page_boundary_and_requires_original_evidence(self):
        db = memory.ArchivioDocumenti()
        original = {"id": "original", "invoice_number": "001/26", "supplier_vat": "00123456789",
                    "invoice_date": "2026-10-08", "total_amount": "10.00", "source_hash": "same-real-original"}
        await db["invoices"].insert_many([
            original,
            {**original, "id": "richer", "linee": [{"descrizione": "riga XML"}]},
            {**original, "id": "separate-original", "source_hash": "different-real-original"},
        ])
        namespace["Database"] = SimpleNamespace(get_db=lambda: db)
        result = await namespace["_load_invoices"]({}, 1, 1)
        self.assertEqual([row["id"] for row in result], ["separate-original"])
        self.assertTrue(result[0]["duplicate_review_required"])


if __name__ == "__main__":
    unittest.main()
