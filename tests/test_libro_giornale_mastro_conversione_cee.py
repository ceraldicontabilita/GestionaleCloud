"""Regola vincolante CLAUDE.md (utente): il piano dei conti ufficiale è SOLO
il CEE (app/services/piano_conti_ufficiale.py); ogni altro schema (es.
l'operativo interno 05.01.01 di piano_conti) va SEMPRE convertito con
app/services/mapping_piano_conti.py.

Bug trovato nell'audit funzionale del 15/07/2026: Libro Giornale e Libro
Mastro (i due report che il commercialista usa per ricostruire la
contabilità) restituivano solo il codice conto OPERATIVO interno, senza mai
chiamare la conversione ufficiale — violazione diretta della regola.

Il fix AGGIUNGE il conto ufficiale accanto a quello operativo (senza
sostituirlo, serve alla ricostruibilità pari-pari art. 2216 c.c.)."""
import asyncio

from app.routers.accounting import contabilita_gestionale as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeFindCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeAggCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for d in self._docs:
            yield d


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeFindCursor(self.docs)

    def aggregate(self, pipeline, *a, **k):
        # Aggregazione minimale: raggruppa per conto_codice (o conto),
        # sufficiente per verificare l'arricchimento CEE sull'output.
        gruppi = {}
        for doc in self.docs:
            for r in doc.get("righe", []):
                cod = r.get("conto_codice") or r.get("conto")
                g = gruppi.setdefault(cod, {"_id": cod, "conto_nome": r.get("conto_nome"),
                                             "dare": 0.0, "avere": 0.0, "righe": 0})
                g["dare"] += float(r.get("dare") or 0)
                g["avere"] += float(r.get("avere") or 0)
                g["righe"] += 1
        return _FakeAggCursor(list(gruppi.values()))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_libro_giornale_aggiunge_conto_ufficiale_cee(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["movimenti_contabili"].docs = [
        {"data_documento": "2026-05-10", "righe": [
            {"conto_codice": "05.01.01", "conto_nome": "Acquisto merci", "dare": 100.0, "avere": 0.0},
            {"conto_codice": "01.01.02", "conto_nome": "Banca c/c", "dare": 0.0, "avere": 100.0},
        ]},
    ]

    esito = _run(mod.get_libro_giornale(limit=500))

    righe = esito["scritture"][0]["righe"]
    r_costo = next(r for r in righe if r["conto_codice"] == "05.01.01")
    assert r_costo["conto_codice_ufficiale"] == "55.01.07"
    assert r_costo["conto_nome_ufficiale"]

    r_banca = next(r for r in righe if r["conto_codice"] == "01.01.02")
    assert r_banca["conto_codice_ufficiale"] == "19.01.01"


def test_libro_giornale_conto_senza_mapping_resta_none(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["movimenti_contabili"].docs = [
        {"data_documento": "2026-05-10", "righe": [
            {"conto_codice": "99.99.99", "conto_nome": "Sconosciuto", "dare": 5.0, "avere": 0.0},
        ]},
    ]

    esito = _run(mod.get_libro_giornale(limit=500))

    riga = esito["scritture"][0]["righe"][0]
    assert riga["conto_codice_ufficiale"] is None
    assert riga["conto_nome_ufficiale"] is None


def test_libro_mastro_aggiunge_conto_ufficiale_cee(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["movimenti_contabili"].docs = [
        {"data_documento": "2026-05-10", "righe": [
            {"conto_codice": "05.01.01", "conto_nome": "Acquisto merci", "dare": 100.0, "avere": 0.0},
        ]},
    ]

    esito = _run(mod.get_libro_mastro())

    mastrino = next(m for m in esito["mastrini"] if m["conto"] == "05.01.01")
    assert mastrino["conto_ufficiale"] == "55.01.07"
    assert mastrino["conto_ufficiale_nome"]
