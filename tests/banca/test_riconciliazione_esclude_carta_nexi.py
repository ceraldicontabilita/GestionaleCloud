"""Regressione 18/07/2026: dopo l'import del primo estratto Nexi reale, le
singole operazioni carta (tipo="carta_credito") comparivano nella coda
"movimenti bancari da riconciliare" — non sono movimenti bancari singoli
da agganciare a una fattura, si riconciliano in blocco con lo statement
Nexi (app/services/nexi_carta.py). Verificato dall'utente su prod: il tab
Banca di Riconciliazione mostrava "Amzn Mktp It...", "PaypalSpotify..."
come movimenti "Da riconciliare"."""
import asyncio

from app.routers.operazioni_module.smart import banca_veloce, ESCLUDI_CARTA_CREDITO
from app.services.riconciliazione_smart import analizza_estratto_conto_batch


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _match(doc, cond):
    for k, v in (cond or {}).items():
        if isinstance(v, dict):
            val = doc.get(k)
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$regex" in v and not str(val or "").startswith(v["$regex"].lstrip("^")):
                return False
            if "$nin" in v and val in v["$nin"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return self._docs


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, q=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def count_documents(self, q):
        return len([d for d in self.docs if _match(d, q)])

    async def distinct(self, field, q=None):
        return list({d[field] for d in self.docs if field in d and _match(d, q)})


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())

    def __getattr__(self, name):
        return self[name]


MOVIMENTI = [
    {"id": "b1", "data": "2026-04-05", "tipo": "uscita", "importo": 1200.0,
     "descrizione": "BONIFICO FORNITORE X", "riconciliato": False},
    {"id": "c1", "data": "2026-01-10", "tipo": "carta_credito", "banca": "Nexi",
     "importo": 82.61, "descrizione": "AMZN MKTP IT", "riconciliato": False},
    {"id": "c2", "data": "2026-01-12", "tipo": "carta_credito", "banca": "Nexi",
     "importo": 20.99, "descrizione": "PAYPALSPOTIFY", "riconciliato": False},
]


def test_banca_veloce_esclude_operazioni_carta():
    assert ESCLUDI_CARTA_CREDITO == {"tipo": {"$ne": "carta_credito"}}


def test_analizza_estratto_conto_batch_esclude_carta(monkeypatch):
    db = _DB()
    db["estratto_conto_movimenti"].docs = list(MOVIMENTI)

    import app.services.riconciliazione_smart as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    async def _fake_arricchisci(db_, movimenti):
        return movimenti

    # Le fasi successive del batch (arricchimento con dipendenti/F24/ecc.)
    # non sono oggetto di questo test: intercettiamo dopo il find dei
    # movimenti verificando solo che i "carta_credito" siano già esclusi.
    orig_find = db["estratto_conto_movimenti"].find
    catturati = {}

    def _spy_find(q=None, proj=None):
        catturati["query"] = q
        return orig_find(q, proj)

    monkeypatch.setattr(db["estratto_conto_movimenti"], "find", _spy_find)

    try:
        _run(analizza_estratto_conto_batch(limit=10, solo_non_riconciliati=True))
    except Exception:
        pass  # il resto della pipeline (dipendenti, F24...) non è mockato qui

    assert catturati["query"].get("tipo") == {"$ne": "carta_credito"}


def test_banca_veloce_non_include_operazioni_carta(monkeypatch):
    db = _DB()
    db["estratto_conto_movimenti"].docs = list(MOVIMENTI)
    db["assegni"].docs = []
    db["invoices"].docs = []

    import app.routers.operazioni_module.smart as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    risultato = _run(banca_veloce(limit=50, solo_non_riconciliati=True, anno=None))
    ids = {m["id"] for m in risultato["movimenti"]}
    assert ids == {"b1"}
    assert risultato["stats"]["non_riconciliati"] == 1
