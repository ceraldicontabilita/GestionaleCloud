"""
Liquidazioni IVA mensili persistite (Fase 3, SPECIFICA_IVA.md §10-13).

Due livelli:
  1. Motore puro `liquidazione_iva_engine`: selezione fatture e totali.
  2. Router `iva` (calcola/conferma/riapri/rettifica) su un DB in memoria,
     con focus sull'ANTI-DOPPIA-DETRAZIONE (§11): una fattura confermata in
     gennaio non deve rientrare nel calcolo di febbraio.
"""
import asyncio
import re

import pytest

from app.engines import liquidazione_iva_engine as liq
from app.routers import iva as iva_router
from app.database import Database


# ─── 1. Motore puro ─────────────────────────────────────────────────────────

def _fatt(**kw):
    base = {"id": kw.get("id", "f"), "iva_detraibile": 100.0,
            "iva_utilizzata": False, "periodo_iva_attribuito": "2026-01",
            "stato_detrazione_iva": "DA_INSERIRE"}
    base.update(kw)
    return base


def test_selezione_include_solo_periodo_e_disponibili():
    fatture = [
        _fatt(id="a", periodo_iva_attribuito="2026-01"),
        _fatt(id="b", periodo_iva_attribuito="2026-02"),  # altro periodo → ignorata
        _fatt(id="c", periodo_iva_attribuito="2026-01", iva_utilizzata=True,
              periodo_iva_utilizzato="2026-01"),  # già usata → esclusa
    ]
    incl, escl = liq.seleziona_fatture_per_liquidazione(fatture, "2026-01")
    assert [f["id"] for f in incl] == ["a"]
    assert [e["id"] for e in escl] == ["c"]
    assert "utilizzat" in escl[0]["motivo_esclusione"].lower()


def test_selezione_esclude_note_credito_annullate_e_iva_nulla():
    fatture = [
        _fatt(id="nc", tipo_documento="TD04"),
        _fatt(id="ann", annullata=True),
        _fatt(id="dup", duplicata=True),
        _fatt(id="zero", iva_detraibile=0),
        _fatt(id="ok"),
    ]
    incl, escl = liq.seleziona_fatture_per_liquidazione(fatture, "2026-01")
    assert [f["id"] for f in incl] == ["ok"]
    motivi = {e["id"]: e["motivo_esclusione"] for e in escl}
    assert set(motivi) == {"nc", "ann", "dup", "zero"}


def test_selezione_esclude_stato_non_ammesso():
    fatture = [_fatt(id="x", stato_detrazione_iva="ESCLUSA")]
    incl, escl = liq.seleziona_fatture_per_liquidazione(fatture, "2026-01")
    assert incl == []
    assert escl[0]["id"] == "x"


def test_totali_saldo_debito_e_credito():
    incl = [_fatt(iva_detraibile=200)]
    # vendite 500, acquisti 200, nessun credito precedente → debito 300
    t = liq.calcola_totali(incl, iva_vendite=500, credito_precedente=0)
    assert t["iva_acquisti"] == 200 and t["saldo"] == 300
    assert t["debito_periodo"] == 300 and t["credito_periodo"] == 0
    # vendite 100, acquisti 200 → credito 100
    t2 = liq.calcola_totali(incl, iva_vendite=100)
    assert t2["saldo"] == -100 and t2["credito_periodo"] == 100 and t2["debito_periodo"] == 0


# ─── 2. Router su DB in memoria ─────────────────────────────────────────────

def _match(doc, query):
    for k, cond in query.items():
        val = doc.get(k)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$in" and val not in arg:
                    return False
                if op == "$nin" and val in arg:
                    return False
                if op == "$ne" and val == arg:
                    return False
                if op == "$gt" and not (val is not None and val > arg):
                    return False
                if op == "$regex" and not (val is not None and re.search(arg, str(val))):
                    return False
        else:
            if val != cond:
                return False
    return True


def _apply_sort(items, sort):
    if not sort:
        return items
    if isinstance(sort, tuple):
        sort = [sort]
    for key, direction in reversed(sort):
        items = sorted(items, key=lambda d: (d.get(key) is None, d.get(key)),
                       reverse=(direction < 0))
    return items


class _Cur:
    def __init__(self, items):
        self._items = items

    def sort(self, *a):
        if len(a) == 1:
            self._items = _apply_sort(self._items, a[0])
        elif len(a) == 2:
            self._items = _apply_sort(self._items, [(a[0], a[1])])
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

    def _proj(self, doc, proj):
        d = dict(doc)
        d.pop("_id", None)
        return d

    async def find_one(self, query, proj=None, sort=None):
        items = [d for d in self.docs if _match(d, query)]
        items = _apply_sort(items, sort)
        return self._proj(items[0], proj) if items else None

    def find(self, query, proj=None):
        items = [d for d in self.docs if _match(d, query)]
        return _Cur([self._proj(d, proj) for d in items])

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


@pytest.fixture
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: d))
    return d


def _inv(db, **kw):
    base = {"iva_detraibile": 100.0, "iva_utilizzata": False,
            "periodo_iva_attribuito": "2026-01", "stato_detrazione_iva": "DA_INSERIRE"}
    base.update(kw)
    db["invoices"].docs.append(base)


