"""Collaudo funzionale: la copia serale RT che si ferma e i giorni di chiusura.

CLAUDE.md: «Se quel programma si ferma nessuno se ne accorge [...]. Il segnale da
guardare e' l'ultima giornata in `corrispettivi`: `fonti_ferme.py` avvisa (anche
su Telegram, una volta) dopo **2 giorni d'apertura** senza chiusura RT, tolte le
`chiusure_attivita`». Giorni di chiusura: ristrutturazione 26/01-08/03/2026 e
ferie 15-23/08/2026 non sono corrispettivi mancanti — ne' per l'avviso, ne' per
la liquidazione IVA, ne' per la completezza del pacchetto del commercialista.
"""
from datetime import date

import pytest

from app.services import fonti_ferme
from app.services.chiusure_attivita import giorni_chiusi, semina_periodi_confermati
from app.services.completezza_commercialista import chiusure_rt_mancanti
from app.services.iva_liquidation_query import corrispettivi_periodo

from ._comune import Importatore, nuovo_db, righe, run, xml_chiusura


@pytest.fixture
def telegram(monkeypatch):
    inviati = []

    async def finto_invio(testo, **_kw):
        inviati.append(testo)
        return {"success": True}

    monkeypatch.setattr("app.services.telegram_notifications.send_notification", finto_invio)
    return inviati


def _chiusura_rt(imp, giorno, progressivo):
    imp.importa(f"{progressivo}.xml", xml_chiusura(data=giorno, progressivo=progressivo))


def _controlla(db, oggi):
    return run(fonti_ferme.controlla_fonti_ferme(db, oggi=oggi))


def _ferme(esito):
    return {r["fonte"]: r for r in esito["ferme"]}


def _alert(db):
    return run(righe(db, "alerts", {"codice": "FONTE_CONTABILE_FERMA", "entita_id": "corrispettivi"}))


# ── la copia serale si ferma ────────────────────────────────────────────────

def test_dopo_due_giorni_d_apertura_senza_chiusura_avvisa_una_volta_e_poi_si_chiude(monkeypatch, telegram):
    db = nuovo_db("s8_ferma")
    imp = Importatore(db, monkeypatch)
    _chiusura_rt(imp, "2026-09-21", "2651")                  # ultima chiusura arrivata: 21/09

    # 22 e 23 settembre: due giorni d'apertura, ancora nella norma.
    assert "corrispettivi" not in _ferme(_controlla(db, date(2026, 9, 22)))
    assert "corrispettivi" not in _ferme(_controlla(db, date(2026, 9, 23)))
    assert _alert(db) == [] and telegram == []

    # 24 settembre: tre giorni senza chiusura. Avviso, con ultima data e giorni.
    ferma = _ferme(_controlla(db, date(2026, 9, 24)))["corrispettivi"]
    assert ferma["ultima_data"] == "2026-09-21" and ferma["giorni"] == 3
    (alert,) = _alert(db)
    assert alert["stato"] == "aperto" and "21/09/2026" in alert["dettaglio"]
    # Un solo messaggio Telegram, anche se il giro riparte.
    _controlla(db, date(2026, 9, 24))
    _controlla(db, date(2026, 9, 25))
    assert len(telegram) == 1 and len(_alert(db)) == 1

    # Il programma sul PC riparte: arriva la chiusura del 24/09 -> l'avviso si chiude da solo.
    _chiusura_rt(imp, "2026-09-24", "2654")
    esito = _controlla(db, date(2026, 9, 25))
    assert "corrispettivi" in esito["riprese"] and "corrispettivi" not in _ferme(esito)
    assert _alert(db)[0]["stato"] == "risolto"
    # Il segnale e' l'ULTIMA giornata: la chiusura del 24 sposta il riferimento.
    riga = next(r for r in run(fonti_ferme.stato_fonti(db, oggi=date(2026, 9, 25))) if r["fonte"] == "corrispettivi")
    assert riga["ultima_data"] == "2026-09-24" and riga["giorni_fermi"] == 1 and riga["ferma"] is False


def test_la_coda_drive_vuota_non_e_il_segnale_conta_l_ultima_giornata(monkeypatch, telegram):
    """Nessun file in attesa su Drive non prova niente: guarda `corrispettivi`.
    Con una giornata fresca non c'e' avviso, qualunque sia lo stato della coda."""
    db = nuovo_db("s8_coda")
    imp = Importatore(db, monkeypatch)
    _chiusura_rt(imp, "2026-09-23", "2653")
    assert "corrispettivi" not in _ferme(_controlla(db, date(2026, 9, 24)))
    assert telegram == []


# ── giorni di chiusura attivita' ────────────────────────────────────────────

def test_i_periodi_confermati_dal_titolare_sono_giorni_di_chiusura():
    db = nuovo_db("s8_registro")
    assert run(semina_periodi_confermati(db)) == 2
    assert run(semina_periodi_confermati(db)) == 0                  # idempotente

    chiusi = run(giorni_chiusi(db, "2026-01-01", "2026-12-31"))
    assert {"2026-01-26", "2026-02-14", "2026-03-08"} <= chiusi      # ristrutturazione, estremi compresi
    assert {"2026-08-15", "2026-08-19", "2026-08-23"} <= chiusi      # ferie, estremi compresi
    for aperto in ("2026-01-25", "2026-03-09", "2026-08-14", "2026-08-24"):
        assert aperto not in chiusi
    assert len([g for g in chiusi if g.startswith("2026-08")]) == 9
    assert len([g for g in chiusi if g < "2026-03-09"]) == 42        # 26/01 -> 08/03


