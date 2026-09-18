"""PR 9 — liquidazione IVA onesta: DATI_MANCANTI invece di "calcolata a 0".

Audit del commercialista (§3): febbraio 2026 senza alcun corrispettivo in
archivio veniva esposto come `CALCOLATO` con vendite 0; l'archivio `invoices`
vuoto rendeva l'intera IVA vendite "da versare". Un mese concluso con giorni
senza chiusura RT o senza fatture in archivio deve dire che mancano i dati.
"""
import asyncio
from datetime import date

from app.services.iva_liquidation_query import get_iva_period_snapshot
from app.services.sheets_document_store import MemorySheetsClient

OGGI = date(2026, 9, 3)


def _run(coro):
    return asyncio.run(coro)


def _db():
    return MemorySheetsClient()["iva_dati_mancanti"]


def _corrispettivo(giorno, iva=100.0):
    return {"data": giorno, "totale": iva * 11, "totale_iva": iva, "matricola_rt": "RT1",
            "corrispettivo_key": f"k-{giorno}"}


def test_febbraio_2026_senza_corrispettivi_e_dati_mancanti_non_zero():
    db = _db()
    _run(db.invoices.insert_one({"id": "f1", "periodo_iva_attribuito": "2026-02", "iva_detraibile": 10.0}))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=2, today=OGGI))
    assert snap["stato_calcolo"] == "DATI_MANCANTI"
    assert snap["attendibile"] is False
    assert "nessun_corrispettivo_nel_mese" in snap["motivi"]
    assert "giorni_senza_corrispettivo" in snap["motivi"]
    assert len(snap["giorni_senza_corrispettivo"]) == 28
    assert snap["giorni_mese"] == 28 and snap["giorni_con_corrispettivo"] == 0
    assert snap["iva_vendite"] is None and snap["iva_vendite_cents"] is None
    assert snap["saldo"] is None and snap["debito_periodo"] is None
    # le fatture esistono: l'IVA acquisti resta leggibile, ma il mese non e' calcolato
    assert snap["iva_acquisti"] == 10.0
    assert snap["fonte"] == "calcolo_canonico"


def test_archivio_fatture_vuoto_azzera_l_attendibilita_e_l_iva_acquisti():
    db = _db()
    for giorno in range(1, 32):
        _run(db.corrispettivi.insert_one(_corrispettivo(f"2026-03-{giorno:02d}")))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=3, today=OGGI))
    assert snap["stato_calcolo"] == "DATI_MANCANTI"
    assert snap["motivi"] == ["archivio_fatture_vuoto"]
    assert snap["archivio_fatture_vuoto"] is True
    assert snap["giorni_senza_corrispettivo"] == []
    assert snap["iva_acquisti"] is None and snap["iva_acquisti_cents"] is None
    assert snap["iva_vendite"] == 3100.0  # le vendite ci sono, ma senza acquisti niente saldo
    assert snap["saldo"] is None and snap["credito_periodo"] is None


def test_giorni_senza_chiusura_rt_vengono_elencati():
    db = _db()
    _run(db.invoices.insert_one({"id": "f1", "periodo_iva_attribuito": "2026-01"}))
    for giorno in range(2, 26):
        _run(db.corrispettivi.insert_one(_corrispettivo(f"2026-01-{giorno:02d}")))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=1, today=OGGI))
    assert snap["stato_calcolo"] == "DATI_MANCANTI"
    assert snap["motivi"] == ["giorni_senza_corrispettivo"]
    assert snap["giorni_senza_corrispettivo"] == [
        "2026-01-01", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30", "2026-01-31",
    ]
    assert snap["giorni_con_corrispettivo"] == 24
    assert snap["iva_vendite"] == 2400.0  # parziale, esposto come tale
    assert snap["saldo"] is None


def test_mese_completo_con_fatture_resta_calcolato_e_attendibile():
    db = _db()
    _run(db.invoices.insert_one({"id": "f1", "periodo_iva_attribuito": "2026-04", "iva_detraibile": 50.0,
                                 "stato_detrazione_iva": "DA_INSERIRE"}))
    for giorno in range(1, 31):
        _run(db.corrispettivi.insert_one(_corrispettivo(f"2026-04-{giorno:02d}", iva=10.0)))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=4, today=OGGI))
    assert snap["stato_calcolo"] == "CALCOLATA"
    assert snap["attendibile"] is True and snap["motivi"] == []
    assert snap["iva_vendite"] == 300.0 and snap["iva_acquisti"] == 50.0 and snap["saldo"] == 250.0


def test_liquidazione_confermata_vince_sui_dati_mancanti():
    db = _db()
    _run(db.liquidazioni_iva.insert_one({
        "periodo": "2026-02", "stato": "CONFERMATA", "versione": 1,
        "iva_vendite": 5000.0, "iva_acquisti": 1000.0, "credito_precedente": 0.0, "saldo": 4000.0,
    }))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=2, today=OGGI))
    assert snap["stato_calcolo"] == "CONFERMATA" and snap["attendibile"] is True
    assert snap["saldo"] == 4000.0
    assert "nessun_corrispettivo_nel_mese" in snap["motivi"]  # resta visibile come avvertenza


def test_scadenze_iva_mensili_espongono_dati_mancanti(monkeypatch):
    from app.routers import scadenze as mod

    db = _db()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    esito = _run(mod.get_scadenze_iva_mensile(2026))
    febbraio = next(s for s in esito["scadenze"] if s["mese"] == 2)
    assert febbraio["stato"] == "DATI_MANCANTI"
    assert febbraio["attendibile"] is False
    assert "archivio_fatture_vuoto" in febbraio["motivi"]
    assert len(febbraio["giorni_senza_corrispettivo"]) == 28
    assert febbraio["saldo"] is None and febbraio["da_versare"] is False
