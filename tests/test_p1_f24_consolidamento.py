"""P1 §5.1 — Consolidamento F24 nella collezione canonica f24_unificato:
chiave naturale di deduplica stabile tra schemi diversi + salva_f24 idempotente."""
import asyncio

from app.services.f24_canonico import chiave_f24, salva_f24, COLL


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return


class _Db:
    def __init__(self):
        self.c = _Coll()

    def __getitem__(self, name):
        assert name == COLL
        return self.c


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_chiave_stabile_tra_schemi_diversi():
    # stesso F24 espresso con schemi diversi -> stessa chiave naturale
    manuale = {"codice_fiscale": "RSSMRA80A01H501U", "scadenza": "2026-07-16",
               "saldo_finale": 1234.5, "protocollo": "P123"}
    parsato = {"dati_generali": {"codice_fiscale": "rssmra80a01h501u",
                                 "data_versamento": "2026-07-16"},
               "totali": {"saldo_netto": 1234.50}, "protocollo": "P123"}
    assert chiave_f24(manuale) == chiave_f24(parsato)


def test_chiave_diversa_per_f24_diversi():
    a = {"codice_fiscale": "CF1", "scadenza": "2026-07-16", "saldo": 100}
    assert chiave_f24(a) != chiave_f24({**a, "saldo": 200})
    assert chiave_f24(a) != chiave_f24({**a, "scadenza": "2026-08-16"})
    assert chiave_f24(a) != chiave_f24({**a, "codice_fiscale": "CF2"})


def test_salva_f24_idempotente():
    db = _Db()
    doc = {"codice_fiscale": "CF1", "scadenza": "2026-07-16", "saldo": 100, "status": "da_pagare"}
    id1 = _run(salva_f24(db, doc, source="test"))
    id2 = _run(salva_f24(db, dict(doc, status="pagato"), source="test"))  # stesso F24, aggiornato
    assert id1 == id2               # stesso documento, non duplicato
    assert len(db.c.docs) == 1      # una sola riga
    assert db.c.docs[0]["status"] == "pagato"   # update applicato
    assert db.c.docs[0]["f24_dedup_key"].startswith("f24_")
