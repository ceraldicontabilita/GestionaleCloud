"""Audit 27/09/2026 — IVA mensile e annuale: punti 3, 7, 8 e 10.

3. Una fattura del mese con IVA e detraibilita' da decidere usciva dal
   calcolo: IVA acquisti 0, stato CALCOLATA, «da versare» gonfiato. Ora il
   mese e' DATI_MANCANTI con IVA acquisti e saldo None; le copie archiviate
   non entrano.
7. Il riepilogo annuale legge solo fatture attive.
8. Le note di credito riducono l'IVA detraibile (segno negativo).
10. Un mese interamente in chiusura (``chiusure_attivita``) senza
    corrispettivi non e' «nessun corrispettivo nel mese».
"""
import asyncio
from datetime import date

from app.routers import iva as iva_router
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.chiusure_attivita import registra_chiusura
from app.services.iva_liquidation_query import get_iva_period_snapshot

OGGI = date(2026, 9, 27)


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _mese_pieno(db, periodo, giorni, iva=100.0):
    for giorno in range(1, giorni + 1):
        _run(db.corrispettivi.insert_one({
            "data": f"{periodo}-{giorno:02d}", "totale": iva * 11, "totale_iva": iva,
            "corrispettivo_key": f"k-{periodo}-{giorno}",
        }))


def test_detraibilita_da_decidere_rende_il_mese_dati_mancanti():
    db = _db("iva-da-decidere")
    _mese_pieno(db, "2026-04", 30)
    _run(db.invoices.insert_many([
        {"id": "ok", "periodo_iva_attribuito": "2026-04", "iva": 50.0, "iva_detraibile": 50.0,
         "stato_detrazione_iva": "DA_INSERIRE"},
        {"id": "dv", "periodo_iva_attribuito": "2026-04", "iva": 220.0,
         "stato_detrazione_iva": "DA_VERIFICARE"},
    ]))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=4, today=OGGI))
    assert snap["stato_calcolo"] == "DATI_MANCANTI"
    assert "detraibilita_da_verificare" in snap["motivi"]
    assert snap["attendibile"] is False
    assert snap["iva_acquisti"] is None and snap["iva_acquisti_cents"] is None
    assert snap["saldo"] is None and snap["saldo_cents"] is None
    assert snap["debito_periodo"] is None
    assert snap["iva_vendite"] == 3000.0
    assert snap["conteggi"]["detraibilita_da_decidere_con_iva"] == 1


def test_copia_archiviata_non_blocca_ne_conta():
    db = _db("iva-archiviata")
    _mese_pieno(db, "2026-04", 30)
    _run(db.invoices.insert_many([
        {"id": "ok", "periodo_iva_attribuito": "2026-04", "iva": 50.0, "iva_detraibile": 50.0,
         "stato_detrazione_iva": "DA_INSERIRE"},
        # copia archiviata della stessa fattura, mai valutata
        {"id": "arch", "periodo_iva_attribuito": "2026-04", "iva": 50.0, "status": "archived",
         "stato_detrazione_iva": "DA_VERIFICARE"},
        {"id": "arch2", "periodo_iva_attribuito": "2026-04", "iva": 50.0, "iva_detraibile": 50.0,
         "status": "archiviata", "stato_detrazione_iva": "DA_INSERIRE"},
    ]))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=4, today=OGGI))
    assert snap["stato_calcolo"] == "CALCOLATA"
    assert snap["iva_acquisti"] == 50.0
    assert snap["saldo"] == 2950.0


def test_nota_credito_riduce_iva_acquisti_del_mese():
    db = _db("iva-nota-credito")
    _mese_pieno(db, "2026-04", 30)
    _run(db.invoices.insert_many([
        {"id": "f", "periodo_iva_attribuito": "2026-04", "iva": 100.0, "iva_detraibile": 100.0,
         "stato_detrazione_iva": "DA_INSERIRE"},
        {"id": "nc", "periodo_iva_attribuito": "2026-04", "iva": 30.0, "iva_detraibile": 30.0,
         "stato_detrazione_iva": "DA_INSERIRE", "tipo_documento": "TD04"},
    ]))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=4, today=OGGI))
    assert snap["iva_acquisti"] == 70.0
    assert snap["saldo"] == 2930.0


