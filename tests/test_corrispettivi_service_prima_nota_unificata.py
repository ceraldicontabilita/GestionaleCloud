"""Bug scoperto il 14/07/2026: CorrispettiviService._create_prima_nota_entry
(usato da drive_corrispettivi_ingest.py e da create_manual) era una TERZA
implementazione parallela e diversa della regola contabile corrispettivi
già unificata in corrispettivi_helpers.py::_create_prima_nota_movements.
Leggeva pagato_pos invece di pagato_elettronico e non creava MAI la riga
in prima_nota_banca (mai vista da Coerenza POS). Ora delega alla stessa
implementazione condivisa: questo test verifica che il fix sia effettivo."""
import asyncio

from app.services.corrispettivi_service import CorrispettiviService


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        elif isinstance(v, dict) and ("$gte" in v or "$lte" in v):
            pass  # non serve per questi test
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return

    async def delete_many(self, query, *a, **k):
        self.docs = [d for d in self.docs if not _matches(d, query)]

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    def __setitem__(self, name, value):
        self.collections[name] = value


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_create_prima_nota_entry_crea_anche_la_riga_banca():
    db = _FakeDb()
    svc = CorrispettiviService(db=db)
    corr = {
        "id": "corr-1", "data": "2026-07-14",
        "totale": 1000.0, "pagato_contanti": 600.0, "pagato_elettronico": 400.0,
    }

    prima_nota_id = _run(svc._create_prima_nota_entry(corr))

    assert prima_nota_id is not None
    cassa = db["prima_nota_cassa"].docs
    banca = db["prima_nota_banca"].docs
    assert len(cassa) == 2  # entrata totale + uscita POS
    assert len(banca) == 1  # entrata POS in banca — MAI creata prima del fix
    entrata_cassa = next(d for d in cassa if d["tipo"] == "entrata")
    uscita_cassa = next(d for d in cassa if d["tipo"] == "uscita")
    assert entrata_cassa["importo"] == 1000.0
    assert uscita_cassa["importo"] == 400.0
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["importo"] == 400.0
    assert banca[0]["source"] == "corrispettivo_pos"  # letto da Coerenza POS


def test_create_prima_nota_entry_legge_pagato_pos_come_fallback():
    # I corrispettivi da CorrispettiviService.process_xml storicamente
    # salvano "pagato_pos" (non pagato_elettronico): deve continuare a
    # funzionare come fallback, non solo con il nome campo nuovo.
    db = _FakeDb()
    svc = CorrispettiviService(db=db)
    corr = {"id": "corr-2", "data": "2026-07-14", "totale": 500.0,
            "pagato_contanti": 300.0, "pagato_pos": 200.0}

    _run(svc._create_prima_nota_entry(corr))

    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["importo"] == 200.0
