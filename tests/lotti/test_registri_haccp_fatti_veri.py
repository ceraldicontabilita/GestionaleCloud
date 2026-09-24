"""Frigoriferi, congelatori e sanificazione: il registro attesta solo fatti.

Stessa regola del calendario chiusure (niente fermi frigo inventati), estesa a
tutte le scritture dei tre registri:

- nessun giorno futuro;
- la firma e' una persona riconosciuta (PIN o sessione verificata), mai un
  nome fisso nel codice: la sanificazione scriveva sempre l'operatore
  designato e sempre «Detergente alimentare professionale», chiunque avesse
  pulito e con qualunque prodotto;
- una correzione non cancella il valore di prima;
- in stampa ogni riga porta chi l'ha firmata.
"""
import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi.registro_haccp import oggi_locale


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    import app.lotti.routers.report_haccp as report
    import app.lotti.routers.sanificazione as san
    import app.lotti.routers.temperature_negative as neg
    import app.lotti.routers.temperature_positive as pos

    database = AsyncMongoMockClient()["Lotti_Test"]
    for modulo in (pos, neg, san, report):
        monkeypatch.setattr(modulo, "db", database)
    return database


@pytest.fixture()
def sessione(monkeypatch):
    """Tablet con operatore entrato col PIN: la sessione e' la firma."""
    import app.lotti.auth as auth

    monkeypatch.setattr(auth, "request_actor", lambda _r: {
        "id": "hr-7", "nome": "Pocci Salvatore", "ruolo": "operatore", "via": "pin"})
    return object()


OGGI = oggi_locale()
DOMANI = OGGI + timedelta(days=1)


def test_niente_giorni_futuri_su_nessun_registro(db):
    from app.lotti.routers import sanificazione as san
    from app.lotti.routers import temperature_negative as neg
    from app.lotti.routers import temperature_positive as pos

    chiamate = [
        pos.registra_temperatura(DOMANI.year, 1, DOMANI.month, DOMANI.day, temperatura=3.0,
                                 operatore="", pin="", note="", azione_correttiva=""),
        neg.registra_temperatura(DOMANI.year, 1, DOMANI.month, DOMANI.day, temperatura=-20.0,
                                 operatore="", pin="", note=""),
        san.registra_sanificazione(DOMANI.year, DOMANI.month, DOMANI.day, "Pavimentazione",
                                   eseguita=True, operatore="", pin=""),
        san.registra_giorno_completo(DOMANI.year, DOMANI.month, DOMANI.day, operatore="", pin=""),
        san.registra_sanificazione_apparecchio(DOMANI.year, tipo="frigorifero", numero=1,
                                               giorno=DOMANI.day, mese=DOMANI.month, eseguita=True,
                                               note="", prodotto="", operatore="", pin=""),
    ]
    for chiamata in chiamate:
        with pytest.raises(HTTPException) as e:
            run(chiamata)
        assert e.value.status_code == 422


def test_riscrittura_intera_non_accetta_il_futuro(db):
    from app.lotti.routers import sanificazione as san
    from app.lotti.routers import temperature_positive as pos

    with pytest.raises(HTTPException):
        run(pos.aggiorna_scheda_completa(
            DOMANI.year, 1, pos.AggiornaTemperaturePositiveRequest(
                temperature={str(DOMANI.month): {str(DOMANI.day): {"temp": 3.0}}})))
    with pytest.raises(HTTPException):
        run(san.aggiorna_scheda_completa(
            DOMANI.year, DOMANI.month,
            san.AggiornaSchedaRequest(registrazioni={"Pavimentazione": {str(DOMANI.day): "X"}})))


def test_la_sessione_del_tablet_firma_la_temperatura(db, sessione):
    from app.lotti.routers import temperature_negative as neg

    run(neg.registra_temperatura(OGGI.year, 1, OGGI.month, OGGI.day, temperatura=-20.0,
                                 operatore="", pin="", note="", request=sessione))
    scheda = run(db.temperature_negative.find_one({"congelatore_numero": 1}))
    record = scheda["temperature"][str(OGGI.month)][str(OGGI.day)]
    assert record["operatore"] == "Pocci Salvatore"
    assert record["dipendente_id"] == "hr-7"
    assert record["firma_verificata"] is True


