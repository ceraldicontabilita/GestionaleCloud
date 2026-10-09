"""Libro giornale spento (CLAUDE.md §24): nessuna scrittura con l'interruttore off.

Decisione del titolare 07/10/2026: il giornale non serve, le registrazioni
restano spente finche' ``LIBRO_GIORNALE_ATTIVO`` non vale true. Il difetto
(variabile assente) e' spento.
"""
import asyncio

import pytest

from app.services import registrazione_contabile as rc


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, *a, **k):
        return None

    def find(self, *a, **k):
        class _C:
            async def to_list(self_inner, n=None):
                return []

            def __aiter__(self_inner):
                return self_inner

            async def __anext__(self_inner):
                raise StopAsyncIteration
        return _C()

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, *a, **k):
        return None


class _Db(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Coll())


def run(c):
    return asyncio.run(c)


FATTURA = {"id": "F1", "invoice_number": "1", "invoice_date": "2026-03-01",
           "total_amount": 122.0, "total_tax": 22.0, "iva_detraibile": 22.0,
           "supplier_name": "Alfa", "supplier_vat": "01234567890"}


def test_difetto_spento(monkeypatch):
    monkeypatch.delenv("LIBRO_GIORNALE_ATTIVO", raising=False)
    assert rc.giornale_attivo() is False
    monkeypatch.setenv("LIBRO_GIORNALE_ATTIVO", "true")
    assert rc.giornale_attivo() is True


@pytest.mark.parametrize("valore", ["false", "0", "no", "off", ""])
def test_spento_niente_scritture(monkeypatch, valore):
    monkeypatch.setenv("LIBRO_GIORNALE_ATTIVO", valore)
    db = _Db()
    assert run(rc.registra_fattura(db, dict(FATTURA)))["stato"] == "disattivato"
    assert run(rc.registra_corrispettivo(db, {"id": "C1", "data": "2026-03-01", "totale": 100}))["stato"] == "disattivato"
    assert run(rc.registra_documento_import(db, "fattura", dict(FATTURA)))["stato"] == "disattivato"
    semplice = run(rc.registra_scrittura_semplice(db, {"data": "2026-03-01", "tipo": "x"}, [], {"tipo": "x"}))
    assert semplice["stato"] == "disattivato" and semplice["id"] is None
    assert run(rc.registra_tutte_fatture(db))["stato"] == "disattivato"
    assert run(rc.registra_tutti_corrispettivi(db))["stato"] == "disattivato"
    assert run(rc.registra_pregresso(db))["stato"] == "disattivato"
    assert run(rc.registra_fatture_rimaste_fuori(db))["stato"] == "disattivato"
    assert run(rc.storna_registrazione_fattura(db, "F1", "test"))["stato"] == "disattivato"
    assert rc.avvia_pregresso_in_background(db) is False
    assert db["movimenti_contabili"].docs == []
    assert db["invoices"].docs == []


def test_la_guardia_di_fondo_rifiuta_la_scrittura(monkeypatch):
    monkeypatch.setenv("LIBRO_GIORNALE_ATTIVO", "false")
    with pytest.raises(rc.GiornaleDisattivato):
        run(rc._scrivi_movimento(_Db(), {"tipo": "x", "righe": [{"conto_codice": "a", "dare": 1, "avere": 0}]}, []))
