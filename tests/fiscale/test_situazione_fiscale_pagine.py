"""Situazione fiscale: documenti F24 a pagine, filtri e totali sul server.

La pagina chiedeva 5.000 righe tributo e le raggruppava, filtrava e contava
nel browser. Ora ``raggruppa=true`` rende una pagina di documenti interi: le
pagine in fila danno lo stesso elenco e i totali sono la somma di tutte le
righe, qualunque pagina si chieda.
"""
import asyncio
from decimal import Decimal

from app.routers import fiscal_control
from app.services import registro_fiscale_f24 as rf
from tests.fiscale.test_fiscal_drive_readthrough import _usa_registro


def _obblighi(**kwargs):
    base = dict(status=None, limit=200, _admin={}, raggruppa=True, offset=0,
                cerca=None, anno_documento=None, stato_documento=None)
    base.update(kwargs)
    return asyncio.run(fiscal_control.obligations(**base))


def test_documenti_interi_con_totali_uguali_alla_somma_delle_righe(monkeypatch):
    _usa_registro(monkeypatch)
    righe = asyncio.run(fiscal_control.obligations(status=None, limit=5000, _admin={}))["items"]
    tutto = _obblighi()
    assert tutto["total"] == tutto["total_groups"] == 3
    assert tutto["total_rows"] == len(righe) == 4
    assert [d["document_id"] for d in tutto["items"]] == ["F24-APERTO", "Q-GIUGNO", "F24-COPERTO"]
    aperto = tutto["items"][0]
    assert aperto["is_f24_group"] is True and len(aperto["rows"]) == 2
    assert (aperto["debit_amount"], aperto["credit_amount"], aperto["net_amount"]) == (300.0, 50.0, 250.0)

    debito = sum(Decimal(str(r["debit_amount"] or 0)) for r in righe)
    credito = sum(Decimal(str(r["credit_amount"] or 0)) for r in righe)
    assert tutto["totali"] == {"debit_amount": float(debito), "credit_amount": float(credito),
                               "net_amount": float(debito - credito)}

    # Pagine da uno: stesso elenco, stessi totali su ogni pagina.
    pagine = [_obblighi(offset=o, limit=1) for o in range(3)]
    assert [p["items"][0]["id"] for p in pagine] == [d["id"] for d in tutto["items"]]
    assert all(p["totali"] == tutto["totali"] and p["total"] == 3 for p in pagine)


def test_filtri_di_elenco_e_tendine(monkeypatch):
    _usa_registro(monkeypatch)
    tutto = _obblighi()
    assert tutto["facets"]["anni"] == ["2024"]
    assert tutto["facets"]["stati"] == ["DA_VERIFICARE", "QUIETANZA_PRESENTE"]

    quietanze = _obblighi(stato_documento="QUIETANZA_PRESENTE")
    assert [d["document_id"] for d in quietanze["items"]] == ["Q-GIUGNO"]
    assert quietanze["totali"]["debit_amount"] == 1000.0
    # Il testo si cerca anche dentro le righe del documento (codice 1631).
    assert [d["document_id"] for d in _obblighi(cerca="1631")["items"]] == ["F24-APERTO"]
    assert _obblighi(anno_documento="2023")["total"] == 0
    # Lo stato della scheda (TO_PAY) resta il filtro del registro.
    assert [d["document_id"] for d in _obblighi(status="TO_PAY")["items"]] == ["F24-APERTO"]


def test_f24_rows_raggruppate(monkeypatch):
    _usa_registro(monkeypatch)
    payload = asyncio.run(fiscal_control.f24_rows(
        tax_code=None, document_id=None, year=2024, credits_only=True,
        offset=0, limit=200, _admin={}, raggruppa=True,
        cerca=None, anno_documento=None, stato_documento=None,
    ))
    assert payload["total"] == 1 and payload["total_rows"] == 1
    assert payload["items"][0]["credit_amount"] == 50.0
    assert payload["filters"]["credits_only"] is True


def test_anno_e_stato_del_documento():
    assert rf.anno_documento({"payment_year": "2025", "payment_date": "2024-01-01"}) == "2025"
    assert rf.anno_documento({"payment_date": "2024-06-17"}) == "2024"
    assert rf.stato_documento({"evidence_state": "X", "status": "Y"}) == "X"
    assert rf.stato_documento({}) == ""
