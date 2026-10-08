"""Regressioni dei reader HR sul cursore reale, senza avvio DB/API o librerie opzionali."""
import ast
import logging
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def compile_source(path, names, namespace, decorators=False):
    """Esegue classi/funzioni originali; esclude solo import/startup opzionali."""
    nodes = []
    for node in ast.parse((ROOT / path).read_text()).body:
        name = getattr(node, "name", None)
        if name in names:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not decorators:
                node.decorator_list = []
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets
        ):
            nodes.append(node)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), path, "exec"), namespace)


namespace = {
    "Any": Any, "Dict": Dict, "List": List, "Optional": Optional, "re": re,
    "HTTPException": HTTPException, "logger": logging.getLogger("hr-reader-test"),
}
compile_source("app/hr/db_supabase.py", {
    "_Mancante", "_MANCANTE", "_get", "_confronta", "_match", "_proietta", "_chiave_ordine", "_Cursore",
}, namespace)
Cursor = namespace["_Cursore"]


class Collection:
    def __init__(self, docs=(), error=None):
        self.docs = list(docs)
        self.error = error

    def find(self, filtro, proj):
        return Cursor(self, filtro, proj)

    def _escludibili(self, filtro, proj):
        return []

    async def _seleziona(self, filtro, escludi):
        if self.error:
            raise self.error
        return [dict(doc) for doc in self.docs if namespace["_match"](doc, filtro)]


class Database:
    collection = None

    @classmethod
    def get_db(cls):
        return {"dipendenti": cls.collection}


namespace.update(Database=Database, Collections=SimpleNamespace(EMPLOYEES="dipendenti"), Query=lambda default, **kwargs: default)
compile_source("app/hr/routers/employees/dipendenti.py", {"list_dipendenti"}, namespace)
list_dipendenti = namespace["list_dipendenti"]


class HRPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_employee_reader_accepts_zero_offset_on_empty_archive(self):
        Database.collection = Collection()
        self.assertEqual(await list_dipendenti(limit=10000), [])

    async def test_employee_page_filters_orders_then_skips_and_limits(self):
        Database.collection = Collection([
            {"id": "Z", "nome_completo": "Zeno Rossi", "codice_fiscale": "CFZ", "attivo": True},
            {"id": "M", "nome_completo": "Maria Rossi", "codice_fiscale": "CFM", "attivo": True},
            {"id": "A", "nome_completo": "Anna Rossi", "codice_fiscale": "CFA", "attivo": True},
            {"id": "C", "nome_completo": "Cessato Rossi", "codice_fiscale": "CFC", "attivo": False},
            {"id": "merged", "nome_completo": "Abel Rossi", "codice_fiscale": "CFX", "merged_into": "A", "attivo": True},
        ])
        result = await list_dipendenti(skip=1, limit=1, attivo=True, search="Rossi")
        self.assertEqual([row["id"] for row in result], ["M"])
        self.assertEqual(await list_dipendenti(skip=100, limit=10), [])

    async def test_skip_is_independent_of_chain_order_and_preserves_projection(self):
        coll = Collection([{"_id": index, "anno": 2026, "mese": index, "secret": "hidden"} for index in range(1, 5)])
        first = await coll.find({}, {"_id": 0, "secret": 0}).sort([("anno", -1), ("mese", -1)]).limit(2).skip(1).to_list(2)
        second = await coll.find({}, {"_id": 0, "secret": 0}).skip(1).limit(2).sort([("anno", -1), ("mese", -1)]).to_list(2)
        self.assertEqual(first, second)
        self.assertEqual([row["mese"] for row in first], [3, 2])
        self.assertTrue(all("secret" not in row and "_id" not in row for row in first))

    async def test_async_iteration_and_skip_reset_use_the_same_page(self):
        cursor = Collection([{"id": i} for i in range(5)]).find({}, None).sort("id", 1).skip(2).limit(2)
        self.assertEqual([row["id"] async for row in cursor], [2, 3])
        self.assertEqual([row["id"] for row in await cursor.skip(0).to_list(2)], [0, 1])

    async def test_invalid_offsets_and_database_errors_are_not_empty_successes(self):
        cursor = Collection().find({}, None)
        with self.assertRaises(ValueError):
            cursor.skip(-1)
        with self.assertRaises(TypeError):
            cursor.skip("1")
        Database.collection = Collection(error=ConnectionError("Database non raggiungibile"))
        with self.assertRaises(ConnectionError):
            await list_dipendenti(limit=10000)


if __name__ == "__main__":
    unittest.main()
