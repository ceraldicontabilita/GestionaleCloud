import asyncio

import pytest
from fastapi import HTTPException

from app.database import Database
from app.routers import lotti_integration
from app.services.archivio_documenti_memoria import SheetDatabase


@pytest.fixture()
def sheet_db():
    original = Database.db
    db = SheetDatabase("test-lotti")
    Database.db = db
    try:
        yield db
    finally:
        Database.db = original


def run(coro):
    return asyncio.run(coro)


def test_projection_reads_invoices_and_is_stable(sheet_db, monkeypatch):
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    run(sheet_db["invoices"].insert_one({
        "id": "inv-1",
        "invoice_number": "44/A",
        "invoice_date": "2026-08-20",
        "supplier_name": "Molino Test",
        "supplier_vat": "01234567890",
        "total_amount": 122,
        "linee": [{"descrizione": "Farina 00", "quantita": "2", "unita_misura": "KG", "prezzo_unitario": "10"}],
        "xml_raw": "<FatturaElettronica />",
    }))
    run(sheet_db["fatture_ricevute"].insert_one({"id": "sbagliata"}))

    first = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=200, x_lotti_key="secret-test"
    ))
    second = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=200, x_lotti_key="secret-test"
    ))

    assert first == second
    assert first["total"] == 1
    assert first["data"][0]["source_id"] == "inv-1"
    assert first["data"][0]["has_xml"] is True
    assert "xml_raw" not in first["data"][0]
    assert len(first["data"][0]["source_hash"]) == 64

    detail = run(lotti_integration.get_invoice_for_lotti("inv-1", "secret-test"))
    assert detail["xml_raw"] == "<FatturaElettronica />"
    assert detail["lines"][0]["descrizione"] == "Farina 00"


def test_projection_filters_year_and_deleted(sheet_db, monkeypatch):
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    run(sheet_db["invoices"].insert_many([
        {"id": "old", "invoice_date": "2025-01-01"},
        {"id": "deleted", "invoice_date": "2026-01-01", "status": "deleted"},
        {"id": "current", "invoice_date": "23/08/2026"},
    ]))
    result = run(lotti_integration.list_invoices_for_lotti(
        anno=2026, skip=0, limit=50, x_lotti_key="secret-test"
    ))
    assert [item["source_id"] for item in result["data"]] == ["current"]


def test_projection_fails_closed_without_secret(sheet_db, monkeypatch):
    monkeypatch.delenv("LOTTI_INTEGRATION_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        run(lotti_integration.list_invoices_for_lotti(
            anno=2026, skip=0, limit=50, x_lotti_key="anything"
        ))
    assert exc.value.status_code == 503


def test_employee_projection_uses_stable_identity_and_filters_inactive(sheet_db, monkeypatch):
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    run(sheet_db["dipendenti"].insert_many([
        {
            "id": "dip-1", "nome": "Anna", "cognome": "Rossi",
            "codice_fiscale": "rssnna00a00f839x", "mansione": "Pasticcere",
            "attivo": True, "in_carico": True,
        },
        {"id": "dip-2", "nome_completo": "Mario Verdi", "attivo": False},
        {"id": "dip-3", "nome_completo": "Record unificato", "merged_into": "dip-1"},
    ]))

    result = run(lotti_integration.list_employees_for_lotti("secret-test"))

    assert result["total"] == 1
    assert result["data"] == [{
        "source_id": "dip-1",
        "nome": "Anna",
        "cognome": "Rossi",
        "nome_completo": "Anna Rossi",
        "codice_fiscale": "RSSNNA00A00F839X",
        "mansione": "Pasticcere",
        "matricola": "",
        "stato": "attivo",
        "data_fine_rapporto": None,
        "motivo_cessazione": None,
        "lotti_operatore": True,
        "ruolo_app": "dipendente",
        "source": "gestionalecloud",
    }]
    # con includi_cessati anche chi non e' piu' in forza, con lo stato
    tutti = run(lotti_integration.list_employees_for_lotti("secret-test", includi_cessati=True))
    assert [(d["source_id"], d["stato"]) for d in tutti["data"]] == [("dip-1", "attivo"), ("dip-2", "cessato")]


def test_projection_usa_xml_in_fattura_allegata():
    """15/09/2026: le fatture legacy tengono l'XML in ``fattura_allegata``;
    il feed lo esponeva solo da ``xml_raw`` e Lotti le scartava."""
    from app.routers.lotti_integration import _projection, _xml_of
    xml = '<?xml version="1.0"?><p:FatturaElettronica versione="FPR12"><FatturaElettronicaHeader/></p:FatturaElettronica>'
    doc = {"id": 1, "numero": "1029", "data": "2026-04-01", "fornitore": "EUROUOVA SRL", "fattura_allegata": xml}
    assert _xml_of(doc) == xml
    assert _xml_of({"fattura_allegata": "non e' xml"}) == ""
    proj = _projection(doc, include_xml=True)
    assert proj["has_xml"] is True and proj["xml_raw"] == xml


def test_source_hash_identico_da_content_hash_e_da_xml(sheet_db, monkeypatch):
    """17/09/2026: l'elenco per Lotti si calcola dalla versione leggera
    (senza XML) usando content_hash = sha256(XML): il source_hash deve
    restare identico a quello calcolato dall'XML, altrimenti Lotti vedrebbe
    ogni fattura come «cambiata dopo la prima ricezione»."""
    import hashlib

    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    xml = "<FatturaElettronica><Numero>7</Numero></FatturaElettronica>"
    base = {
        "invoice_number": "7", "invoice_date": "2026-09-01", "supplier_vat": "01234567890",
        "supplier_name": "Fornitore", "total_amount": 10, "linee": [],
    }
    run(sheet_db["invoices"].insert_many([
        {"id": "con-hash", "xml_raw": xml, "content_hash": hashlib.sha256(xml.encode("utf-8")).hexdigest(), **base},
        {"id": "senza-hash", "xml_raw": xml, **base},
    ]))
    elenco = run(lotti_integration.list_invoices_for_lotti(anno=2026, skip=0, limit=50, x_lotti_key="secret-test"))
    per_id = {item["source_id"]: item for item in elenco["data"]}
    atteso = lotti_integration._projection({"id": "con-hash", "xml_raw": xml, **base}, include_xml=False)
    assert per_id["con-hash"]["source_hash"] == atteso["source_hash"]
    assert per_id["con-hash"]["has_xml"] is True and per_id["senza-hash"]["has_xml"] is True
    dettaglio = run(lotti_integration.get_invoice_for_lotti("senza-hash", "secret-test"))
    assert dettaglio["xml_raw"] == xml
