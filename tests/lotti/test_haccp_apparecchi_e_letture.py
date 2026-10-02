"""Blocco 3 dell'audit Lotti: apparecchi veri, pagine che non scrivono,
stati del registro distinti, turno sull'ora di Roma.

- le schede di un anno sono quelle degli apparecchi censiti (anche oltre il
  12) più chi ha rilevazioni; un apparecchio eliminato senza storia sparisce;
- aprire la pagina temperature o la lista attrezzature non crea documenti;
- «conforme» dichiarato dal responsabile non è più «da rilevare»;
- il turno delle 07:00 crea la scheda dell'anno che manca (a gennaio);
- il filtro per data dei lotti non si perde oltre i primi 1.000.
"""
import asyncio
from datetime import datetime

import pytest
from mongomock_motor import AsyncMongoMockClient


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    database = AsyncMongoMockClient()["blocco3"]
    import app.lotti.routers.attrezzature as attr
    import app.lotti.routers.haccp_auto as ha
    import app.lotti.routers.lotti as lotti
    import app.lotti.routers.sanificazione as san
    import app.lotti.routers.temperature_negative as tn
    import app.lotti.routers.temperature_positive as tp
    import app.lotti.servizi.schede_temperature as st

    for modulo in (attr, ha, lotti, san, tn, tp, st):
        monkeypatch.setattr(modulo, "db", database)
    return database


def _censisci(db, tipo, numeri, **extra):
    _run(db.attrezzature_config.insert_many([
        {"tipo": tipo, "numero": n, "nome": f"{tipo} {n}", "attivo": True, **extra} for n in numeri
    ]))


def test_schede_anno_seguono_gli_apparecchi_censiti(db):
    from app.lotti.routers import temperature_positive as tp

    _censisci(db, "frigo", [1, 2, 13])
    _run(db.attrezzature_config.insert_one({"tipo": "frigo", "numero": 3, "nome": "dismesso", "attivo": False}))
    _run(db.attrezzature_config.insert_one({"tipo": "frigo", "numero": 4, "nome": "dismesso con storia", "attivo": False}))
    _run(db.temperature_positive.insert_one({
        "anno": 2026, "frigorifero_numero": 4, "temperature": {"7": {"3": {"temp": 3.0}}}}))

    schede = _run(tp.get_tutte_schede(2026))
    numeri = [s["frigorifero_numero"] for s in schede]
    assert numeri == [1, 2, 4, 13]  # 13 c'è, 3 (eliminato, senza storia) no
    assert [s["attivo"] for s in schede] == [True, True, False, True]
    # Aprire la pagina non ha creato niente.
    assert _run(db.temperature_positive.count_documents({})) == 1


def test_get_scheda_singola_non_crea(db):
    from app.lotti.routers import temperature_negative as tn

    scheda = _run(tn.get_scheda_congelatore(2026, 7))
    assert scheda["congelatore_numero"] == 7 and scheda["temperature"]["1"] == {}
    assert _run(db.temperature_negative.count_documents({})) == 0


def test_lista_attrezzature_non_scrive(db):
    from app.lotti.routers import attrezzature as attr

    _run(db.temperature_positive.insert_one({"anno": 2026, "frigorifero_numero": 5, "temperature": {}}))
    risposta = _run(attr.get_attrezzature())
    assert [f["numero"] for f in risposta["frigoriferi"]] == [5]  # letto, non censito
    assert _run(db.attrezzature_config.count_documents({})) == 0


