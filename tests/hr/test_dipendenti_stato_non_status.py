"""TFR e API esterna contano gli attivi usando il campo canonico `stato`.

La regressione resta coperta sulle funzioni effettivamente chiamate. Il vecchio
report PDF non montato e il test del suo solo database finto sono stati rimossi.
"""
import asyncio

from app.routers import tfr as mod_tfr
from app.routers import external_api_v1 as mod_public


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    async def count_documents(self, query=None, *a, **k):
        return len([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        return _FakeCursor([])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


_DIPENDENTI_REALI = [
    {"id": "d1", "nome_completo": "Mario Rossi", "stato": "attivo", "tfr_maturato": 100.0},
    {"id": "d2", "nome_completo": "Anna Bianchi", "stato": "inattivo", "tfr_maturato": 50.0},
    {"id": "d3", "nome_completo": "Luca Verdi", "stato": "attivo", "tfr_accantonato": 200.0},
]


def test_tfr_riepilogo_conta_i_dipendenti_attivi_veri(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod_tfr.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = list(_DIPENDENTI_REALI)
    db["tfr_accantonamenti"].docs = []
    db["tfr_liquidazioni"].docs = []

    esito = _run(mod_tfr.get_riepilogo_tfr_aziendale(anno=2026))

    assert esito["num_dipendenti_attivi"] == 2
    assert esito["totale_fondo_tfr"] == 300.0


def test_api_esterna_conta_dipendenti_attivi_veri(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod_public.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = list(_DIPENDENTI_REALI)
    db["invoices"].docs = []
    db["fatture_emesse"].docs = []
    db["prima_nota_cassa"].docs = []

    esito = _run(mod_public.api_v1_stats(anno=2026, _client={}))

    assert esito["dipendenti_attivi"] == 2
