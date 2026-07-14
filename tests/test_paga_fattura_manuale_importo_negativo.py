"""Bug 14/07/2026 segnalato dall'utente (errore 400 su una fattura "BOLLETTE..."
con importo negativo, dallo screenshot dell'Estratto Fatture): paga_fattura_manuale
bloccava con "fattura_id e importo sono obbligatori" qualunque importo <= 0,
anche quando l'importo negativo è un dato legittimo (rettifica di credito
fornitore arrivata con tipo_documento ancora TD01). Inoltre il movimento
Prima Nota era sempre hardcoded tipo="uscita"/categoria="fornitori",
indipendentemente dal segno — stessa classe di bug della nota di credito
già corretta altrove in questa sessione."""
import asyncio

from app.routers.fatture_module import pagamento as mod


def _matches(doc, query):
    if not query:
        return True
    return all(doc.get(k) == v for k, v in query.items())


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return


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


def _payload(**over):
    base = {
        "fattura_id": "fatt-1", "importo": -516.0, "metodo": "banca",
        "data_pagamento": "2026-07-14", "fornitore": "ABC - ACQUA BENE COMUNE NAPOLI A.S.",
        "numero_fattura": "BOLLETTE202100666716",
    }
    base.update(over)
    return base


def test_importo_negativo_non_solleva_400(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [{"id": "fatt-1", "tipo_documento": "TD01"}]

    res = _run(mod.paga_fattura_manuale(_payload()))

    assert res["success"] is True
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["categoria"] == "Nota credito fornitore"
    assert banca[0]["importo"] == 516.0  # sempre positivo, segno nel campo "tipo"


def test_importo_positivo_resta_uscita_normale(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [{"id": "fatt-1", "tipo_documento": "TD01"}]

    res = _run(mod.paga_fattura_manuale(_payload(importo=100.0)))

    assert res["success"] is True
    banca = db["prima_nota_banca"].docs
    assert banca[0]["tipo"] == "uscita"
    assert banca[0]["categoria"] == "Pagamento fornitore"
    assert banca[0]["importo"] == 100.0


def test_importo_zero_resta_bloccato(monkeypatch):
    from fastapi import HTTPException
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    try:
        _run(mod.paga_fattura_manuale(_payload(importo=0)))
        assert False, "doveva sollevare HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
