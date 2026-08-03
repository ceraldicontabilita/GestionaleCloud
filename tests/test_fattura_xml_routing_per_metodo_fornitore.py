"""Regola utente 03/08/2026: cassa e banca instradano subito la fattura
nelle rispettive Prime Note; misto o senza metodo resta provvisoria."""
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
    "total_amount": 122.0, "imponibile": 100.0, "iva": 22.0,
}


def _setup(monkeypatch, metodo, **supplier_extra):
    db = _Db()
    if metodo is not None:
        db["fornitori"].docs = [{
            "partita_iva": "01234567890",
            "metodo_pagamento": metodo,
            **supplier_extra,
        }]
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


def test_fornitore_banca_registra_subito_in_banca(monkeypatch):
    db = _setup(monkeypatch, "bonifico")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is not None
    assert update["prima_nota_tipo"] == "banca"
    assert update["pagato"] is True
    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["fattura_id"] == "fatt-1"
    assert db["prima_nota_cassa"].docs == []
    assert db["invoices"].docs[0]["stato_pagamento"] == "pagata"


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


def test_idempotente_banca_su_reimport(monkeypatch):
    db = _setup(monkeypatch, "banca")

    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert len(db["prima_nota_banca"].docs) == 1


def test_fornitore_escluso_non_entra_in_cassa_banca_ma_mantiene_iva(monkeypatch):
    db = _setup(monkeypatch, "banca", esclude_cassa_banca=True)
    fattura = dict(FATTURA)

    update = _run(mod.auto_registra_prima_nota(db, fattura, None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert fattura["esclusa_da_cassa_banca"] is True
    assert fattura["registrazione_fiscale_mantenuta"] is True
    assert db["invoices"].docs[0]["imponibile"] == 100.0
    assert db["invoices"].docs[0]["iva"] == 22.0


def test_fornitore_cessato_e_automaticamente_escluso_solo_finanziariamente(monkeypatch):
    db = _setup(monkeypatch, "contanti", cessato=True)

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0]["iva"] == 22.0