def test_una_correzione_conserva_il_valore_precedente(db, sessione):
    from app.lotti.routers import temperature_positive as pos

    for temp in (3.0, 5.5):
        run(pos.registra_temperatura(OGGI.year, 1, OGGI.month, OGGI.day, temperatura=temp,
                                     operatore="", pin="", note="", azione_correttiva="",
                                     request=sessione))
    scheda = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))
    record = scheda["temperature"][str(OGGI.month)][str(OGGI.day)]
    assert record["temp"] == 5.5
    assert record["sostituisce"][0]["temp"] == 3.0
    assert record["sostituisce"][0]["sostituito_da"] == "Pocci Salvatore"


def test_sanificazione_senza_operatore_ne_prodotto_inventati(db):
    from app.lotti.routers import sanificazione as san

    scheda = run(san.get_scheda_mensile(OGGI.year, OGGI.month))
    assert scheda["operatore_responsabile"] == ""

    run(san.registra_sanificazione_apparecchio(
        OGGI.year, tipo="congelatore", numero=2, giorno=OGGI.day, mese=OGGI.month,
        eseguita=True, note="", prodotto="", operatore="", pin=""))
    apparecchi = run(db.sanificazione_apparecchi.find_one({"anno": OGGI.year}))
    rec = apparecchi["registrazioni_congelatori"]["2"][0]
    assert rec["operatore"] == ""
    assert rec["prodotto"] == ""
    assert rec["firma_verificata"] is False
    assert san.OPERATORE_SANIFICAZIONE not in str(apparecchi)


def test_sanificazione_firmata_e_stampata_con_chi_l_ha_fatta(db, sessione):
    from app.lotti.routers import report_haccp
    from app.lotti.routers import sanificazione as san

    run(san.registra_sanificazione(OGGI.year, OGGI.month, OGGI.day, "Pavimentazione",
                                   eseguita=True, operatore="", pin="", request=sessione))
    run(san.registra_sanificazione(OGGI.year, OGGI.month, OGGI.day, "Deposito",
                                   eseguita=True, operatore="Qualcuno", pin="", request=None))
    run(san.registra_sanificazione_apparecchio(
        OGGI.year, tipo="frigorifero", numero=3, giorno=OGGI.day, mese=OGGI.month,
        eseguita=True, note="", prodotto="Sgrassatore X", operatore="", pin="", request=sessione))

    righe = run(report_haccp.load_sanificazioni(OGGI.year, OGGI.month))
    per_area = {r["area"]: r for r in righe}
    assert per_area["Pavimentazione"]["operatore"] == "Pocci Salvatore"
    assert per_area["Deposito"]["operatore"] == "Qualcuno (non verificata)"
    # prima le sanificazioni degli apparecchi sparivano dal report
    frigo = [r for r in righe if r["area"].startswith("Frigorifero")]
    assert frigo and frigo[0]["prodotto"] == "Sgrassatore X"
    assert frigo[0]["operatore"] == "Pocci Salvatore"


def test_congelatore_fuori_soglia_chiede_e_registra_l_azione_correttiva(db, sessione):
    from app.lotti.routers import temperature_negative as neg

    esito = run(neg.registra_temperatura(OGGI.year, 1, OGGI.month, OGGI.day, temperatura=-10.0,
                                         operatore="", pin="", note="", request=sessione))
    assert esito["allarme"] is True and esito["serve_azione_correttiva"] is True
    run(neg.registra_temperatura(OGGI.year, 1, OGGI.month, OGGI.day, temperatura=-10.0,
                                 operatore="", pin="", note="",
                                 azione_correttiva="Merce spostata in altro congelatore",
                                 request=sessione))
    record = run(db.temperature_negative.find_one({"congelatore_numero": 1}))[
        "temperature"][str(OGGI.month)][str(OGGI.day)]
    assert record["azione_correttiva"] == "Merce spostata in altro congelatore"