def test_calcola_crea_bozza_senza_marcare_iva(db):
    _inv(db, id="a", iva_detraibile=220)
    res = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    lq = res["liquidazione"]
    assert lq["stato"] == "CALCOLATA" and lq["iva_acquisti"] == 220
    assert len(lq["fatture_incluse"]) == 1
    # l'IVA NON è ancora utilizzata: la conferma è un passo separato
    assert db["invoices"].docs[0]["iva_utilizzata"] is False


def test_conferma_marca_iva_e_impedisce_doppia_detrazione(db):
    _inv(db, id="a", iva_detraibile=220, periodo_iva_attribuito="2026-01")
    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    liq_id = calc["liquidazione"]["id"]
    conf = _run(iva_router.conferma_liquidazione(liq_id=liq_id, utente="mario"))
    assert conf["fatture_marcate"] == 1
    inv = db["invoices"].docs[0]
    assert inv["iva_utilizzata"] is True
    assert inv["periodo_iva_utilizzato"] == "2026-01"
    assert inv["stato_detrazione_iva"] == "INSERITA_IN_LIQUIDAZIONE"
    assert any(m["tipo_movimento"] == "UTILIZZO" for m in db["movimenti_iva_fattura"].docs)

    # La stessa fattura NON deve entrare nel calcolo di febbraio
    # (caso "ricevuta a febbraio ma già usata a gennaio", §11).
    db["invoices"].docs[0]["periodo_iva_attribuito"] = "2026-02"
    febbraio = _run(iva_router.calcola_liquidazione(periodo="2026-02", iva_vendite=0))
    assert febbraio["liquidazione"]["iva_acquisti"] == 0
    assert len(febbraio["liquidazione"]["fatture_escluse"]) == 1


def test_conferma_bloccata_se_gia_confermata(db):
    from fastapi import HTTPException
    _inv(db, id="a")
    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    liq_id = calc["liquidazione"]["id"]
    _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    with pytest.raises(HTTPException) as ei:
        _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    assert ei.value.status_code == 409


def test_ricalcolo_bloccato_su_confermata(db):
    from fastapi import HTTPException
    _inv(db, id="a")
    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    _run(iva_router.conferma_liquidazione(liq_id=calc["liquidazione"]["id"]))
    with pytest.raises(HTTPException) as ei:
        _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    assert ei.value.status_code == 409


def test_riapri_libera_le_fatture(db):
    _inv(db, id="a", iva_detraibile=150)
    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    liq_id = calc["liquidazione"]["id"]
    _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    ria = _run(iva_router.riapri_liquidazione(liq_id=liq_id, motivo="errore"))
    assert ria["fatture_liberate"] == 1
    inv = db["invoices"].docs[0]
    assert inv["iva_utilizzata"] is False and inv["liquidazione_id"] is None
    assert inv["disponibile_per_nuovo_calcolo"] is True
    # dopo la riapertura si può ricalcolare
    ric = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    assert ric["liquidazione"]["iva_acquisti"] == 150


def test_rettifica_crea_nuova_versione(db):
    _inv(db, id="a", iva_detraibile=100)
    calc = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    liq_id = calc["liquidazione"]["id"]
    _run(iva_router.conferma_liquidazione(liq_id=liq_id))
    ret = _run(iva_router.rettifica_liquidazione(liq_id=liq_id, motivo="correzione", iva_vendite=0))
    assert ret["nuova_liquidazione"]["versione"] > calc["liquidazione"]["versione"]
    vecchia = next(d for d in db["liquidazioni_iva"].docs if d["id"] == liq_id)
    assert vecchia["stato"] == "RETTIFICATA"
    assert ret["nuova_liquidazione"]["iva_acquisti"] == 100


def test_credito_precedente_riportato(db):
    # Gennaio: solo acquisti 100, vendite 0 → credito 100 riportato.
    _inv(db, id="a", iva_detraibile=100, periodo_iva_attribuito="2026-01")
    g = _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    assert g["liquidazione"]["credito_periodo"] == 100
    _run(iva_router.conferma_liquidazione(liq_id=g["liquidazione"]["id"]))
    # Febbraio: vendite 300, acquisti 50, credito precedente 100 → saldo 300-50-100=150
    _inv(db, id="b", iva_detraibile=50, periodo_iva_attribuito="2026-02")
    f = _run(iva_router.calcola_liquidazione(periodo="2026-02", iva_vendite=300))
    assert f["liquidazione"]["credito_precedente"] == 100
    assert f["liquidazione"]["saldo"] == 150


def test_lista_e_periodo(db):
    _inv(db, id="a")
    _run(iva_router.calcola_liquidazione(periodo="2026-01", iva_vendite=0))
    lista = _run(iva_router.lista_liquidazioni(anno=2026, limit=200))
    assert lista["totale"] == 1
    per = _run(iva_router.liquidazione_periodo(periodo="2026-01"))
    assert per["corrente"]["periodo"] == "2026-01"
    assert len(per["versioni"]) == 1