def test_sanificazione_usa_i_nomi_canonici_degli_apparecchi(db):
    from app.lotti.routers import sanificazione as san

    _run(db.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 5, "nome": "FRIGO PASTICCERIA 5", "attivo": True},
        {"tipo": "congelatore", "numero": 1, "nome": "CONGELATORE PASTICCERIA 1", "attivo": True},
    ]))
    _run(db.sanificazione_apparecchi.insert_one({
        "anno": 2026,
        "registrazioni_frigoriferi": {"8": [{"mese": 1, "giorno": 1, "eseguita": True}]},
        "registrazioni_congelatori": {"11": [{"mese": 1, "giorno": 1, "eseguita": True}]},
    }))

    scheda = _run(san.get_scheda_apparecchi(2026))
    assert scheda["apparecchi_frigoriferi"] == [
        {"numero": 5, "nome": "FRIGO PASTICCERIA 5"},
    ]
    assert scheda["apparecchi_congelatori"] == [
        {"numero": 1, "nome": "CONGELATORE PASTICCERIA 1"},
    ]
    assert _run(san.get_sanificazioni_frigorifero(2026, 5))["nome"] == "FRIGO PASTICCERIA 5"
    assert _run(san.get_sanificazioni_congelatore(2026, 1))["nome"] == "CONGELATORE PASTICCERIA 1"


def test_turno_crea_la_scheda_mancante_e_apre_la_casella(db):
    from app.lotti.routers import haccp_auto as ha
    from app.lotti.servizi.registro_haccp import FUSO

    _censisci(db, "frigo", [1], operatore_id="op-1", operatore_nome="Anna")
    quando = datetime(2027, 1, 1, 7, 0, tzinfo=FUSO)
    esito = _run(ha.apri_rilevazioni_del_giorno(quando))
    assert esito["aperte"] == 1
    scheda = _run(db.temperature_positive.find_one({"anno": 2027, "frigorifero_numero": 1}))
    casella = scheda["temperature"]["1"]["1"]
    assert casella["temp"] is None and casella["stato"] == ha.STATO_DA_RILEVARE


def test_turno_oggi_conta_il_conforme_come_fatto(db, monkeypatch):
    from app.lotti.routers import haccp_auto as ha
    from app.lotti.servizi.registro_haccp import FUSO

    adesso = datetime.now(FUSO)
    m, g = str(adesso.month), str(adesso.day)
    _run(db.temperature_positive.insert_many([
        {"anno": adesso.year, "frigorifero_numero": 1,
         "temperature": {m: {g: {"temp": None, "stato": ha.STATO_CONFORME, "esito": "conforme"}}}},
        {"anno": adesso.year, "frigorifero_numero": 2,
         "temperature": {m: {g: {"temp": None, "stato": ha.STATO_DA_RILEVARE}}}},
        {"anno": adesso.year, "frigorifero_numero": 3,
         "temperature": {m: {g: {"temp": 3.2}}}},
    ]))
    turno = _run(ha.turno_di_oggi())
    assert turno["gia_rilevate"] == 2
    assert [d["numero"] for d in turno["da_rilevare"]] == [2]


def test_filtro_data_lotti_oltre_il_tetto(db):
    from app.lotti.routers import lotti

    recenti = [{"id": f"r{i}", "prodotto": "Cornetto", "data_produzione": "20/09/2026",
                "created_at": f"2026-09-20T10:{i % 60:02d}:00"} for i in range(30)]
    vecchio = {"id": "v1", "prodotto": "Pastiera", "data_produzione": "10/01/2026",
               "created_at": "2026-01-10T08:00:00"}
    _run(db.lotti.insert_many(recenti + [vecchio]))
    trovati = _run(lotti.get_lotti(search=None, data_da="01/01/2026", data_a="31/01/2026", limit=5))
    assert [t["id"] for t in trovati] == ["v1"]


def test_ricerca_lotti_testo_non_regex(db):
    from app.lotti.routers import lotti

    _run(db.lotti.insert_many([{"id": "a", "prodotto": "Babà (grande)", "created_at": "1"},
                               {"id": "b", "prodotto": "Babà grande", "created_at": "2"}]))
    trovati = _run(lotti.get_lotti(search="(grande)", data_da=None, data_a=None, limit=10))
    assert [t["id"] for t in trovati] == ["a"]
