"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 8): dedup_fatture_prima_nota con
applica=False non deve MAI scrivere, nemmeno con auto_risolvi_certi=True —
prima "false" cancellava comunque se auto_risolvi_certi era true,
contraddicendo sia il nome del parametro sia l'anteprima promessa dalla UI
(PuliziaPrimaNota.jsx).
"""
import asyncio

from app.routers.prima_nota_module import manutenzione as mod


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor(list(self.docs))

    async def update_many(self, query, update, *a, **k):
        ids = set((query.get("id") or {}).get("$in", []))
        count = 0
        for d in self.docs:
            if d.get("id") in ids:
                d.update(update.get("$set", {}))
                count += 1

        class _R:
            modified_count = count

        return _R()


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


def _duplicati():
    return [
        {"id": "m-1", "operation_hash": "hash-1", "created_at": "2026-01-01T00:00:00Z",
         "status": "attivo", "importo": 100.0, "data": "2026-01-01"},
        {"id": "m-2", "operation_hash": "hash-1", "created_at": "2026-01-02T00:00:00Z",
         "status": "attivo", "importo": 100.0, "data": "2026-01-01"},
    ]


def test_applica_false_e_auto_risolvi_certi_true_non_scrive_nulla(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = _duplicati()

    res = _run(mod.dedup_fatture_prima_nota(applica=False, auto_risolvi_certi=True))

    assert res["cassa"]["movimenti_certi"] == 1  # rilevato, ma non applicato
    for d in db["prima_nota_cassa"].docs:
        assert d["status"] == "attivo"


def test_applica_true_e_auto_risolvi_certi_true_scrive_davvero(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = _duplicati()

    _run(mod.dedup_fatture_prima_nota(applica=True, auto_risolvi_certi=True))

    stati = {d["id"]: d["status"] for d in db["prima_nota_cassa"].docs}
    assert stati["m-1"] == "attivo"  # il più vecchio resta
    assert stati["m-2"] == "deleted"  # il duplicato viene soft-deleted
