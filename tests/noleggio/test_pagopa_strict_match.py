import asyncio

from app.routers.pagopa import cerca_movimento_per_bolletta


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, _value):
        return self

    async def to_list(self, _value):
        return list(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, _query, _projection):
        return _Cursor(self.docs)


class _DB:
    def __init__(self, docs):
        self.estratto_conto_movimenti = _Collection(docs)


def _run(awaitable):
    return asyncio.run(awaitable)


def test_pagopa_richiede_iuv_e_importo_esatto_al_centesimo():
    db = _DB([{"id": "m1", "importo": -859.39}])

    assert _run(cerca_movimento_per_bolletta(db, "IUV123", 859.39))["id"] == "m1"
    assert _run(cerca_movimento_per_bolletta(db, "IUV123", 859.38)) is None
    assert _run(cerca_movimento_per_bolletta(db, "IUV123", None)) is None


def test_pagopa_non_associa_se_due_movimenti_hanno_stessa_prova():
    db = _DB([
        {"id": "m1", "importo": -859.39},
        {"id": "m2", "importo": -859.39},
    ])

    assert _run(cerca_movimento_per_bolletta(db, "IUV123", 859.39)) is None
