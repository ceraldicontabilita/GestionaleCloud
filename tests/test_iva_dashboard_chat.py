"""
Fase 5: dashboard IVA mensile (§21) e strumento chat 'spiega_iva_fattura'
tracciabile (§20).
"""
import pytest

from app.routers import iva as iva_router
from app.services import chat_ai_engine as chat
from app.database import Database

from tests.test_liquidazione_iva_engine import _Db, _run  # noqa: E402


def _f(**kw):
    base = {"id": kw.get("id", "f"), "iva_detraibile": 100.0, "iva_utilizzata": False,
            "periodo_iva_attribuito": "2026-02", "stato_detrazione_iva": "DA_INSERIRE"}
    base.update(kw)
    return base


@pytest.fixture
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: d))
    return d


def test_dashboard_mensile_ripartisce_iva(db):
    # fattura di febbraio attribuita a febbraio
    db["invoices"].docs.append(_f(id="a", iva_detraibile=100, periodo_iva_attribuito="2026-02"))
    # ricevuta a febbraio ma attribuita a gennaio (regola entro il 15)
    db["invoices"].docs.append(_f(id="b", iva_detraibile=40, periodo_iva_attribuito="2026-01",
                                  data_ricezione="2026-02-08"))
    # utilizzata a febbraio
    db["invoices"].docs.append(_f(id="c", iva_detraibile=30, periodo_iva_attribuito="2026-02",
                                  periodo_iva_utilizzato="2026-02",
                                  stato_detrazione_iva="INSERITA_IN_LIQUIDAZIONE", iva_utilizzata=True))
    res = _run(iva_router.dashboard_iva_mensile(anno=2026, mese=2))
    assert res["periodo"] == "2026-02"
    # attribuite a febbraio: a (100) + c (30) = 130
    assert res["iva_acquisti_attribuita"] == 130
    assert res["iva_ricevuta_attribuita_mese_precedente"] == 40
    assert res["iva_utilizzata"] == 30
    # non utilizzata attribuita a feb: a (100), c esclusa perché già in liquidazione
    assert res["iva_non_utilizzata"] == 100


def test_spiega_iva_fattura_non_utilizzata(db):
    db["invoices"].docs.append({
        "id": "x", "supplier_name": "Alfa", "invoice_number": "1/2026",
        "invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
        "periodo_iva_attribuito": "2026-01",
        "regola_iva_applicata": "ENTRO_15_MESE_SUCCESSIVO",
        "iva": 220, "iva_detraibile": 220, "iva_utilizzata": False,
    })
    out = _run(chat._tool_spiega_iva_fattura(db, {"fattura_id": "x"}))
    assert out["periodo_iva_attribuito"] == "2026-01"
    assert out["iva_utilizzata"] is False
    assert "attribuita per competenza al periodo 2026-01" in out["spiegazione"]
    assert "non ancora utilizzata" in out["spiegazione"].lower()


def test_spiega_iva_fattura_gia_utilizzata(db):
    db["liquidazioni_iva"].docs.append({"id": "L1", "periodo": "2026-01", "stato": "CONFERMATA"})
    db["invoices"].docs.append({
        "id": "y", "supplier_name": "Beta", "invoice_number": "9/2026",
        "invoice_date": "2026-01-10", "data_ricezione": "2026-01-12",
        "periodo_iva_attribuito": "2026-01", "regola_iva_applicata": "STESSO_MESE",
        "iva": 50, "iva_detraibile": 50, "iva_utilizzata": True,
        "periodo_iva_utilizzato": "2026-01", "liquidazione_id": "L1",
    })
    out = _run(chat._tool_spiega_iva_fattura(db, {"fattura_id": "y"}))
    assert out["iva_utilizzata"] is True
    assert out["liquidazione_stato"] == "CONFERMATA"
    assert "non viene conteggiata di nuovo" in out["spiegazione"]


def test_spiega_iva_fattura_non_trovata(db):
    out = _run(chat._tool_spiega_iva_fattura(db, {"fattura_id": "zzz"}))
    assert "errore" in out


def test_spiega_iva_fattura_non_inventa_detraibilita(db):
    db["invoices"].docs.append({
        "id": "review", "iva": 220, "periodo_iva_attribuito": "2026-01",
        "stato_detrazione_iva": "DA_VERIFICARE", "iva_utilizzata": False,
    })

    out = _run(chat._tool_spiega_iva_fattura(db, {"fattura_id": "review"}))

    assert out["iva_detraibile"] == 0
    assert "resta a zero" in out["spiegazione"]
