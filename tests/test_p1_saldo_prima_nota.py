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

    async def find_one(self, query, *a, **k):
        # Lookup del saldo iniziale manuale (16/07/2026): questi test coprono
        # il riporto CALCOLATO, quindi nessun saldo manuale impostato.
        return None

    def aggregate(self, pipeline):
        # emula $match + $group entrate/uscite della pipeline reale,
        # incluso il $convert dell'importo (onError/onNull → 0)
        def _num(d):
            try:
                return float(d.get("importo", 0))
            except (TypeError, ValueError):
                return 0.0
        match = pipeline[0]["$match"]
        docs = [d for d in self.movimenti if _match(d, match)]
        entrate = sum(_num(d) for d in docs if d.get("tipo") == "entrata")
        uscite = sum(_num(d) for d in docs if d.get("tipo") == "uscita")
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
    """Semantica corretta 16/07/2026: l'esclusione è per SOURCE, non più per
    l'intera categoria "Corrispettivi POS" — quella categoria la scrivono sia
    le chiusure di verifica (chiusura_pos_mobile, da escludere) sia l'incasso
    POS reale del corrispettivo XML (corrispettivo_pos, da CONTARE: prima
    veniva buttato via e la banca mostrava solo uscite)."""
    movimenti = [
        {"tipo": "entrata", "importo": 100.0, "data": "2026-03-01", "status": "ok"},
        {"tipo": "entrata", "importo": 999.0, "data": "2026-03-01", "status": "deleted"},
        # Incasso POS reale da corrispettivo XML: CONTA (bug corretto).
        {"tipo": "entrata", "importo": 888.0, "data": "2026-03-01", "status": "ok",
         "categoria": "Corrispettivi POS", "source": "corrispettivo_pos"},
        # Chiusura POS serale di verifica: esclusa (non è un secondo incasso).
        {"tipo": "entrata", "importo": 777.0, "data": "2026-03-01", "status": "ok",
         "categoria": "Corrispettivi POS", "source": "chiusura_pos_mobile"},
        # Copia legacy dell'estratto conto reale: esclusa (duplicherebbe
        # pagamenti fatture e accrediti POS già registrati altrove).
        {"tipo": "entrata", "importo": 666.0, "data": "2026-03-01", "status": "ok",
         "categoria": "Ricavi - Incasso tramite POS", "source": "estratto_conto_sync"},
        # POS_DUPLICATO resta escluso per categoria.
        {"tipo": "entrata", "importo": 555.0, "data": "2026-03-01", "status": "ok",
         "categoria": "POS_DUPLICATO"},
    ]
    db = _Db(_Coll(movimenti))
    query = {"status": {"$nin": ["deleted", "archived"]},
             **common.ESCLUSIONI_PRIMA_NOTA}
    s = _run(common.aggrega_saldo_prima_nota(db, "prima_nota_banca", query, anno=None))
    assert s["saldo"] == 988.0  # 100 + 888; deleted/verifica/legacy-EC/duplicato esclusi


def test_importo_stringa_convertito():
    """§6.4 estratto conto: alcuni doc storici hanno importo come STRINGA.
    Il motore li somma comunque ($convert onError/onNull → 0)."""
    movimenti = [
        {"tipo": "entrata", "importo": "100.50", "data": "2026-03-01"},
        {"tipo": "uscita", "importo": 30.0, "data": "2026-03-02"},
        {"tipo": "entrata", "importo": "non-un-numero", "data": "2026-03-03"},  # → 0
        {"tipo": "entrata", "importo": None, "data": "2026-03-04"},             # → 0
    ]
    db = _Db(_Coll(movimenti))
    s = _run(common.aggrega_saldo_prima_nota(db, "estratto_conto_movimenti", {}, anno=None))
    assert s["totale_entrate"] == 100.50
    assert s["totale_uscite"] == 30.0
    assert s["saldo"] == 70.50


def test_riporto_query_base_esplicita_estratto_conto():
    """§6.4 estratto conto sul motore unico: con query_base_precedente={} il
    riporto considera TUTTI i movimenti prima dell'anno (comportamento storico
    dell'estratto conto, che non ha soft-delete né categorie escluse); con il
    default (None) restano le esclusioni della Prima Nota."""
    movimenti = [
        # anno precedente: uno "deleted" (in EC non esiste, ma verifica la semantica)
        {"tipo": "entrata", "importo": 200.0, "data": "2025-06-01", "status": "deleted"},
        {"tipo": "entrata", "importo": 100.0, "data": "2025-07-01"},
        # anno corrente
        {"tipo": "entrata", "importo": 50.0, "data": "2026-02-01"},
    ]
    db = _Db(_Coll(movimenti))
    query_anno = {"data": {"$gte": "2026-01-01", "$lte": "2026-12-31"}}

    # Semantica estratto conto: riporto su TUTTO (300)
    s_ec = _run(common.aggrega_saldo_prima_nota(
        db, "estratto_conto_movimenti", query_anno, anno=2026, query_base_precedente={}))
    assert s_ec["saldo_precedente"] == 300.0
    assert s_ec["saldo"] == 350.0

    # Semantica Prima Nota (default): il "deleted" resta escluso dal riporto (100)
    s_pn = _run(common.aggrega_saldo_prima_nota(
        db, "prima_nota_banca", query_anno, anno=2026))
    assert s_pn["saldo_precedente"] == 100.0
    assert s_pn["saldo"] == 150.0
