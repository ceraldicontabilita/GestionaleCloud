"""Un metodo abituale instrada, ma non prova il pagamento della fattura."""
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
        if k == "$and":
            if not all(_match(doc, sub) for sub in v):
                return False
        elif k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict):
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$gte" in v and doc.get(k) < v["$gte"]:
                return False
            if "$lte" in v and doc.get(k) > v["$lte"]:
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

    def find(self, query, *a, **k):
        return _Cursor([dict(d) for d in self.docs if _match(d, query)])


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]


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


def test_fornitore_cassa_resta_provvisoria_senza_prova(monkeypatch):
    db = _setup(monkeypatch, "contanti")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0].get("stato_pagamento") != "pagata"


def test_fornitore_banca_senza_estratto_resta_provvisoria(monkeypatch):
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


def test_reimport_cassa_non_crea_pagamenti(monkeypatch):
    db = _setup(monkeypatch, "contanti")

    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert db["prima_nota_cassa"].docs == []


def test_idempotente_banca_su_reimport(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-1", "tipo": "uscita", "importo": 122.0,
        "data": "2026-06-10",
        "descrizione": "BONIFICO DOLCIARIA ACQUAVIVA FATTURA 77/A",
    }]

    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["estratto_conto_id"] == "ec-1"
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is True


def test_estratto_prima_della_fattura_abbina_solo_uscita_con_identita(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-1", "tipo": "uscita", "importo": -122.0,
        "data": "2026-06-10",
        "descrizione": "SDD DOLCIARIA ACQUAVIVA FATTURA 77/A",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["movimento_bancario_id"] == "ec-1"
    assert update["riconciliato_con_ec"] is True


def test_sdd_importato_prima_della_fattura_si_aggancia_senza_numero_in_causale(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-sdd", "tipo": "uscita", "importo": -122.0,
        "data": "2026-06-10",
        "descrizione_originale": "ADDEBITO DIRETTO SDD DOLCIARIA ACQUAVIVA S.P.A.",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["movimento_bancario_id"] == "ec-sdd"
    assert update["match_tipo"] == "sdd+fornitore+importo+data"
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is True


def test_stesso_importo_accredito_pos_non_paga_fattura(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "pos-1", "tipo": "entrata", "importo": 122.0,
        "data": "2026-06-02", "descrizione": "NUMIA POS",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_banca"].docs == []


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
