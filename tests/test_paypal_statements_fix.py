"""Copertura per i 2 fix isolati dell'operazione 14 (piano residuo,
audit 14/07/2026): il mapping fornitore PayPal leggeva da una collection
mai scritta (paypal_mapping_fornitori) e il KPI dashboard ignorava il
flag di riconciliazione scritto dal percorso API (riconciliato_con_estratto_banca)."""
import asyncio

import pytest

from app.routers import paypal_statements as mod


def _matches(doc, query):
    if not query:
        return True
    if "$and" in query:
        return all(_matches(doc, q) for q in query["$and"])
    if "$or" in query:
        return any(_matches(doc, q) for q in query["$or"])
    return all(doc.get(k) == v for k, v in query.items())


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return {k2: v for k2, v in d.items() if k2 != "_id"}
        return None

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _matches(d, query))

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        return _FakeCursor([])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def skip(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)

    def __aiter__(self):
        return _aiter(self._docs)


async def _aiter(items):
    for i in items:
        yield i


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


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))


def test_dettaglio_transazione_legge_mapping_da_fornitori_non_da_collection_morta(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [{
        "transaction_id": "TX1", "paypal_account_id": "ACC-1",
        "importo": 100.0, "nome_controparte": "Fornitore Test",
    }]
    db["fornitori"].docs = [{
        "id": "f1", "paypal_account_id": "ACC-1",
        "nome": "Fornitore Test Srl", "piva": "IT12345678901",
    }]
    # La collection legacy morta esiste ma NON deve essere quella letta.
    db["paypal_mapping_fornitori"].docs = [{
        "paypal_account_id": "ACC-1", "fornitore_piva": "PIVA-SBAGLIATA",
    }]
    _patch_db(monkeypatch, db)

    res = _run(mod.dettaglio_transazione_paypal("TX1"))

    assert res["mapping_fornitore"] is not None
    assert res["mapping_fornitore"]["fornitore_piva"] == "IT12345678901"
    assert res["mapping_fornitore"]["fornitore_nome"] == "Fornitore Test Srl"


def test_dettaglio_transazione_nessun_mapping_se_fornitore_non_agganciato(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [{"transaction_id": "TX2", "paypal_account_id": "ACC-2"}]
    _patch_db(monkeypatch, db)

    res = _run(mod.dettaglio_transazione_paypal("TX2"))

    assert res["mapping_fornitore"] is None


def test_dashboard_conta_riconciliati_sia_da_statement_che_da_api(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [
        {"id": "1", "lordo": 10.0, "tipo": "pagamento_web", "riconciliato_banca": True},
        {"id": "2", "lordo": 20.0, "tipo": "pagamento_web", "riconciliato_con_estratto_banca": True},
        {"id": "3", "lordo": 30.0, "tipo": "pagamento_web"},
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.paypal_dashboard(anno=None))

    assert res["riconciliati_banca"] == 2
