"""Bug trovato nell'audit funzionale del 15/07/2026: processa_fatture_pendenti
leggeva le keyword fornitori dalla collection "fornitori_learning", che non
esiste — nessuno scrive mai lì (il nome corretto, usato ovunque nel resto del
codice, è "fornitori_keywords", scritto da app/handlers/fornitore.py). La
classificazione automatica dell'azione batch "classifica" era quindi sempre
un no-op silenzioso: keywords_map restava sempre vuota."""
import asyncio

from app.routers import batch_operations as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeFindCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return _FakeFindCursor(self._docs[:n])

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, *a, **k):
        matched = [d for d in self.docs
                   if not query or d.get("status") in query.get("status", {}).get("$in", [d.get("status")])]
        return _FakeFindCursor(matched)

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))
                return


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_classifica_usa_le_keyword_apprese_reali(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f1", "status": "pending", "supplier_name": "Fastweb Spa", "total_amount": 50.0},
    ]
    db["fornitori_keywords"].docs = [
        {"fornitore_nome": "Fastweb Spa", "keywords": ["fastweb"], "centro_costo_suggerito": "5.2_UTENZE"},
    ]

    esito = _run(mod.processa_fatture_pendenti(limite=100, azioni=["classifica"]))

    assert esito["classificate"] == 1
    assert db["invoices"].docs[0]["centro_costo_id"] == "5.2_UTENZE"


def test_senza_keyword_corrispondenti_non_classifica(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f1", "status": "pending", "supplier_name": "Sconosciuto Srl", "total_amount": 10.0},
    ]
    db["fornitori_keywords"].docs = [
        {"fornitore_nome": "Fastweb Spa", "keywords": ["fastweb"], "centro_costo_suggerito": "5.2_UTENZE"},
    ]

    esito = _run(mod.processa_fatture_pendenti(limite=100, azioni=["classifica"]))

    assert esito["classificate"] == 0
    assert "centro_costo_id" not in db["invoices"].docs[0]
