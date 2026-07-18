"""REGOLA (utente 18/07/2026): la fattura XML con fornitore a metodo
CASSA (contanti) si registra subito in Prima Nota Cassa; con metodo
BANCA resta PROVVISORIA finche' la riconciliazione (estratto conto /
PayPal / carta) non trova l'addebito reale; misto/senza metodo resta
provvisoria per la divisione manuale."""
import asyncio

from app.routers.invoices import fatture_upload as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict):
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

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
                return


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


FATTURA = {
    "id": "fatt-1", "invoice_number": "77/A", "invoice_date": "2026-06-01",
    "supplier_vat": "01234567890", "supplier_name": "Dolciaria Acquaviva S.p.A.",
    "total_amount": 122.0,
}


def _setup(monkeypatch, metodo):
    db = _Db()
    if metodo is not None:
        db["fornitori"].docs = [{"partita_iva": "01234567890", "metodo_pagamento": metodo}]
    db["invoices"].docs = [dict(FATTURA)]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    # registra_pagamento_fattura usa Database.get_db() suo: monkeypatcho il modulo sync
    from app.routers.prima_nota_module import sync as mod_sync
    monkeypatch.setattr(mod_sync.Database, "get_db", staticmethod(lambda: db))
    return db


def test_fornitore_cassa_registra_subito_in_cassa(monkeypatch):
    db = _setup(monkeypatch, "contanti")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is not None
    assert update["prima_nota_tipo"] == "cassa"
    assert update["pagato"] is True
    assert len(db["prima_nota_cassa"].docs) == 1
    assert db["prima_nota_cassa"].docs[0]["fattura_id"] == "fatt-1"
    assert db["prima_nota_banca"].docs == []
    # persistito anche sulla fattura
    assert db["invoices"].docs[0]["stato_pagamento"] == "pagata"


def test_fornitore_banca_resta_provvisoria_fino_a_riconciliazione(monkeypatch):
    """REGOLA utente 18/07/2026: la fattura 'banca' NON e' pagata solo
    perche' il fornitore ha metodo banca — diventa pagata SOLO quando la
    riconciliazione (estratto conto / PayPal / carta) trova l'addebito
    reale. Fino ad allora resta provvisoria."""
    db = _setup(monkeypatch, "bonifico")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_banca"].docs == []
    assert db["prima_nota_cassa"].docs == []


def test_fornitore_misto_resta_provvisoria(monkeypatch):
    db = _setup(monkeypatch, "misto")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []


def test_fornitore_senza_metodo_resta_provvisoria(monkeypatch):
    db = _setup(monkeypatch, None)

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []


def test_idempotente_su_reimport(monkeypatch):
    db = _setup(monkeypatch, "contanti")

    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert len(db["prima_nota_cassa"].docs) == 1  # mai due movimenti per la stessa fattura
