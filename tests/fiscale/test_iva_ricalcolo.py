"""
Calcola pregresso IVA (POST /ricalcola-attribuzione): deve leggere TUTTE le
fatture, ricalcolare i campi IVA, produrre un report verificabile e persisterlo
(GET /ricalcola-attribuzione/ultimo). Il fake-db preserva `_id` perché il
ricalcolo aggiorna le fatture per `_id`.
"""
import asyncio
import re

import pytest

from app.routers import iva as iva_router
from app.database import Database


def _match(doc, query):
    for k, cond in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = doc.get(k)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            for op, arg in cond.items():
                if op == "$regex" and not (val is not None and re.search(arg, str(val))):
                    return False
        elif val != cond:
            return False
    return True


class _Cur:
    def __init__(self, items):
        self._items = items

    def sort(self, *a):
        return self

    async def to_list(self, n):
        return [dict(x) for x in self._items[:n]]

    def __aiter__(self):
        self._it = iter(list(self._items))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))  # conserva _id
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None, sort=None):
        items = [d for d in self.docs if _match(d, query)]
        if sort:
            key, direction = sort[0]
            items = sorted(items, key=lambda d: (d.get(key) is None, d.get(key)),
                           reverse=direction < 0)
        if not items:
            return None
        d = dict(items[0])
        d.pop("_id", None)
        return d

    def find(self, query, proj=None):
        return _Cur([d for d in self.docs if _match(d, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))

                class _R:
                    modified_count = 1
                return _R()

        class _R0:
            modified_count = 0
        return _R0()


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: d))
    return d


def test_ricalcolo_legge_tutte_e_riporta(db):
    db["invoices"].docs.extend([
        {"_id": 1, "invoice_date": "2026-01-10", "data_ricezione": "2026-01-12", "iva": 100},
        {"_id": 2, "invoice_date": "2026-02-05", "data_ricezione": "2026-02-06", "iva": 50},
        {"_id": 3, "iva": 30},  # senza date → da verificare
    ])
    res = _run(iva_router.ricalcola_attribuzione(anno=None, utente="mario"))
    rep = res["report"]
    assert rep["lette"] == 3
    assert rep["con_periodo"] == 2
    assert rep["da_verificare"] == 1
    assert rep["modificate"] == 3  # tutte arricchite la prima volta
    # ripartizione per anno del periodo attribuito
    assert rep["per_anno"].get("2026") == 2
    # le fatture ora hanno il periodo salvato
    assert db["invoices"].docs[0]["periodo_iva_attribuito"] == "2026-01"


def test_ricalcolo_idempotente_seconda_volta_invariate(db):
    db["invoices"].docs.append(
        {"_id": 1, "invoice_date": "2026-03-10", "data_ricezione": "2026-03-11", "iva": 200}
    )
    _run(iva_router.ricalcola_attribuzione(anno=None, utente="admin"))
    res2 = _run(iva_router.ricalcola_attribuzione(anno=None, utente="admin"))
    rep = res2["report"]
    assert rep["lette"] == 1
    assert rep["modificate"] == 0 and rep["invariate"] == 1  # niente cambia al 2° giro


def test_ricalcolo_persistito_e_recuperabile(db):
    db["invoices"].docs.append(
        {"_id": 1, "invoice_date": "2026-01-10", "data_ricezione": "2026-01-12", "iva": 100}
    )
    _run(iva_router.ricalcola_attribuzione(anno=None, utente="mario"))
    ultimo = _run(iva_router.ultimo_ricalcolo())
    assert ultimo["ultimo"] is not None
    assert ultimo["ultimo"]["lette"] == 1
    assert ultimo["ultimo"]["eseguito_da"] == "mario"


def test_ricalcolo_non_tocca_iva_utilizzata(db):
    db["invoices"].docs.append({
        "_id": 1, "invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
        "iva": 100, "iva_utilizzata": True,
        "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
        "periodo_iva_utilizzato": "2026-01", "periodo_iva_attribuito": "2026-01",
    })
    res = _run(iva_router.ricalcola_attribuzione(anno=None, utente="admin"))
    assert res["report"]["gia_utilizzate"] == 1
    inv = db["invoices"].docs[0]
    assert inv["iva_utilizzata"] is True
    assert inv["stato_detrazione_iva"] == "INSERITA_IN_LIQUIDAZIONE"
