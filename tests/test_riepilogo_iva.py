"""
Riepilogo annuale IVA + anomalie + azioni manuali (Fase 4, SPECIFICA_IVA.md
§16-19).

Livello 1: motore puro `riepilogo_iva_engine` (categorie, calcolo annuale,
anomalie). Livello 2: azioni manuali del router `iva` (escludi/rinvia/
indetraibile/recupero-annuale/correggi-periodo) su un DB in memoria, con la
protezione dell'IVA già utilizzata.
"""
import asyncio

import pytest

from app.engines import riepilogo_iva_engine as riep
from app.routers import iva as iva_router
from app.database import Database

# Riuso del fake-db del test liquidazioni.
from tests.test_liquidazione_iva_engine import _Db, _run  # noqa: E402


def _f(**kw):
    base = {"id": kw.get("id", "f"), "iva_detraibile": 100.0, "iva_utilizzata": False,
            "periodo_iva_attribuito": "2026-01", "stato_detrazione_iva": "DA_INSERIRE"}
    base.update(kw)
    return base


# ─── Motore puro ────────────────────────────────────────────────────────────

def test_riepilogo_categorie_separa_senza_doppioni():
    fatture = [
        _f(id="u", iva_utilizzata=True, iva_detraibile=100, stato_detrazione_iva="INSERITA_IN_LIQUIDAZIONE"),
        _f(id="n", iva_detraibile=50),                        # non utilizzata
        _f(id="i", iva_detraibile=30, stato_detrazione_iva="INDETRAIBILE"),
        _f(id="r", iva_detraibile=20, stato_detrazione_iva="RINVIATA"),
        _f(id="nc", iva_detraibile=999, tipo_documento="TD04"),  # nota credito → ignorata
    ]
    cat = riep.riepilogo_categorie(fatture)
    assert cat["utilizzata"] == {"iva": 100, "conteggio": 1}
    assert cat["non_utilizzata"] == {"iva": 50, "conteggio": 1}
    assert cat["indetraibile"] == {"iva": 30, "conteggio": 1}
    assert cat["rinviata"] == {"iva": 20, "conteggio": 1}
    # disponibile = utilizzata + non utilizzata + rinviata + recuperata
    assert cat["disponibile"]["iva"] == 170


def test_calcolo_annuale_da_liquidazioni_confermate():
    fatture = [
        _f(id="u", iva_utilizzata=True, iva_detraibile=200, stato_detrazione_iva="INSERITA_IN_LIQUIDAZIONE"),
        _f(id="n", iva_detraibile=50),
    ]
    liq = [{"iva_vendite": 500, "debito_periodo": 250, "credito_periodo": 0}]
    r = riep.calcolo_annuale(fatture, liq)
    assert r["iva_vendite"] == 500
    assert r["iva_acquisti_utilizzata"] == 200
    assert r["iva_recuperabile_non_utilizzata"] == 50
    assert r["iva_detraibile_annuale"] == 250
    assert r["debito_finale"] == 250 and r["credito_finale"] == 0


def test_anomalie_bloccanti_e_avvisi():
    fatture = [
        _f(id="neg", iva_detraibile=-5),                                   # bloccante
        _f(id="retro", periodo_iva_attribuito="2025-12", data_ricezione="2026-01-08"),  # bloccante
        _f(id="noric", data_ricezione=None),                               # avviso
        _f(id="dav", stato_detrazione_iva="DA_VERIFICARE"),                # avviso
    ]
    res = riep.rileva_anomalie(fatture, mese_corrente="2026-06")
    tipi_bloccanti = {a["tipo"] for a in res["bloccanti"]}
    assert "iva_negativa" in tipi_bloccanti
    assert "retroattribuzione_anno" in tipi_bloccanti
    tipi_avvisi = {a["tipo"] for a in res["avvisi"]}
    assert "data_ricezione_mancante" in tipi_avvisi
    assert "da_verificare" in tipi_avvisi


def test_anomalia_non_utilizzata_da_mesi():
    fatture = [_f(id="v", periodo_iva_attribuito="2026-01", data_ricezione="2026-01-05")]
    res = riep.rileva_anomalie(fatture, mese_corrente="2026-07")  # >3 mesi
    assert any(a["tipo"] == "non_utilizzata_da_mesi" for a in res["avvisi"])


# ─── Azioni manuali (router) ────────────────────────────────────────────────

@pytest.fixture
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: d))
    return d


def test_escludi_e_traccia_movimento(db):
    db["invoices"].docs.append(_f(id="a", iva_detraibile=100))
    res = _run(iva_router.escludi_fattura(fid="a", motivo="fuori competenza", utente="mario"))
    assert res["stato_nuovo"] == "ESCLUSA"
    inv = db["invoices"].docs[0]
    assert inv["stato_detrazione_iva"] == "ESCLUSA"
    assert inv["disponibile_per_nuovo_calcolo"] is False
    mov = db["movimenti_iva_fattura"].docs[0]
    assert mov["tipo_movimento"] == "ESCLUSIONE"
    assert mov["valore_precedente"] == "DA_INSERIRE" and mov["valore_nuovo"] == "ESCLUSA"
    assert mov["created_by"] == "mario"


def test_azione_bloccata_se_iva_utilizzata(db):
    from fastapi import HTTPException
    db["invoices"].docs.append(_f(id="a", iva_utilizzata=True,
                                  stato_detrazione_iva="INSERITA_IN_LIQUIDAZIONE"))
    with pytest.raises(HTTPException) as ei:
        _run(iva_router.escludi_fattura(fid="a", motivo="x", utente="admin"))
    assert ei.value.status_code == 409


def test_correggi_periodo(db):
    db["invoices"].docs.append(_f(id="a", periodo_iva_attribuito="2026-03"))
    res = _run(iva_router.correggi_periodo_fattura(
        fid="a", periodo="2026-02", motivo="periodo errato", utente="admin"))
    assert res["success"]
    inv = db["invoices"].docs[0]
    assert inv["periodo_iva_attribuito"] == "2026-02"
    assert inv["regola_iva_applicata"] == "CORREZIONE_MANUALE"


def test_recupero_annuale(db):
    db["invoices"].docs.append(_f(id="a"))
    res = _run(iva_router.recupero_annuale_fattura(fid="a", motivo="non usata nel mese", utente="admin"))
    assert res["stato_nuovo"] == "RECUPERATA_IN_DICHIARAZIONE_ANNUALE"
    assert db["movimenti_iva_fattura"].docs[0]["tipo_movimento"] == "RECUPERO_ANNUALE"


def test_includi_riporta_disponibile(db):
    db["invoices"].docs.append(_f(id="a", stato_detrazione_iva="ESCLUSA",
                                  disponibile_per_nuovo_calcolo=False, motivo_esclusione="x"))
    res = _run(iva_router.includi_fattura(fid="a", motivo="rientra", utente="admin"))
    assert res["stato_nuovo"] == "DA_INSERIRE"
    inv = db["invoices"].docs[0]
    assert inv["disponibile_per_nuovo_calcolo"] is True
    assert inv["motivo_esclusione"] is None
