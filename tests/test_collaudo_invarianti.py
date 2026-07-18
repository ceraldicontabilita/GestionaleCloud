"""COLLAUDO AUTOMATICO (18/07/2026): il motore esegue i check in sola
lettura, salva il report in collaudo_report e trasforma le violazioni in
alert COLLAUDO_INVARIANTE; un check tornato pulito risolve l'alert."""
import asyncio

import pytest

import app.services.collaudo_invarianti as coll


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return self._docs

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.inserted = []

    def find(self, *a, **k):
        return _Cursor(self.docs)

    async def find_one(self, *a, **k):
        return self.docs[0] if self.docs else None

    async def count_documents(self, *a, **k):
        return len(self.docs)

    def aggregate(self, *a, **k):
        return _Cursor(self.docs)

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_many(self, *a, **k):
        class R:
            modified_count = 0
        return R()


class _Db:
    def __init__(self, colls=None):
        self.colls = colls or {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_check_dangling_e_duplicati():
    db = _Db({
        "estratto_conto_movimenti": _Coll([{"id": "EC1"}]),
        "prima_nota_banca": _Coll([
            {"id": "P1", "estratto_conto_id": "EC1", "data": "2026-01-01", "importo": 10},
            {"id": "P2", "estratto_conto_id": "EC1", "data": "2026-01-02", "importo": 10},   # duplicato
            {"id": "P3", "estratto_conto_id": "EC-FANTASMA", "data": "2026-01-03", "importo": 5},  # dangling
        ]),
    })
    r = _run(coll.check_ec_dangling_e_duplicati(db))
    assert r["violazioni"] == 2
    problemi = {e.get("problema") for e in r["esempi"]}
    assert "estratto_conto_id inesistente" in problemi
    assert "stesso addebito su più righe" in problemi


def test_check_badge_status_conta():
    db = _Db({"documents_inbox": _Coll([{"id": 1}, {"id": 2}])})
    r = _run(coll.check_badge_status(db))
    assert r["violazioni"] == 2


def test_esegui_collaudo_report_e_alert(monkeypatch):
    async def check_sporco(db):
        return {"nome": "sporco", "violazioni": 3, "descrizione": "x", "esempi": []}

    async def check_pulito(db):
        return {"nome": "pulito", "violazioni": 0, "descrizione": "y", "esempi": []}

    monkeypatch.setattr(coll, "CHECKS", [check_sporco, check_pulito])

    generati, risolti = [], []

    async def fake_genera(codice, entita_id, collezione, dettaglio, db, extra=None):
        generati.append((codice, entita_id))

    async def fake_risolvi(codice, entita_id, db, resolved_by="sistema"):
        risolti.append((codice, entita_id))
        return 1

    import app.services.alert_engine as ae
    monkeypatch.setattr(ae, "genera_alert", fake_genera)
    monkeypatch.setattr(ae, "risolvi_alert", fake_risolvi)

    db = _Db()
    report = _run(coll.esegui_collaudo(db))
    assert report["checks_totali"] == 2
    assert report["checks_violati"] == 1
    assert report["violazioni_totali"] == 3
    assert db.colls[coll.COLL_REPORT].inserted, "report non salvato"
    assert generati == [("COLLAUDO_INVARIANTE", "sporco")]
    assert risolti == [("COLLAUDO_INVARIANTE", "pulito")]


def test_check_in_errore_non_ferma_il_giro(monkeypatch):
    async def check_rotto(db):
        raise RuntimeError("boom")

    async def check_ok(db):
        return {"nome": "ok", "violazioni": 0, "descrizione": "y", "esempi": []}

    monkeypatch.setattr(coll, "CHECKS", [check_rotto, check_ok])

    import app.services.alert_engine as ae

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(ae, "genera_alert", _noop)
    monkeypatch.setattr(ae, "risolvi_alert", _noop)

    report = _run(coll.esegui_collaudo(_Db()))
    assert report["checks_in_errore"] == 1
    assert report["checks_totali"] == 2
