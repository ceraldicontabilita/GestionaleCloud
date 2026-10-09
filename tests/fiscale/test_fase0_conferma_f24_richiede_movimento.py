"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 5): conferma_f24_batch non deve
più poter marcare un F24 pagato/riconciliato senza un movimento bancario
reale in estratto_conto_movimenti.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.operazioni_module import smart as mod
from app.routers.operazioni_module.common import ConfermaBatchRequest


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items() if not isinstance(v2, dict)):
                return dict(d)
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if d.get("id") == query.get("id"):
                d.update(update.get("$set", {}))

                class _R:
                    matched_count = 1

                return _R()

        class _R0:
            matched_count = 0

        return _R0()

    def find(self, query=None, projection=None, *a, **k):
        query = query or {}
        ids = None
        if "id" in query and isinstance(query["id"], dict) and "$in" in query["id"]:
            ids = set(query["id"]["$in"])
        matched = [d for d in self.docs if ids is None or d.get("id") in ids]
        return _FakeCursor(matched)


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


def test_conferma_f24_senza_movimento_id_rifiutata(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["f24_unificato"].docs = [{"id": "f24-1", "riconciliato": False}]

    request = ConfermaBatchRequest(operazioni=[{"operazione_id": "f24-1", "metodo_pagamento": "banca"}])

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.conferma_f24_batch(request))

    assert exc_info.value.status_code == 409
    assert db["f24_unificato"].docs[0]["riconciliato"] is False


def test_conferma_f24_con_movimento_inesistente_rifiutata(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["f24_unificato"].docs = [{"id": "f24-1", "riconciliato": False}]
    db["estratto_conto_movimenti"].docs = []  # nessun movimento reale

    request = ConfermaBatchRequest(operazioni=[{
        "operazione_id": "f24-1", "metodo_pagamento": "banca", "movimento_id": "EC-fantasma",
    }])

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.conferma_f24_batch(request))

    assert exc_info.value.status_code == 409
    assert db["f24_unificato"].docs[0]["riconciliato"] is False


def test_conferma_f24_con_movimento_reale_va_a_buon_fine(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["f24_unificato"].docs = [{"id": "f24-1", "riconciliato": False}]
    db["estratto_conto_movimenti"].docs = [{"id": "EC-1", "importo": 100.0}]

    request = ConfermaBatchRequest(operazioni=[{
        "operazione_id": "f24-1", "metodo_pagamento": "banca", "movimento_id": "EC-1",
    }])

    res = _run(mod.conferma_f24_batch(request))

    assert res["confermati"] == 1
    assert res["errori"] == []
    assert db["f24_unificato"].docs[0]["riconciliato"] is True
    assert db["f24_unificato"].docs[0]["movimento_bancario_id"] == "EC-1"
