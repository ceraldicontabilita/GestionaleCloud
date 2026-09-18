"""Bug trovato in verifica live 16/07/2026: 11 movimenti banca legacy con
data in formato GG/MM/AAAA. I saldi confrontano le date come stringhe:
"04/02/2026" < "2024-01-01", quindi finivano nel riporto anni precedenti
di ogni anno invece che nel loro anno vero."""
import asyncio

from app.routers.prima_nota_module import manutenzione as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        import re
        rx = (query or {}).get("data", {}).get("$regex")
        out = [d for d in self.docs if rx and re.match(rx, str(d.get("data", "")))]
        return _FakeCursor(out)

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if d.get("id") == query.get("id"):
                d.update(update.get("$set", {}))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_normalizza_date_italiane_in_iso(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_banca"].docs = [
        {"id": "m1", "data": "04/02/2026", "tipo": "uscita", "importo": 100.0},
        {"id": "m2", "data": "2026-02-04", "tipo": "uscita", "importo": 50.0},  # già ISO: intoccato
    ]
    db["prima_nota_cassa"].docs = [
        {"id": "m3", "data": "26/01/2026", "tipo": "entrata", "importo": 70.0},
    ]

    esito = _run(mod.fix_date_formato_italiano())

    assert esito["totale"] == 2
    assert db["prima_nota_banca"].docs[0]["data"] == "2026-02-04"
    assert db["prima_nota_banca"].docs[0]["anno"] == 2026
    assert db["prima_nota_banca"].docs[0]["mese"] == 2
    assert db["prima_nota_banca"].docs[0]["data_originale_malformata"] == "04/02/2026"
    assert db["prima_nota_banca"].docs[1]["data"] == "2026-02-04"  # invariato
    assert "data_originale_malformata" not in db["prima_nota_banca"].docs[1]
    assert db["prima_nota_cassa"].docs[0]["data"] == "2026-01-26"
