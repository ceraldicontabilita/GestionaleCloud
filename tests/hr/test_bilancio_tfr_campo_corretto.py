"""Bug trovato nell'audit funzionale del 15/07/2026: il Conto Economico
dettagliato (B9c_tfr) sommava il campo "tfr" sui documenti di `cedolini`,
ma quel campo non esiste mai — il campo reale scritto da
salari_unificati_v2.py è "tfr_mese" (stesso nome già usato correttamente in
piano_conti.py). La somma dava quindi sempre 0, e il codice cadeva
sistematicamente sulla stima forfettaria (lordo*6.91%) invece di usare il
TFR realmente accantonato dai cedolini."""
import asyncio

from app.routers.accounting import bilancio as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match_doc(doc, match):
    for k, v in match.items():
        if k == "$or":
            if not any(_match_doc(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        elif isinstance(v, dict) and "$gte" in v and "$lte" in v:
            val = doc.get(k) or ""
            if not (v["$gte"] <= val <= v["$lte"]):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


def _eval_sum_expr(doc, expr):
    if isinstance(expr, (int, float)):
        return expr
    if isinstance(expr, dict) and "$ifNull" in expr:
        field_ref, default = expr["$ifNull"]
        field = field_ref.lstrip("$")
        val = doc.get(field)
        return val if val not in (None, "") else default
    return 0


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _match_doc(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match_doc(d, query):
                return dict(d)
        return None

    async def count_documents(self, query=None, *a, **k):
        return len([d for d in self.docs if _match_doc(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        matched = self.docs
        group_stage = None
        for stage in pipeline:
            if "$match" in stage:
                matched = [d for d in matched if _match_doc(d, stage["$match"])]
            elif "$group" in stage:
                group_stage = stage["$group"]
        if group_stage is None:
            return _FakeCursor(matched)
        result = {}
        for key, expr in group_stage.items():
            if key == "_id":
                continue
            if expr == {"$sum": 1}:
                result[key] = len(matched)
            elif isinstance(expr, dict) and "$sum" in expr:
                result[key] = sum(_eval_sum_expr(d, expr["$sum"]) for d in matched)
        return _FakeCursor([result] if matched else [])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_b9c_tfr_usa_il_campo_reale_non_la_stima(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cedolini"].docs = [
        {"anno": 2026, "lordo": 2000.0, "netto": 1500.0, "tfr_mese": 137.0,
         "inps_dipendente": 0, "inps_azienda": 500.0, "inail": 20.0,
         "costo_azienda": 0, "irpef": 0},
    ]
    db["corrispettivi"].docs = []
    db[mod.Collections.INVOICES].docs = []

    esito = _run(mod.get_conto_economico_dettagliato(anno=2026, mese=None))

    costo_personale = esito["B_COSTI_PRODUZIONE"]["B9_costo_personale"]
    assert costo_personale["B9c_tfr"] == 137.0
