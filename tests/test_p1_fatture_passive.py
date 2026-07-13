"""P1 §5.4 — Consolidamento fatture passive su `invoices`: mapping schema legacy
→ canonico, salva idempotente per invoice_key, ponte ERP e crud sulla canonica."""
import asyncio
from pathlib import Path

from app.services.fatture_canonico import (
    invoice_key, mappa_fattura_passiva, salva_invoice_passiva, COLL,
)


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


def test_mapping_schema_legacy_a_canonico():
    legacy = {
        "numero": "12/A", "fornitore_denominazione": "ACME Srl",
        "fornitore_piva": "IT01", "data": "2026-03-10", "importo_totale": 122.0,
        "imponibile": 100.0, "iva": 22.0, "stato": "importata",
        "righe": [{"descrizione": "x"}], "source": "tracciabilita",
    }
    c = mappa_fattura_passiva(legacy)
    assert c["invoice_number"] == "12/A"
    assert c["supplier_name"] == "ACME Srl"
    assert c["supplier_vat"] == "IT01"
    assert c["invoice_date"] == "2026-03-10"
    assert c["total_amount"] == 122.0
    assert c["linee"] == [{"descrizione": "x"}]
    assert c["invoice_key"] == invoice_key("12/A", "IT01", "2026-03-10")


def test_salva_idempotente_per_invoice_key():
    db = _Db()
    legacy = {"numero": "5", "fornitore_piva": "IT9", "data": "2026-01-01",
              "importo_totale": 50, "fornitore_denominazione": "Beta"}
    id1 = _run(salva_invoice_passiva(db, legacy, source="mig"))
    id2 = _run(salva_invoice_passiva(db, dict(legacy), source="mig"))  # stessa fattura
    assert id1 == id2
    assert len(db.c.docs) == 1  # nessun doppione


def test_salta_se_dati_insufficienti():
    db = _Db()
    # senza numero o P.IVA la chiave non è affidabile -> non inserisce
    assert _run(salva_invoice_passiva(db, {"data": "2026-01-01"})) is None
    assert len(db.c.docs) == 0


def test_ponte_erp_e_crud_scrivono_leggono_invoices():
    bridge = Path("app/routers/erp_bridge.py").read_text(encoding="utf-8")
    assert 'db["invoices"].update_one' in bridge
    assert 'db["fatture_passive"].update_one' not in bridge
    crud = Path("app/routers/fatture_module/crud.py").read_text(encoding="utf-8")
    assert 'db["fatture_passive"].find' not in crud
