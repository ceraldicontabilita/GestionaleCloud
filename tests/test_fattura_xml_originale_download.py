"""Richiesta utente 19/07/2026: "io ho bisogno di vedere sempre l'originale
la fattura così come arriva altrimenti non potrei mai vedere se c'è un
errore" — prima non esisteva nessun modo di scaricare/vedere il testo XML
grezzo di una fattura, nemmeno quando era salvato nel database, e il
modale "vedi fattura" poteva mostrare silenziosamente un riepilogo
ricostruito senza segnalarlo.

Copre: app.routers.fatture_module.crud.download_xml_originale (nuovo
endpoint) e il banner di avviso in generate_invoice_html quando si mostra
il fallback ricostruito invece dell'originale."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.fatture_module import crud as crud_mod
from app.routers.fatture_module.helpers import generate_invoice_html


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(crud_mod.Database, "get_db", staticmethod(lambda: db))


def test_download_xml_originale_404_se_fattura_non_esiste(monkeypatch):
    _patch_db(monkeypatch, _FakeDb())

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("non-esiste"))
    assert exc.value.status_code == 404
    assert "non trovata" in exc.value.detail.lower()


def test_download_xml_originale_404_se_xml_non_salvato(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20"}]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("fatt-1"))
    assert exc.value.status_code == 404
    assert "non disponibile" in exc.value.detail.lower()


def test_download_xml_originale_ritorna_i_bytes_xml_raw(monkeypatch):
    xml_content = "<FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>"
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20", "xml_raw": xml_content}]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.download_xml_originale("fatt-1"))

    assert res.body.decode("utf-8") == xml_content
    assert res.media_type == "application/xml"
    assert "fattura_20.xml" in res.headers["content-disposition"]


def test_generate_invoice_html_fallback_avvisa_che_non_e_loriginale():
    html = generate_invoice_html({"invoice_number": "20", "total_amount": 100.0}, [])

    assert "NON è il documento XML originale" in html
