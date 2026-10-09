import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def archivio(monkeypatch):
    import app.lotti.routers.haccp_auto as haccp

    db = AsyncMongoMockClient()["Lotti_Attestazione_Test"]
    monkeypatch.setattr(haccp, "db", db)
    return db


def _temperature_vuote():
    return {str(mese): {} for mese in range(1, 13)}


def test_storico_popola_conformita_senza_inventare_gradi_e_non_copre_anomalie(archivio):
    from app.lotti.routers.haccp_auto import applica_attestazione_storica

    temperature = _temperature_vuote()
    temperature["1"] = {
        "1": None,
        "2": 2.5,
        "3": {"temp": 10.0, "allarme": True, "note": "anomalia vera"},
    }
    run(archivio.temperature_positive.insert_one({
        "anno": 2023,
        "frigorifero_numero": 1,
        "temperature": temperature,
        "temp_min": 0,
        "temp_max": 4,
    }))
    attore = {"id": "titolare-1", "nome": "Titolare", "ruolo": "amministratore", "via": "sessione_erp"}

    esito = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 3), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=False,
    ))

    assert esito["temperature_popolate"] == 1
    assert esito["misure_esistenti_attestate"] == 1
    assert esito["temperature_non_sovrascritte"] == 1
    doc = run(archivio.temperature_positive.find_one({"frigorifero_numero": 1}))
    giorno_1 = doc["temperature"]["1"]["1"]
    assert giorno_1["temp"] is None and giorno_1["stato"] == "conforme"
    assert giorno_1["firma_verificata"] is True
    assert giorno_1["firma_significato"] == "attestazione_veridicita_storica"
    assert doc["temperature"]["1"]["2"]["temp"] == 2.5
    assert doc["temperature"]["1"]["3"] == {
        "temp": 10.0, "allarme": True, "note": "anomalia vera"
    }


def test_attestazione_e_idempotente(archivio):
    from app.lotti.routers.haccp_auto import applica_attestazione_storica

    run(archivio.temperature_negative.insert_one({
        "anno": 2023,
        "congelatore_numero": 1,
        "temperature": _temperature_vuote(),
        "temp_min": -22,
        "temp_max": -18,
    }))
    attore = {"id": "titolare-1", "nome": "Titolare", "ruolo": "amministratore", "via": "sessione_erp"}
    primo = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 2), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=False,
    ))
    secondo = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 2), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=False,
    ))

    assert primo["temperature_popolate"] == 2
    assert secondo["idempotente"] is True
    assert secondo["temperature_popolate"] == 0
    assert secondo["misure_esistenti_attestate"] == 0


def test_attestazione_si_riapplica_dopo_una_nuova_importazione(archivio):
    from app.lotti.routers.haccp_auto import applica_attestazione_storica

    temperature = _temperature_vuote()
    temperature["1"]["1"] = {"temp": -20, "firma_verificata": False}
    run(archivio.temperature_negative.insert_one({
        "anno": 2023, "congelatore_numero": 1, "temperature": temperature,
        "temp_min": -22, "temp_max": -18,
    }))
    attore = {"id": "titolare-1", "nome": "Titolare", "ruolo": "amministratore", "via": "sessione_erp"}
    primo = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 1), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=False,
    ))
    attestazione_id = primo["attestazione_id"]

    # Simula la sostituzione della casella da parte di un import Excel successivo.
    run(archivio.temperature_negative.update_one(
        {"congelatore_numero": 1},
        {"$set": {"temperature.1.1": {"temp": -19, "firma_verificata": False}}},
    ))
    secondo = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 1), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=False,
    ))

    assert secondo["idempotente"] is False
    assert secondo["misure_esistenti_attestate"] == 1
    assert secondo["attestazione_id"] == attestazione_id
    doc = run(archivio.temperature_negative.find_one({"congelatore_numero": 1}))
    assert doc["temperature"]["1"]["1"]["firma_verificata"] is True


def test_sanificazioni_attesta_solo_le_x_esistenti_e_ripara_la_chiave_spezzata(archivio):
    from app.lotti.routers.haccp_auto import applica_attestazione_storica

    area = "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine"
    run(archivio.sanificazione_schede.insert_one({
        "anno": 2023,
        "mese": 1,
        "registrazioni": {
            "Lavabo, Macch": {
                "1": "X",
                "Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine": {"2": "X"},
            },
            "Pavimentazione": {"1": "X", "2": "N/D"},
        },
    }))
    attore = {"id": "titolare-1", "nome": "Titolare", "ruolo": "amministratore", "via": "sessione_erp"}
    esito = run(applica_attestazione_storica(
        date(2023, 1, 1), date(2023, 1, 2), attore, "Dichiarazione verificata",
        attesta_sanificazioni_registrate=True,
    ))

    assert esito["sanificazioni_attestate"] == 3
    assert esito["schede_sanificazione_riparate"] == 1
    doc = run(archivio.sanificazione_schede.find_one({"anno": 2023, "mese": 1}))
    assert "Lavabo, Macch" not in doc["registrazioni"]
    assert doc["registrazioni"][area] == {"1": "X", "2": "X"}
    assert doc["firme"][area]["1"]["firma_verificata"] is True
    assert "2" not in doc["firme"]["Pavimentazione"], "N/D non diventa una sanificazione eseguita"


def test_giro_ore_sette_usa_la_dichiarazione_e_non_sovrascrive_la_misura(archivio):
    from app.lotti.routers.haccp_auto import applica_dichiarazione_continua_oggi

    quando = datetime(2026, 10, 1, 7, 0, tzinfo=ZoneInfo("Europe/Rome"))
    run(archivio.impostazioni.insert_one({
        "_id": "haccp_attestazione_continua",
        "attivo": True,
        "firma_verificata": True,
        "attestazione_id": "att-1",
        "firmato_da": "Titolare",
        "firmatario_id": "titolare-1",
        "sottoscritta_il": "2026-10-01T06:00:00+00:00",
    }))
    run(archivio.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 1, "attivo": True},
        {"tipo": "frigo", "numero": 2, "attivo": True},
    ]))
    t1, t2 = _temperature_vuote(), _temperature_vuote()
    t1["10"]["1"] = {"temp": None, "stato": "da_rilevare"}
    t2["10"]["1"] = {"temp": 10.0, "allarme": True}
    run(archivio.temperature_positive.insert_many([
        {"anno": 2026, "frigorifero_numero": 1, "temperature": t1, "temp_min": 0, "temp_max": 4},
        {"anno": 2026, "frigorifero_numero": 2, "temperature": t2, "temp_min": 0, "temp_max": 4},
    ]))

    esito = run(applica_dichiarazione_continua_oggi(quando))
    assert esito["dichiarate"] == 1 and esito["gia_presenti"] == 1
    primo = run(archivio.temperature_positive.find_one({"frigorifero_numero": 1}))
    secondo = run(archivio.temperature_positive.find_one({"frigorifero_numero": 2}))
    assert primo["temperature"]["10"]["1"]["temp"] is None
    assert primo["temperature"]["10"]["1"]["stato"] == "conforme"
    assert secondo["temperature"]["10"]["1"]["temp"] == 10.0
