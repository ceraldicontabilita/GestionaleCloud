"""Regola contabile fissata dall'utente il 14/07/2026 per il caricamento
corrispettivi in Prima Nota:
- prima_nota_cassa: ENTRATA = totale corrispettivo (contanti + POS)
- prima_nota_cassa: USCITA = quota POS/elettronica (esce verso banca)
- prima_nota_banca: ENTRATA = quota POS/elettronica (copiata, mai duplicata)
Il saldo cassa netto = solo contante. La riga in prima_nota_banca alimenta
anche Coerenza POS (pos_corrispettivi_check.py legge source='corrispettivo_pos').

Copre i due percorsi che scrivono in Prima Nota: il caricamento diretto
(corrispettivi_helpers.py) e la sincronizzazione periodica dello scheduler
(prima_nota_module/sync.py) — devono produrre lo stesso risultato e non
duplicarsi a vicenda.
"""
import asyncio

from app.routers.invoices import corrispettivi_helpers as helpers_mod
from app.routers.prima_nota_module import sync as sync_mod


def _matches(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_matches(doc, q) for q in query["$or"])
    return all(doc.get(k) == v for k, v in query.items())


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

    async def delete_many(self, query, *a, **k):
        rimasti = [d for d in self.docs if not _matches(d, query)]
        rimossi = len(self.docs) - len(rimasti)
        self.docs = rimasti

        class _R:
            deleted_count = rimossi
        return _R()

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


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _corrispettivo(**over):
    base = {
        "id": "corr-1", "data": "2026-07-14",
        "totale": 1000.0, "pagato_contanti": 600.0, "pagato_elettronico": 400.0,
    }
    base.update(over)
    return base


# ---------- percorso 1: caricamento diretto (corrispettivi_helpers.py) ----------

def test_create_prima_nota_movements_regola_contabile_completa():
    db = _FakeDb()
    corr = _corrispettivo()

    res = _run(helpers_mod._create_prima_nota_movements(db, corr))

    cassa = db.collections["prima_nota_cassa"].docs
    banca = db.collections["prima_nota_banca"].docs

    entrata_cassa = next(d for d in cassa if d["tipo"] == "entrata")
    assert entrata_cassa["importo"] == 1000.0
    assert entrata_cassa["categoria"] == "Corrispettivi"

    uscita_cassa = next(d for d in cassa if d["tipo"] == "uscita")
    assert uscita_cassa["importo"] == 400.0
    assert uscita_cassa["categoria"] == "POS Verso Banca"

    entrata_banca = banca[0]
    assert entrata_banca["importo"] == 400.0
    assert entrata_banca["tipo"] == "entrata"
    assert entrata_banca["source"] == "corrispettivo_pos"

    # saldo netto cassa = entrata - uscita = solo contante
    saldo_cassa = sum(d["importo"] if d["tipo"] == "entrata" else -d["importo"] for d in cassa)
    assert saldo_cassa == 600.0

    assert res["prima_nota_cassa_id"] == entrata_cassa["id"]
    assert res["prima_nota_banca_id"] == entrata_banca["id"]


def test_create_prima_nota_movements_legge_pagato_pos_oltre_a_pagato_elettronico():
    db = _FakeDb()
    corr = _corrispettivo(pagato_elettronico=None)
    corr["pagato_pos"] = 250.0
    corr["pagato_contanti"] = 750.0

    _run(helpers_mod._create_prima_nota_movements(db, corr))

    banca = db.collections["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["importo"] == 250.0


def test_create_prima_nota_movements_nessun_elettronico_nessuna_riga_banca():
    db = _FakeDb()
    corr = _corrispettivo(pagato_contanti=1000.0, pagato_elettronico=0.0)

    _run(helpers_mod._create_prima_nota_movements(db, corr))

    assert db["prima_nota_banca"].docs == []
    cassa = db.collections["prima_nota_cassa"].docs
    assert len(cassa) == 1  # solo l'entrata, nessuna uscita POS
    assert cassa[0]["importo"] == 1000.0


# ---------- percorso 2: sincronizzazione scheduler (prima_nota_module/sync.py) ----------

def _patch_db(monkeypatch, db):
    monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: db))


def test_sync_corrispettivi_impl_crea_anche_la_riga_banca(monkeypatch):
    db = _FakeDb()
    db["corrispettivi"].docs = [_corrispettivo()]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod._sync_corrispettivi_impl(anno=None))

    assert res["inseriti"] == 1
    banca = db.collections["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["importo"] == 400.0
    assert banca[0]["source"] == "corrispettivo_pos"


def test_sync_corrispettivi_impl_non_duplica_se_gia_caricato_dal_percorso_diretto(monkeypatch):
    db = _FakeDb()
    corr = _corrispettivo()
    db["corrispettivi"].docs = [corr]
    _patch_db(monkeypatch, db)

    # Il corrispettivo è già stato processato dal caricamento diretto
    _run(helpers_mod._create_prima_nota_movements(db, corr))
    banca_prima = len(db.collections["prima_nota_banca"].docs)
    cassa_prima = len(db.collections["prima_nota_cassa"].docs)

    # La sincronizzazione periodica non deve aggiungere altro
    res = _run(sync_mod._sync_corrispettivi_impl(anno=None))

    assert res["duplicati"] == 1
    assert res["inseriti"] == 0
    assert len(db.collections["prima_nota_banca"].docs) == banca_prima
    assert len(db.collections["prima_nota_cassa"].docs) == cassa_prima


def test_sync_corrispettivi_impl_idempotente_su_doppia_esecuzione(monkeypatch):
    db = _FakeDb()
    db["corrispettivi"].docs = [_corrispettivo()]
    _patch_db(monkeypatch, db)

    _run(sync_mod._sync_corrispettivi_impl(anno=None))
    res2 = _run(sync_mod._sync_corrispettivi_impl(anno=None))

    assert res2["inseriti"] == 0
    assert res2["duplicati"] == 1
    assert len(db.collections["prima_nota_banca"].docs) == 1
