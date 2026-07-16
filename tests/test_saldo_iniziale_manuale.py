"""Richiesta utente 16/07/2026: il riporto dell'anno (saldo al 1° gennaio,
es. quello che viene dal 2025) deve essere modificabile a mano, perché il
riporto calcolato dai movimenti degli anni precedenti non è affidabile
quando lo storico a sistema è parziale. Se impostato, il saldo iniziale
manuale SOSTITUISCE il riporto calcolato nella funzione unica di saldo."""
import asyncio

from app.routers.prima_nota_module import common, stats as mod_stats


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$lt" in v and not (doc.get(k) is not None and doc.get(k) < v["$lt"]):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Agg:
    def __init__(self, res):
        self._res = res

    async def to_list(self, n):
        return list(self._res)


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def aggregate(self, pipeline):
        match = pipeline[0]["$match"]
        docs = [d for d in self.docs if _match(d, match)]
        if not docs:
            return _Agg([])
        entrate = sum(float(d.get("importo", 0)) for d in docs if d.get("tipo") == "entrata")
        uscite = sum(float(d.get("importo", 0)) for d in docs if d.get("tipo") == "uscita")
        return _Agg([{"_id": None, "entrate": entrate, "uscite": uscite}])

    def find(self, query=None, projection=None, *a, **k):
        return _Agg([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))

    async def delete_one(self, query, *a, **k):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, query)]

        class _R:
            deleted_count = before - len(self.docs)
        return _R()


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


def test_saldo_manuale_sostituisce_riporto_calcolato():
    db = _Db()
    # 2025: movimenti "sporchi" (solo uscite di vecchi backfill) → riporto
    # calcolato sarebbe -500.
    db["prima_nota_banca"].docs = [
        {"tipo": "uscita", "importo": 500.0, "data": "2025-06-01"},
        {"tipo": "entrata", "importo": 100.0, "data": "2026-02-01", "anno": 2026},
    ]
    db[common.COLLECTION_SALDI_INIZIALI].docs = [
        {"id": "s1", "tipo": "banca", "anno": 2026, "importo": 12500.0},
    ]

    s = _run(common.aggrega_saldo_prima_nota(
        db, "prima_nota_banca", {"anno": 2026}, anno=2026))

    assert s["saldo_precedente"] == 12500.0  # manuale, non -500
    assert s["saldo_iniziale_manuale"] is True
    assert s["saldo"] == 12600.0  # 12500 + 100


def test_senza_saldo_manuale_resta_il_riporto_calcolato():
    db = _Db()
    db["prima_nota_banca"].docs = [
        {"tipo": "entrata", "importo": 300.0, "data": "2025-06-01"},
        {"tipo": "entrata", "importo": 100.0, "data": "2026-02-01", "anno": 2026},
    ]

    s = _run(common.aggrega_saldo_prima_nota(
        db, "prima_nota_banca", {"anno": 2026}, anno=2026))

    assert s["saldo_precedente"] == 300.0
    assert s["saldo_iniziale_manuale"] is False
    assert s["saldo"] == 400.0


def test_set_e_update_saldo_iniziale(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_stats.Database, "get_db", staticmethod(lambda: db))

    esito1 = _run(mod_stats.set_saldo_iniziale({"tipo": "cassa", "anno": 2026, "importo": 1500.0}))
    esito2 = _run(mod_stats.set_saldo_iniziale({"tipo": "cassa", "anno": 2026, "importo": 1800.0}))

    assert esito1["id"] == esito2["id"]  # upsert, non duplica
    docs = db[common.COLLECTION_SALDI_INIZIALI].docs
    assert len(docs) == 1
    assert docs[0]["importo"] == 1800.0

    saldi = _run(mod_stats.get_saldi_iniziali(anno=2026))
    assert saldi["cassa"]["importo"] == 1800.0
    assert saldi["banca"] is None


def test_delete_saldo_iniziale_torna_al_calcolato(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_stats.Database, "get_db", staticmethod(lambda: db))
    _run(mod_stats.set_saldo_iniziale({"tipo": "banca", "anno": 2026, "importo": 900.0}))

    _run(mod_stats.delete_saldo_iniziale(tipo="banca", anno=2026))

    assert db[common.COLLECTION_SALDI_INIZIALI].docs == []