@pytest.mark.parametrize("oggi,avvisa", [
    (date(2026, 8, 25), False),    # ferie 15-23: restano il 24 e il 25 -> 2 giorni, norma
    (date(2026, 8, 26), True),     # il 24, 25 e 26 senza chiusura: 3 giorni
])
def test_le_ferie_di_agosto_non_sono_giorni_senza_chiusura(monkeypatch, telegram, oggi, avvisa):
    db = nuovo_db("s8_ferie")
    imp = Importatore(db, monkeypatch)
    run(semina_periodi_confermati(db))
    _chiusura_rt(imp, "2026-08-14", "2630")                          # ultima prima delle ferie

    assert ("corrispettivi" in _ferme(_controlla(db, oggi))) is avvisa
    assert bool(telegram) is avvisa


@pytest.mark.parametrize("oggi,avvisa", [
    (date(2026, 3, 10), False),    # 26/01-08/03 chiuso: restano il 9 e il 10
    (date(2026, 3, 11), True),
])
def test_la_ristrutturazione_di_inverno_non_e_una_fonte_ferma(monkeypatch, telegram, oggi, avvisa):
    db = nuovo_db("s8_ristrutturazione")
    imp = Importatore(db, monkeypatch)
    run(semina_periodi_confermati(db))
    _chiusura_rt(imp, "2026-01-25", "2480")

    assert ("corrispettivi" in _ferme(_controlla(db, oggi))) is avvisa
    assert bool(telegram) is avvisa


def test_senza_il_registro_delle_chiusure_le_stesse_ferie_sarebbero_un_avviso(monkeypatch, telegram):
    """Prova in negativo: e' il registro a spegnere l'avviso, non un ritardo di tolleranza."""
    db = nuovo_db("s8_senza_registro")
    imp = Importatore(db, monkeypatch)
    _chiusura_rt(imp, "2026-08-14", "2630")
    assert "corrispettivi" in _ferme(_controlla(db, date(2026, 8, 25)))


def _giornata(db, giorno, iva="90.91"):
    run(db["corrispettivi"].insert_one({
        "id": f"c-{giorno}", "data": giorno, "corrispettivo_key": f"k-{giorno}", "totale": 1000.0,
        "totale_iva": float(iva), "stato": "definitivo_xml", "status": "imported"}))


def test_la_liquidazione_iva_non_conta_le_ferie_fra_i_giorni_senza_corrispettivo():
    db = nuovo_db("s8_iva")
    run(semina_periodi_confermati(db))
    for g in range(1, 32):
        giorno = f"2026-08-{g:02d}"
        if 15 <= g <= 23 or g == 12:           # ferie, e un 12 agosto davvero dimenticato
            continue
        _giornata(db, giorno)

    mese = run(corrispettivi_periodo(db, "2026-08"))

    assert mese["giorni_senza_corrispettivo"] == ["2026-08-12"]          # solo il buco vero
    assert mese["giorni_chiusura"] == [f"2026-08-{g}" for g in range(15, 24)]
    assert mese["giorni_con_corrispettivo"] == 21


def test_la_completezza_del_pacchetto_non_chiede_le_chiusure_rt_delle_ferie():
    db = nuovo_db("s8_completezza")
    run(semina_periodi_confermati(db))
    for g in range(1, 32):
        if 15 <= g <= 23 or g == 12:
            continue
        _giornata(db, f"2026-08-{g:02d}")

    assert run(chiusure_rt_mancanti(db, "2026-08-01", "2026-08-31")) == ["2026-08-12"]


def test_una_giornata_ritirata_non_nasconde_un_fermo_vero(monkeypatch, telegram):
    """L'ultima giornata e' quella VIVA: una riga ritirata (status deleted) con una data piu'
    recente non e' una chiusura arrivata e non deve far tacere l'avviso."""
    db = nuovo_db("s8_ritirata")
    imp = Importatore(db, monkeypatch)
    _chiusura_rt(imp, "2026-09-21", "2651")
    run(db["corrispettivi"].insert_one({
        "id": "ritirata", "data": "2026-09-23", "totale": 500.0, "status": "deleted",
        "deleted_reason": "sostituita_da_chiusura_xml"}))

    ferma = _ferme(_controlla(db, date(2026, 9, 25)))["corrispettivi"]

    assert ferma["ultima_data"] == "2026-09-21" and ferma["giorni"] == 4


def test_la_liquidazione_iva_non_conta_le_giornate_archiviate():
    """In archivio convivono `archived` e `archiviata` (regola 13): un filtro che ne
    conosce una sola conta l'IVA di una giornata che i ricavi escludono."""
    db = nuovo_db("s8_archiviata")
    _giornata(db, "2026-08-01")
    run(db["corrispettivi"].insert_one({
        "id": "storica", "data": "2026-08-02", "corrispettivo_key": "k-storica", "totale": 1000.0,
        "totale_iva": 90.91, "status": "archiviata"}))

    mese = run(corrispettivi_periodo(db, "2026-08"))

    assert mese["corrispettivi_inclusi"] == 1 and mese["iva_vendite_cents"] == 9091
    assert "2026-08-02" in mese["giorni_senza_corrispettivo"]
