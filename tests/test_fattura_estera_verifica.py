"""Coda di verifica fatture estere (scelta utente 14/07/2026): l'utente
conferma o corregge i dati letti dall'AI, ogni esito costruisce il rating
di affidabilità per fornitore in `fatture_estere_verifiche`."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import fatture_estera_verifica as mod


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        self._docs = sorted(self._docs, key=lambda d: d.get(field) or "", reverse=(direction == -1))
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in (query or {}).items()):
                return {k2: v for k2, v in d.items() if k2 != "_id"}
        return None

    def find(self, query=None, *a, **k):
        query = query or {}
        return _FakeCursor([d for d in self.docs if all(d.get(k2) == v for k2, v in query.items())])

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in (query or {}).items()):
                for k2, v in update.get("$set", {}).items():
                    d[k2] = v
                return

    async def update_many(self, query, update, *a, **k):
        n = 0
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in (query or {}).items()):
                for k2, v in update.get("$set", {}).items():
                    d[k2] = v
                n += 1

        class _R:
            modified_count = n
        return _R()

    def aggregate(self, pipeline, *a, **k):
        # Interprete minimo per il solo pipeline group-by-supplier_vat di affidabilita_fornitori
        gruppi = {}
        for d in self.docs:
            key = d.get("supplier_vat")
            g = gruppi.setdefault(key, {"_id": key, "fornitore_nome": None, "totale": 0, "corrette": 0})
            g["fornitore_nome"] = d.get("supplier_name")
            g["totale"] += 1
            if d.get("esito") == "confermata":
                g["corrette"] += 1
        risultati = sorted(gruppi.values(), key=lambda g: -g["totale"])
        return _FakeCursor(risultati)


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


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))


def _invoice(**over):
    base = {
        "id": "inv-1", "invoice_number": "RE-055", "invoice_date": "2026-06-10",
        "data_scadenza": "2026-07-10", "supplier_name": "Foreign Supplies GmbH",
        "supplier_vat": "DE123456789", "total_amount": 100.0, "imponibile": 100.0,
        "iva": 0.0, "numero_fattura": "RE-055", "data_fattura": "2026-06-10",
        "cedente_denominazione": "Foreign Supplies GmbH", "cedente_piva": "DE123456789",
        "importo_totale": 100.0, "invoice_key": "RE-055_DE123456789_2026-06-10",
        "verifica_ai": "in_attesa",
    }
    base.update(over)
    return base


def test_lista_da_verificare_solo_in_attesa(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice(id="a"), _invoice(id="b", verifica_ai="confermata")]
    _patch_db(monkeypatch, db)

    res = _run(mod.lista_da_verificare())

    assert res["totale"] == 1
    assert res["fatture"][0]["id"] == "a"


def test_conferma_senza_correzioni(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    _patch_db(monkeypatch, db)

    res = _run(mod.verifica_fattura("inv-1", {
        "invoice_number": "RE-055", "invoice_date": "2026-06-10",
        "supplier_name": "Foreign Supplies GmbH", "supplier_vat": "DE123456789",
        "imponibile": 100.0, "iva": 0.0, "total_amount": 100.0,
    }))

    assert res["esito"] == "confermata"
    assert res["campi_corretti"] == []
    assert db["invoices"].docs[0]["verifica_ai"] == "confermata"
    assert len(db["fatture_estere_verifiche"].docs) == 1
    assert db["fatture_estere_verifiche"].docs[0]["esito"] == "confermata"


def test_correzione_importo_aggiorna_fattura_e_specchio(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    _patch_db(monkeypatch, db)

    res = _run(mod.verifica_fattura("inv-1", {"total_amount": 120.0}))

    assert res["esito"] == "corretta"
    assert "total_amount" in res["campi_corretti"]
    inv = db["invoices"].docs[0]
    assert inv["total_amount"] == 120.0
    assert inv["importo_totale"] == 120.0  # campo speculare in sync
    assert db["fatture_estere_verifiche"].docs[0]["esito"] == "corretta"
    assert db["fatture_estere_verifiche"].docs[0]["campi_corretti"] == ["total_amount"]


def test_correzione_numero_rigenera_invoice_key(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    _patch_db(monkeypatch, db)

    _run(mod.verifica_fattura("inv-1", {"invoice_number": "RE-999"}))

    inv = db["invoices"].docs[0]
    assert inv["invoice_number"] == "RE-999"
    assert inv["numero_fattura"] == "RE-999"
    assert inv["invoice_key"] == "RE-999_DE123456789_2026-06-10"


def test_correzione_data_ricalcola_scadenza(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    _patch_db(monkeypatch, db)

    _run(mod.verifica_fattura("inv-1", {"invoice_date": "2026-05-01"}))

    inv = db["invoices"].docs[0]
    assert inv["invoice_date"] == "2026-05-01"
    assert inv["data_scadenza"] == "2026-05-31"
    assert inv["anno"] == 2026


def test_fattura_gia_verificata_409(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice(verifica_ai="confermata")]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(mod.verifica_fattura("inv-1", {"total_amount": 50.0}))
    assert exc.value.status_code == 409


def test_fattura_inesistente_404(monkeypatch):
    db = _FakeDb()
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(mod.verifica_fattura("non-esiste", {}))
    assert exc.value.status_code == 404


def test_partita_aperta_integra_viene_aggiornata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    db["partite_aperte"].docs = [{
        "id": "pa-1", "documento_id": "inv-1", "tipo": "fattura_fornitore",
        "importo_originale": 100.0, "residuo": 100.0,
    }]
    _patch_db(monkeypatch, db)

    _run(mod.verifica_fattura("inv-1", {"total_amount": 130.0}))

    partita = db["partite_aperte"].docs[0]
    assert partita["importo_originale"] == 130.0
    assert partita["residuo"] == 130.0


def test_partita_aperta_gia_toccata_non_viene_modificata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_invoice()]
    db["partite_aperte"].docs = [{
        "id": "pa-1", "documento_id": "inv-1", "tipo": "fattura_fornitore",
        "importo_originale": 100.0, "residuo": 40.0,  # già parzialmente pagata
    }]
    _patch_db(monkeypatch, db)

    _run(mod.verifica_fattura("inv-1", {"total_amount": 130.0}))

    partita = db["partite_aperte"].docs[0]
    assert partita["importo_originale"] == 100.0
    assert partita["residuo"] == 40.0


def test_affidabilita_fornitori_percentuale(monkeypatch):
    db = _FakeDb()
    db["fatture_estere_verifiche"].docs = [
        {"supplier_vat": "DE1", "supplier_name": "Foo GmbH", "esito": "confermata"},
        {"supplier_vat": "DE1", "supplier_name": "Foo GmbH", "esito": "confermata"},
        {"supplier_vat": "DE1", "supplier_name": "Foo GmbH", "esito": "corretta"},
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.affidabilita_fornitori())

    assert len(res["fornitori"]) == 1
    f = res["fornitori"][0]
    assert f["supplier_vat"] == "DE1"
    assert f["totale"] == 3
    assert f["corrette"] == 2
    assert f["percentuale_corrette"] == pytest.approx(66.7, abs=0.1)
