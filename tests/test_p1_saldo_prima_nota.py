"""P1 §6.4 — Funzione UNICA di saldo Prima Nota (segno, riporto/saldo iniziale,
saldo finale). Test di caratterizzazione: la funzione condivisa riproduce ESATTAMENTE
la formula preesistente (entrate−uscite + riporto anni precedenti)."""
import asyncio

from app.routers.prima_nota_module import common


class _Agg:
    def __init__(self, res):
        self._res = res

    async def to_list(self, n):
        return list(self._res)


class _Coll:
    def __init__(self, movimenti):
        self.movimenti = movimenti

    def aggregate(self, pipeline):
        # emula $match + $group entrate/uscite della pipeline reale
        match = pipeline[0]["$match"]
        docs = [d for d in self.movimenti if _match(d, match)]
        entrate = sum(d.get("importo", 0) for d in docs if d.get("tipo") == "entrata")
        uscite = sum(d.get("importo", 0) for d in docs if d.get("tipo") == "uscita")
        if not docs:
            return _Agg([])
        return _Agg([{"_id": None, "entrate": entrate, "uscite": uscite}])


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict):
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$lt" in v and not (doc.get(k) is not None and doc.get(k) < v["$lt"]):
                return False
            if "$gte" in v and not (doc.get(k) is not None and doc.get(k) >= v["$gte"]):
                return False
            if "$lte" in v and not (doc.get(k) is not None and doc.get(k) <= v["$lte"]):
                return False
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Db:
    def __init__(self, coll):
        self._coll = coll

    def __getitem__(self, name):
        return self._coll


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_saldo_segno_entrate_uscite():
    movimenti = [
        {"tipo": "entrata", "importo": 100.0, "data": "2026-03-01", "status": "ok"},
        {"tipo": "uscita", "importo": 30.0, "data": "2026-03-02", "status": "ok"},
    ]
    db = _Db(_Coll(movimenti))
    query = {"status": {"$nin": ["deleted", "archived"]},
             "categoria": {"$nin": common.CATEGORIE_ESCLUSE}}
    s = _run(common.aggrega_saldo_prima_nota(db, "prima_nota_cassa", query, anno=None))
    assert s["totale_entrate"] == 100.0
    assert s["totale_uscite"] == 30.0
    assert s["saldo_anno"] == 70.0
    assert s["saldo_precedente"] == 0.0
    assert s["saldo"] == 70.0


def test_saldo_con_riporto_anni_precedenti():
    movimenti = [
        # anno precedente (2025): riporto = 200 - 50 = 150
        {"tipo": "entrata", "importo": 200.0, "data": "2025-06-01", "status": "ok"},
        {"tipo": "uscita", "importo": 50.0, "data": "2025-07-01", "status": "ok"},
        # anno corrente (2026)
        {"tipo": "entrata", "importo": 80.0, "data": "2026-02-01", "anno": 2026, "status": "ok"},
    ]
    db = _Db(_Coll(movimenti))
    # query anno 2026 come la costruisce cassa/banca
    query = {
        "status": {"$nin": ["deleted", "archived"]},
        "categoria": {"$nin": common.CATEGORIE_ESCLUSE},
        "$or": [
            {"anno": 2026},
            {"anno": {"$exists": False}, "data": {"$gte": "2026-01-01", "$lte": "2026-12-31"}},
        ],
    }
    s = _run(common.aggrega_saldo_prima_nota(db, "prima_nota_cassa", query, anno=2026))
    assert s["saldo_anno"] == 80.0
    assert s["saldo_precedente"] == 150.0   # riporto 2025
    assert s["saldo"] == 230.0              # 150 + 80


def test_esclusioni_non_contano():
    movimenti = [
        {"tipo": "entrata", "importo": 100.0, "data": "2026-03-01", "status": "ok"},
        {"tipo": "entrata", "importo": 999.0, "data": "2026-03-01", "status": "deleted"},
        {"tipo": "entrata", "importo": 888.0, "data": "2026-03-01", "status": "ok",
         "categoria": "Corrispettivi POS"},
    ]
    db = _Db(_Coll(movimenti))
    query = {"status": {"$nin": ["deleted", "archived"]},
             "categoria": {"$nin": common.CATEGORIE_ESCLUSE}}
    s = _run(common.aggrega_saldo_prima_nota(db, "prima_nota_cassa", query, anno=None))
    assert s["saldo"] == 100.0  # deleted e Corrispettivi POS esclusi