def test_mese_tutto_in_chiusura_non_e_dati_mancanti_per_i_corrispettivi():
    db = _db("iva-chiusura")
    _run(registra_chiusura(db, "2026-02-01", "2026-02-28", "ristrutturazione", "titolare"))
    _run(db.invoices.insert_one({"id": "f", "periodo_iva_attribuito": "2026-02", "iva": 10.0,
                                 "iva_detraibile": 10.0, "stato_detrazione_iva": "DA_INSERIRE"}))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=2, today=OGGI))
    assert "nessun_corrispettivo_nel_mese" not in snap["motivi"]
    assert "giorni_senza_corrispettivo" not in snap["motivi"]
    assert snap["stato_calcolo"] == "CALCOLATA"
    assert snap["iva_vendite"] == 0.0
    assert snap["saldo"] == -10.0


def test_mese_chiuso_solo_in_parte_resta_dati_mancanti():
    db = _db("iva-chiusura-parziale")
    _run(registra_chiusura(db, "2026-02-01", "2026-02-20", "ristrutturazione", "titolare"))
    _run(db.invoices.insert_one({"id": "f", "periodo_iva_attribuito": "2026-02",
                                 "iva_detraibile": 10.0, "stato_detrazione_iva": "DA_INSERIRE"}))
    snap = _run(get_iva_period_snapshot(db, anno=2026, mese=2, today=OGGI))
    assert "nessun_corrispettivo_nel_mese" in snap["motivi"]
    assert snap["stato_calcolo"] == "DATI_MANCANTI"


def test_riepilogo_annuale_legge_solo_fatture_attive():
    db = _db("iva-annuale-attive")
    _run(db.invoices.insert_many([
        {"id": "a", "periodo_iva_attribuito": "2026-03", "iva_detraibile": 10.0,
         "stato_detrazione_iva": "DA_INSERIRE"},
        {"id": "b", "periodo_iva_attribuito": "2026-03", "iva_detraibile": 10.0,
         "stato_detrazione_iva": "DA_INSERIRE", "status": "archived"},
        {"id": "c", "periodo_iva_attribuito": "2026-03", "iva_detraibile": 10.0,
         "stato_detrazione_iva": "DA_INSERIRE", "stato_import": "archivio_storico"},
    ]))
    fatture = _run(iva_router._fatture_anno(db, 2026))
    assert [f["id"] for f in fatture] == ["a"]


def test_dashboard_mensile_nota_credito_in_negativo(monkeypatch):
    db = _db("iva-dashboard-nc")
    _mese_pieno(db, "2026-04", 30)
    _run(db.invoices.insert_many([
        {"id": "f", "periodo_iva_attribuito": "2026-04", "iva": 100.0, "iva_detraibile": 100.0,
         "stato_detrazione_iva": "DA_INSERIRE"},
        {"id": "nc", "periodo_iva_attribuito": "2026-04", "iva": 30.0, "iva_detraibile": 30.0,
         "stato_detrazione_iva": "DA_INSERIRE", "tipo_documento": "TD04"},
        {"id": "arch", "periodo_iva_attribuito": "2026-04", "iva": 500.0, "iva_detraibile": 500.0,
         "stato_detrazione_iva": "DA_INSERIRE", "status": "archived"},
    ]))
    monkeypatch.setattr(iva_router.Database, "get_db", staticmethod(lambda: db))
    funzione = getattr(iva_router.dashboard_iva_mensile, "__wrapped__", iva_router.dashboard_iva_mensile)
    esito = _run(funzione(2026, 4))
    assert esito["iva_acquisti_attribuita"] == 70.0
    assert esito["iva_non_utilizzata"] == 70.0
