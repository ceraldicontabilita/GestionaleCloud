"""Bug 14/07/2026 (stessa classe già corretta in prima_nota_module/sync.py):
altri due percorsi che registrano un pagamento fattura in Prima Nota
scrivevano sempre tipo="uscita"/categoria="Fatture", ignorando
tipo_documento — una nota di credito fornitore (TD04/TD08) risultava una
fattura in uscita invece di un'entrata "Nota credito fornitore" (segno +).
Copre multi_pagamento.registra_pagamento e dati_provvisori_service.conferma_proposta."""
import asyncio

from app.routers import multi_pagamento as mp_mod
from app.services import dati_provvisori_service as dp_mod


def _matches(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_matches(doc, q) for q in query["$or"])
    out = True
    for k, v in query.items():
        if k == "$or":
            continue
        if isinstance(v, dict) and "$nin" in v:
            out = out and (doc.get(k) not in v["$nin"])
        elif isinstance(v, dict) and "$gte" in v:
            out = out and (str(doc.get(k, "")) >= v["$gte"])
        elif isinstance(v, dict) and "$lte" in v:
            out = out and (str(doc.get(k, "")) <= v["$lte"])
        else:
            out = out and doc.get(k) == v
    return out


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                for op in ("$addToSet",):
                    for kk, vv in update.get(op, {}).items():
                        d.setdefault(kk, [])
                        if vv not in d[kk]:
                            d[kk].append(vv)
                return

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


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


def _fattura(**over):
    base = {
        "id": "fatt-1", "invoice_number": "4", "invoice_date": "2026-06-05",
        "supplier_name": "RONDINELLA MARKET S.R.L.", "total_amount": 58.0,
        "tipo_documento": "TD01",
    }
    base.update(over)
    return base


def test_multi_pagamento_nota_credito_entrata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD04")]
    monkeypatch.setattr(mp_mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(mp_mod.registra_pagamento({
        "fattura_id": "fatt-1", "importo": 58.0, "metodo": "bonifico", "data": "2026-06-10",
    }))

    assert res["success"] is True
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["categoria"] == "Nota credito fornitore"
    assert banca[0]["importo"] == 58.0
    assert banca[0]["numero_fattura"] == "4"


def test_multi_pagamento_fattura_normale_resta_uscita(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD01")]
    monkeypatch.setattr(mp_mod.Database, "get_db", staticmethod(lambda: db))

    _run(mp_mod.registra_pagamento({
        "fattura_id": "fatt-1", "importo": 58.0, "metodo": "bonifico", "data": "2026-06-10",
    }))

    banca = db["prima_nota_banca"].docs
    assert banca[0]["tipo"] == "uscita"
    assert banca[0]["categoria"] == "Pagamento fornitore"


def test_conferma_proposta_nota_credito_entrata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD08")]
    db["dati_provvisori"].docs = [{
        "id": "prop-1", "stato": "proposta", "fattura_id": "fatt-1",
        "fattura_importo": 58.0, "fattura_fornitore": "RONDINELLA MARKET S.R.L.",
        "fattura_numero": "4", "movimento_data": "10/06/2026", "movimento_id": "mov-1",
    }]

    res = _run(dp_mod.conferma_proposta(db, "prop-1"))

    assert res["success"] is True
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["categoria"] == "Nota credito fornitore"
    assert banca[0]["numero_fattura"] == "4"


def test_conferma_proposta_fattura_normale_resta_uscita(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD01")]
    db["dati_provvisori"].docs = [{
        "id": "prop-2", "stato": "proposta", "fattura_id": "fatt-1",
        "fattura_importo": 58.0, "fattura_fornitore": "RONDINELLA MARKET S.R.L.",
        "fattura_numero": "4", "movimento_data": "10/06/2026", "movimento_id": "mov-1",
    }]

    _run(dp_mod.conferma_proposta(db, "prop-2"))

    banca = db["prima_nota_banca"].docs
    assert banca[0]["tipo"] == "uscita"
    assert banca[0]["categoria"] == "Pagamento fornitore"
