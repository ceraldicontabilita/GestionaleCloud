"""Test della ristrutturazione CDC sui 4 settori reali e della migrazione
non distruttiva del centro_costo delle fatture."""
import asyncio

from app.routers.accounting import centri_costo as cc
from app.scripts import migra_cdc_4_settori as mig


def test_quattro_settori_operativi():
    op = [k for k, v in cc.CDC_STANDARD.items() if v["tipo"] == "operativo"]
    assert op == ["CDC-01", "CDC-02", "CDC-03", "CDC-04"]
    assert cc.CDC_STANDARD["CDC-03"]["nome"] == "GELATERIA"
    assert cc.CDC_STANDARD["CDC-04"]["nome"] == "ROSTICCERIA"


def test_mappa_categorie_ai_settori():
    assert cc.CATEGORIA_TO_CDC["gelato"] == "CDC-03"
    assert cc.CATEGORIA_TO_CDC["gastronomia"] == "CDC-04"
    assert cc.CATEGORIA_TO_CDC["farine"] == "CDC-02"
    assert cc.CATEGORIA_TO_CDC["utenze_elettricita"] == "CDC-99"


# ─── fake DB per la migrazione ───────────────────────────────────────────────
class _Cur:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._it = iter(list(self._items))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query, proj=None):
        # basta il filtro categoria_contabile esistente/non vuota
        return _Cur([d for d in self.docs
                     if d.get("categoria_contabile") not in (None, "")])

    async def update_one(self, query, update):
        for d in self.docs:
            if d.get("_id") == query.get("_id"):
                d.update(update.get("$set", {}))


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


def _fake_db(monkeypatch, docs):
    db = _Db()
    db[cc.Collections.INVOICES].docs = docs
    monkeypatch.setattr(mig.Database, "get_db", staticmethod(lambda: db))
    return db


def test_migrazione_rimappa_e_preserva(monkeypatch):
    docs = [
        # gelato: prima CDC-02, ora CDC-03 → va aggiornata
        {"_id": 1, "categoria_contabile": "gelato", "centro_costo": "CDC-02"},
        # gastronomia: prima CDC-03 (laboratorio), ora CDC-04 → aggiornata
        {"_id": 2, "categoria_contabile": "gastronomia", "centro_costo": "CDC-03"},
        # caffe: già CDC-01 → invariata
        {"_id": 3, "categoria_contabile": "caffe", "centro_costo": "CDC-01"},
        # manuale: da NON toccare
        {"_id": 4, "categoria_contabile": "gelato", "centro_costo": "CDC-02",
         "centro_costo_manuale": True},
        # senza categoria mappata: ignorata
        {"_id": 5, "categoria_contabile": "sconosciuta", "centro_costo": "CDC-99"},
    ]
    db = _fake_db(monkeypatch, docs)

    dry = _run(mig.migra(esegui=False))
    assert dry["da_aggiornare"] == 2
    assert dry["saltate_manuali"] == 1
    # dry-run non scrive
    assert db[cc.Collections.INVOICES].docs[0]["centro_costo"] == "CDC-02"

    run = _run(mig.migra(esegui=True))
    assert run["da_aggiornare"] == 2
    d = {x["_id"]: x for x in db[cc.Collections.INVOICES].docs}
    assert d[1]["centro_costo"] == "CDC-03" and d[1]["centro_costo_migrato_da"] == "CDC-02"
    assert d[2]["centro_costo"] == "CDC-04" and d[2]["centro_costo_migrato_da"] == "CDC-03"
    assert d[3]["centro_costo"] == "CDC-01"           # invariata
    assert d[4]["centro_costo"] == "CDC-02"           # manuale preservata
    assert "centro_costo_migrato_da" not in d[4]

    # idempotente
    again = _run(mig.migra(esegui=True))
    assert again["da_aggiornare"] == 0
