"""P1 §10 — Scenari IVA aggiuntivi richiesti dal prompt (il modulo IVA è maturo,
si aggiungono SOLO i test mancanti): più aliquote, IVA parzialmente indetraibile,
recupero annuale, concorrenza di due richieste di conferma.

(Note credito / fattura annullata / rettifica dopo conferma sono già coperti in
tests/test_liquidazione_iva_engine.py.)"""
import asyncio

import pytest

from app.engines import liquidazione_iva_engine as liq
from app.engines import riepilogo_iva_engine as rip
from app.routers import iva as iva_router
from app.database import Database


def _fatt(**kw):
    base = {"id": "f", "iva_detraibile": 100.0, "iva_utilizzata": False,
            "periodo_iva_attribuito": "2026-01", "stato_detrazione_iva": "DA_INSERIRE"}
    base.update(kw)
    return base


# ─── 1. Più aliquote nella stessa liquidazione ──────────────────────────────

def test_piu_aliquote_sommano_correttamente():
    # imponibili diversi con aliquote 4% / 10% / 22% → l'IVA detraibile è già
    # calcolata per riga; la liquidazione somma gli importi IVA, non le aliquote.
    fatture = [
        _fatt(id="a4", iva_detraibile=4.0),    # 100 @ 4%
        _fatt(id="b10", iva_detraibile=10.0),  # 100 @ 10%
        _fatt(id="c22", iva_detraibile=22.0),  # 100 @ 22%
    ]
    incl, escl = liq.seleziona_fatture_per_liquidazione(fatture, "2026-01")
    assert len(incl) == 3 and escl == []
    t = liq.calcola_totali(incl, iva_vendite=0)
    assert t["iva_acquisti"] == 36.0  # 4 + 10 + 22


# ─── 2. IVA parzialmente indetraibile ───────────────────────────────────────

def test_iva_parzialmente_indetraibile_usa_quota_detraibile():
    # fattura con IVA 22 ma detraibile solo 11 (es. 50% pro-rata / auto):
    # la liquidazione deve usare la QUOTA detraibile, non l'IVA totale.
    f = _fatt(id="p", iva=22.0, iva_detraibile=11.0)
    assert liq._iva_detraibile(f) == 11.0
    incl, escl = liq.seleziona_fatture_per_liquidazione([f], "2026-01")
    assert len(incl) == 1
    t = liq.calcola_totali(incl, iva_vendite=0)
    assert t["iva_acquisti"] == 11.0  # non 22

    # quota detraibile nulla → esclusa (indetraibile al 100%)
    f0 = _fatt(id="q", iva=22.0, iva_detraibile=0.0)
    incl0, escl0 = liq.seleziona_fatture_per_liquidazione([f0], "2026-01")
    assert incl0 == [] and escl0[0]["id"] == "q"


# ─── 3. Recupero annuale ────────────────────────────────────────────────────

def test_recupero_annuale_categoria_dedicata():
    fatture = [
        _fatt(id="rec", iva_detraibile=50.0,
              stato_detrazione_iva="RECUPERATA_IN_DICHIARAZIONE_ANNUALE"),
        _fatt(id="norm", iva_detraibile=30.0, stato_detrazione_iva="DA_INSERIRE"),
    ]
    cat = rip.riepilogo_categorie(fatture)
    assert cat["recuperata_annualmente"]["iva"] == 50.0
    assert cat["recuperata_annualmente"]["conteggio"] == 1
    # la quota recuperata annualmente concorre al "disponibile"
    assert cat["disponibile"]["iva"] == 80.0  # 50 recuperata + 30 non utilizzata


# ─── 4. Concorrenza di due richieste di conferma ────────────────────────────

def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif doc.get(k) != v:
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
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None, sort=None):
        items = [d for d in self.docs if _match(d, query)]
        return dict(items[0]) if items else None

    def find(self, query, proj=None):
        return _Cur([dict(d) for d in self.docs if _match(d, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        n = 0
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                n = 1
                break

        class _R:
            modified_count = n
        return _R()

    async def replace_one(self, query, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                self.docs[i] = dict(doc)
                return
        if upsert:
            self.docs.append(dict(doc))


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


def test_due_conferme_marcano_iva_una_sola_volta(monkeypatch):
    from fastapi import HTTPException
    d = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: d))
    d["invoices"].docs.append({"id": "a", "iva_detraibile": 100.0, "iva_utilizzata": False,
                               "periodo_iva_attribuito": "2026-01",
                               "stato_detrazione_iva": "DA_INSERIRE"})

    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    liq_id = calc["liquidazione"]["id"]

    # prima conferma: OK
    _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    # seconda conferma ("concorrente"): deve fallire con 409, NON ri-marcare l'IVA
    with pytest.raises(HTTPException) as ei:
        _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    assert ei.value.status_code == 409

    # invariante: un solo movimento di UTILIZZO, IVA marcata una sola volta
    utilizzi = [m for m in d["movimenti_iva_fattura"].docs if m.get("tipo_movimento") == "UTILIZZO"]
    assert len(utilizzi) == 1
    assert d["invoices"].docs[0]["iva_utilizzata"] is True
