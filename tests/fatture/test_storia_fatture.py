"""Storia fattura: lo stato derivato sopravvive all'azzeramento e viene
riapplicato al reimport, riconoscendo la fattura per invoice_key."""
import asyncio

from app.services import storia_fatture as sf


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
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$push", {}).items():
                    d.setdefault(k, []).append(v)
                return


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_snapshot_sopravvive_e_ripristina():
    db = _Db()
    # Fattura con stato derivato (pagata, IVA attribuita, centro di costo)
    fattura = {
        "id": "F1", "invoice_key": "K-123", "invoice_number": "12",
        "supplier_vat": "IT01", "invoice_date": "2026-03-10", "total_amount": 100,
        "stato_pagamento": "pagata", "metodo_pagamento": "banca",
        "periodo_iva_attribuito": "2026-03", "iva_utilizzata": True,
        "centro_costo": "CDC-02", "riconciliato": True,
    }
    # 1) Snapshot prima dell'azzeramento
    _run(sf.registra_snapshot(db, fattura, tipo="pre_azzeramento"))
    st = _run(sf.storia(db, "K-123"))
    assert st and st["stato_corrente"]["stato_pagamento"] == "pagata"
    assert st["operazioni"][0]["tipo"] == "pre_azzeramento"

    # 2) Azzeramento: la storia NON è in `invoices`, quindi sopravvive
    db.colls["invoices"] = _Coll()  # svuota
    assert _run(sf.storia(db, "K-123")) is not None

    # 3) Reimport della STESSA fattura (solo dati XML grezzi, senza stato derivato)
    reimport = {
        "id": "F1-NEW", "invoice_key": "K-123", "invoice_number": "12",
        "supplier_vat": "IT01", "invoice_date": "2026-03-10", "total_amount": 100,
        "status": "imported",
    }
    db["invoices"].docs.append(dict(reimport))
    patch = _run(sf.ripristina_stato(db, reimport))

    # Lo stato derivato è stato riapplicato alla fattura reimportata
    assert patch.get("stato_pagamento") == "pagata"
    assert patch.get("periodo_iva_attribuito") == "2026-03"
    assert patch.get("centro_costo") == "CDC-02"
    salvata = _run(db["invoices"].find_one({"id": "F1-NEW"}))
    assert salvata["stato_pagamento"] == "pagata"
    assert salvata["iva_utilizzata"] is True
    # È stato aggiunto l'evento "reimportata" allo storico
    st2 = _run(sf.storia(db, "K-123"))
    assert any(o["tipo"] == "reimportata" for o in st2["operazioni"])


def test_prima_importazione_apre_lo_storico():
    db = _Db()
    f = {"id": "X", "invoice_key": "NEW-1", "invoice_number": "1",
         "supplier_vat": "IT9", "invoice_date": "2026-01-01", "total_amount": 5}
    patch = _run(sf.ripristina_stato(db, f))
    assert patch == {}  # niente da ripristinare
    st = _run(sf.storia(db, "NEW-1"))
    assert st and st["operazioni"][0]["tipo"] == "importata"
