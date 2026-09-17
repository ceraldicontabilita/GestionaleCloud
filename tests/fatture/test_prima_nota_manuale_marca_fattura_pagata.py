"""Bug trovato in audit 15/07/2026: registrare a mano in Prima Nota Cassa (o
Banca) il pagamento di una fattura specifica (fattura_id) creava il
movimento ma non aggiornava lo stato della fattura. Una riconciliazione
bancaria successiva trovava ancora la fattura "da pagare" (filtro
pagato != True) e poteva creare un SECONDO movimento reale per lo stesso
pagamento — doppio conteggio della stessa spesa.

create_prima_nota_cassa/banca ora marcano la fattura pagata quando il
movimento è un'uscita collegata a fattura_id, come già fa il flusso
"Paga in Cassa/Banca" (registra_fattura_prima_nota)."""
import asyncio

from app.routers.prima_nota_module import cassa as cassa_mod
from app.routers.prima_nota_module import banca as banca_mod
from app.database import Collections
from fastapi import HTTPException


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))
                return

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return d
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_uscita_cassa_con_fattura_id_marca_fattura_pagata(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(cassa_mod.Database, "get_db", staticmethod(lambda: db))
    db[Collections.INVOICES].docs = [{"id": "fatt-1", "pagato": False}]

    _run(cassa_mod.create_prima_nota_cassa({
        "data": "2026-07-15", "tipo": "uscita", "importo": 100.0,
        "descrizione": "Pagamento fattura fornitore", "fattura_id": "fatt-1",
        "source": "fattura",
    }))

    fattura = db[Collections.INVOICES].docs[0]
    assert fattura["pagato"] is True
    assert fattura["stato_pagamento"] == "pagata"
    assert fattura["metodo_pagamento"] == "cassa"


def test_entrata_cassa_con_fattura_id_non_tocca_la_fattura(monkeypatch):
    # Un'ENTRATA (es. corrispettivo) collegata per errore a un fattura_id non
    # rappresenta un pagamento fornitore: non deve marcare nulla come pagato.
    db = _FakeDb()
    monkeypatch.setattr(cassa_mod.Database, "get_db", staticmethod(lambda: db))
    db[Collections.INVOICES].docs = [{"id": "fatt-1", "pagato": False}]

    _run(cassa_mod.create_prima_nota_cassa({
        "data": "2026-07-15", "tipo": "entrata", "importo": 100.0,
        "descrizione": "Corrispettivo", "fattura_id": "fatt-1",
        "source": "corrispettivo",
    }))

    assert db[Collections.INVOICES].docs[0]["pagato"] is False


def test_uscita_banca_con_fattura_id_marca_fattura_pagata(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(banca_mod.Database, "get_db", staticmethod(lambda: db))
    db[Collections.INVOICES].docs = [{"id": "fatt-2", "pagato": False}]
    db["estratto_conto_movimenti"].docs = [{"id": "ec-2", "tipo": "uscita"}]

    _run(banca_mod.create_prima_nota_banca({
        "data": "2026-07-15", "tipo": "uscita", "importo": 250.0,
        "descrizione": "Bonifico fornitore", "fattura_id": "fatt-2",
        "estratto_conto_id": "ec-2",
    }))

    fattura = db[Collections.INVOICES].docs[0]
    assert fattura["pagato"] is True
    assert fattura["stato_pagamento"] == "pagata"
    assert fattura["metodo_pagamento"] == "banca"


def test_uscita_banca_fattura_senza_estratto_resta_fuori(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(banca_mod.Database, "get_db", staticmethod(lambda: db))
    db[Collections.INVOICES].docs = [{"id": "fatt-3", "pagato": False}]

    try:
        _run(banca_mod.create_prima_nota_banca({
            "data": "2026-07-15", "tipo": "uscita", "importo": 250.0,
            "descrizione": "Bonifico non riscontrato", "fattura_id": "fatt-3",
        }))
        assert False, "doveva richiedere l'evidenza dell'estratto conto"
    except HTTPException as exc:
        assert exc.status_code == 409
    assert db[Collections.INVOICES].docs[0]["pagato"] is False


def test_uscita_cassa_senza_fattura_id_non_tocca_invoices(monkeypatch):
    # Movimento libero (piccola spesa contanti): nessun fattura_id, nessun
    # aggiornamento da fare — deve restare innocuo.
    db = _FakeDb()
    monkeypatch.setattr(cassa_mod.Database, "get_db", staticmethod(lambda: db))

    _run(cassa_mod.create_prima_nota_cassa({
        "data": "2026-07-15", "tipo": "uscita", "importo": 20.0,
        "descrizione": "Caffè ufficio",
    }))

    assert Collections.INVOICES not in db.collections or db[Collections.INVOICES].docs == []
