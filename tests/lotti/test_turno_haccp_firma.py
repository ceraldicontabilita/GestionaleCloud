"""Guardia: il turno del mattino apre il lavoro, e a firmare e' il PIN.

Il titolare chiede che alle 07:00 il sistema prepari le registrazioni di
temperatura su tutti i frigoriferi, col nome del dipendente assegnato. Qui
c'e' la riga che divide il registro vero dal falso: il sistema apre la casella
e ci scrive CHI deve rilevare, ma **non scrive la temperatura**. Quella la
mette la persona dal tablet, col proprio PIN.

Fino al 20/09/2026 il sistema la scriveva da solo, sorteggiata dentro le
soglie e firmata sorteggiando fra sei dipendenti: 384 rilevazioni del 2026
nate cosi'.

Il PIN e' gia' unico per tutte le app del gruppo — la fonte e' `pin_hash`
sulla scheda HR, lo stesso PIN del portale dipendenti — quindi non c'e' un
secondo elenco da tenere allineato.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def archivio(monkeypatch):
    import app.lotti.routers.attrezzature as attrezzature
    import app.lotti.routers.haccp_auto as haccp

    db = AsyncMongoMockClient()["Lotti_Test"]
    monkeypatch.setattr(haccp, "db", db)
    monkeypatch.setattr(attrezzature, "db", db)

    oggi = datetime.now(timezone.utc)
    run(db.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 1, "nome": "Frigorifero N°1", "attivo": True,
         "operatore_id": "hr-7", "operatore_nome": "Pocci Salvatore"},
        {"tipo": "frigo", "numero": 2, "nome": "Frigorifero N°2", "attivo": True},
        {"tipo": "congelatore", "numero": 1, "nome": "Congelatore N°1", "attivo": True,
         "operatore_id": "hr-9", "operatore_nome": "Moscato Antonio"},
    ]))
    run(db.temperature_positive.insert_many([
        {"anno": oggi.year, "frigorifero_numero": 1, "frigorifero_nome": "Frigorifero N°1",
         "temperature": {str(m): {} for m in range(1, 13)}, "temp_min": 0, "temp_max": 4},
        {"anno": oggi.year, "frigorifero_numero": 2, "frigorifero_nome": "Frigorifero N°2",
         "temperature": {str(m): {} for m in range(1, 13)}, "temp_min": 0, "temp_max": 4},
    ]))
    run(db.temperature_negative.insert_one(
        {"anno": oggi.year, "congelatore_numero": 1, "congelatore_nome": "Congelatore N°1",
         "temperature": {str(m): {} for m in range(1, 13)}, "temp_min": -22, "temp_max": -18}
    ))
    return db, oggi


# ── Il turno delle 07:00 ─────────────────────────────────────────────────────

def test_il_turno_apre_una_casella_per_apparecchio_senza_scrivere_la_temperatura(archivio):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    db, oggi = archivio
    esito = run(apri_rilevazioni_del_giorno())

    assert esito["aperte"] == 3, "un frigorifero o congelatore attivo, una casella"

    scheda = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))
    casella = scheda["temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["temp"] is None, (
        "Il sistema ha scritto una temperatura: quella la misura una persona. "
        "Un valore generato e firmato e' un falso documentale."
    )
    assert casella["stato"] == "da_rilevare"
    assert casella["operatore_nome"] == "Pocci Salvatore"
    assert casella["operatore_id"] == "hr-7"


def test_il_turno_segnala_gli_apparecchi_senza_responsabile(archivio):
    """Il Frigorifero N°2 non e' assegnato: il suo registro restera' senza firma."""
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    esito = run(apri_rilevazioni_del_giorno())

    assert esito["senza_responsabile"] == ["Frigorifero N°2"], (
        "Un apparecchio senza responsabile deve saltare fuori subito, non a "
        "fine mese quando il registro e' gia' pieno di buchi."
    )


def test_il_turno_non_tocca_una_rilevazione_gia_fatta(archivio):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    db, oggi = archivio
    vera = {"temp": 2.4, "operatore": "Parisi Ciro", "firma_verificata": True}
    run(db.temperature_positive.update_one(
        {"frigorifero_numero": 1},
        {"$set": {f"temperature.{oggi.month}.{oggi.day}": vera}},
    ))

    esito = run(apri_rilevazioni_del_giorno())

    scheda = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))
    assert scheda["temperature"][str(oggi.month)][str(oggi.day)]["temp"] == 2.4, (
        "Il turno ha cancellato una misura vera: non deve mai sovrascrivere."
    )
    assert esito["gia_presenti"] == 1


def test_il_turno_e_idempotente(archivio):
    """Girato due volte (riavvio, catchup) non raddoppia niente."""
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    primo = run(apri_rilevazioni_del_giorno())
    secondo = run(apri_rilevazioni_del_giorno())

    assert primo["aperte"] == 3
    assert secondo["aperte"] == 0 and secondo["gia_presenti"] == 3


def test_il_turno_dice_cosa_resta_da_fare(archivio):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno, turno_di_oggi

    run(apri_rilevazioni_del_giorno())
    turno = run(turno_di_oggi())

    assert turno["quante_da_rilevare"] == 3
    nomi = {r["operatore_nome"] for r in turno["da_rilevare"]}
    assert "Pocci Salvatore" in nomi and "Moscato Antonio" in nomi


# ── La firma ─────────────────────────────────────────────────────────────────

def test_senza_pin_la_rilevazione_resta_non_firmata(monkeypatch):
    from app.lotti.servizi.firma_dipendente import firma_da_pin

    firma = run(firma_da_pin("", "Tizio Qualunque"))

    assert firma["firma_verificata"] is False
    assert firma["operatore"] == "Tizio Qualunque"
    assert firma["dipendente_id"] == ""


def test_col_pin_il_nome_lo_mette_l_anagrafica(monkeypatch):
    """Non quello scritto nella query: il registro non puo' portare un nome
    che in azienda e' scritto in un altro modo, o che non esiste."""
    from app.lotti.servizi import firma_dipendente

    async def per_pin(_pin, solo_operatori_lotti=False):
        assert solo_operatori_lotti is True
        return [{"id": "hr-7", "cognome": "Pocci", "nome": "Salvatore"}]

    monkeypatch.setattr(
        "app.hr.services.auth_dipendenti.trova_dipendente_per_pin", per_pin
    )

    firma = run(firma_dipendente.firma_da_pin("1234", "chiunque"))

    assert firma == {
        "operatore": "Pocci Salvatore",
        "dipendente_id": "hr-7",
        "firma_verificata": True,
    }


def test_rilevazioni_firmate_salvano_id_dipendente(archivio, monkeypatch):
    import app.lotti.routers.temperature_positive as positive
    import app.lotti.routers.temperature_negative as negative
    from app.lotti.servizi import firma_dipendente

    db, oggi = archivio
    monkeypatch.setattr(positive, "db", db)
    monkeypatch.setattr(negative, "db", db)

    async def firma(_pin, _nome):
        return {"operatore": "Pocci Salvatore", "dipendente_id": "hr-7", "firma_verificata": True}

    monkeypatch.setattr(firma_dipendente, "firma_da_pin", firma)
    run(positive.registra_temperatura(oggi.year, 1, oggi.month, oggi.day,
                                     temperatura=2.0, operatore="", pin="1234", note="", azione_correttiva=""))
    run(negative.registra_temperatura(oggi.year, 1, oggi.month, oggi.day,
                                     temperatura=-20.0, operatore="", pin="1234", note=""))
    for collection, campo in ((db.temperature_positive, "frigorifero_numero"),
                              (db.temperature_negative, "congelatore_numero")):
        scheda = run(collection.find_one({campo: 1}))
        record = scheda["temperature"][str(oggi.month)][str(oggi.day)]
        assert record["dipendente_id"] == "hr-7"
        assert "operatore_id" not in record


def test_un_pin_sbagliato_non_registra_niente(monkeypatch):
    """Meglio una registrazione mancante che una firmata da nessuno."""
    from app.lotti.servizi import firma_dipendente

    async def nessuno(_pin, solo_operatori_lotti=False):
        return []

    monkeypatch.setattr(
        "app.hr.services.auth_dipendenti.trova_dipendente_per_pin", nessuno
    )

    with pytest.raises(HTTPException) as errore:
        run(firma_dipendente.firma_da_pin("0000", "Pocci Salvatore"))

    assert errore.value.status_code == 401


def test_un_pin_di_due_persone_non_sceglie_a_caso(monkeypatch):
    from app.lotti.servizi import firma_dipendente

    async def due(_pin, solo_operatori_lotti=False):
        return [{"id": "hr-7", "nome": "Uno"}, {"id": "hr-9", "nome": "Due"}]

    monkeypatch.setattr(
        "app.hr.services.auth_dipendenti.trova_dipendente_per_pin", due
    )

    with pytest.raises(HTTPException) as errore:
        run(firma_dipendente.firma_da_pin("1111"))

    assert errore.value.status_code == 409


def test_il_pin_non_finisce_mai_nel_record():
    """La firma non conserva il PIN: serve a riconoscere, poi si butta."""
    import inspect

    from app.lotti.servizi import firma_dipendente

    sorgente = inspect.getsource(firma_dipendente.firma_da_pin)
    assert '"pin"' not in sorgente and "'pin'" not in sorgente, (
        "Il PIN comparirebbe in un campo salvato."
    )


def test_una_chiamata_diretta_senza_pin_non_esplode():
    """FastAPI risolve i default `Query(...)` solo passando dal router.

    Chiamata da codice, `pin` arriva come oggetto `Query`: prima faceva
    `AttributeError: 'Query' object has no attribute 'strip'` e la
    registrazione della temperatura falliva del tutto — compreso il caso in
    cui il frigorifero era fuori soglia e l'allarme andava scritto.
    """
    from fastapi import Query

    from app.lotti.servizi.firma_dipendente import firma_da_pin

    firma = run(firma_da_pin(Query(default=""), "Mario"))

    assert firma["firma_verificata"] is False
    assert firma["operatore"] == "Mario"


# ── Il controllo del responsabile ────────────────────────────────────────────

@pytest.fixture()
def responsabile(monkeypatch, archivio):
    """Il titolare dichiara di eseguire lui il controllo visivo, ogni 2 ore."""
    import app.lotti.routers.haccp_auto as haccp

    async def azienda():
        return {
            "responsabile_haccp": "Ceraldi Vincenzo",
            "controllo_visivo_responsabile": "true",
            "controllo_visivo_ogni_ore": "2",
        }

    monkeypatch.setattr("app.lotti.azienda.get_azienda", azienda)
    return archivio


def test_il_turno_non_dichiara_conforme_niente(responsabile):
    """Col controllo visivo attivo, alle 07:00 il turno apre solo le caselle.

    Prima scriveva «conforme» firmato dal responsabile su ogni apparecchio,
    prima che qualcuno avesse fatto il giro.
    """
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    db, oggi = responsabile
    run(apri_rilevazioni_del_giorno())
    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["stato"] == "da_rilevare"
    assert "esito" not in casella and "operatore" not in casella


def test_il_responsabile_dichiara_l_esito_dopo_il_giro_firmato(responsabile, monkeypatch):
    """L'esito del controllo visivo, firmato da chi l'ha fatto e all'ora vera."""
    import app.lotti.auth as auth
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno, dichiara_conformi_oggi

    db, oggi = responsabile
    run(apri_rilevazioni_del_giorno())
    monkeypatch.setattr(auth, "request_actor", lambda _r: {
        "id": "hr-1", "nome": "Ceraldi Vincenzo", "ruolo": "amministratore", "via": "pin"})
    esito = run(dichiara_conformi_oggi(request=object(), pin=""))
    assert esito["dichiarate"] == 3

    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["temp"] is None, "nessun numero inventato"
    assert casella["esito"] == "conforme"
    assert casella["soglie"] == {"min": 0, "max": 4}, "le soglie vere della scheda"
    assert casella["operatore"] == "Ceraldi Vincenzo"
    assert casella["firma_verificata"] is True
    assert "controllo visivo" in casella["metodo"]


def test_senza_firma_verificata_non_si_dichiara_niente(responsabile, monkeypatch):
    import app.lotti.auth as auth
    from app.lotti.routers.haccp_auto import dichiara_conformi_oggi

    monkeypatch.setattr(auth, "request_actor", lambda _r: None)
    with pytest.raises(HTTPException) as e:
        run(dichiara_conformi_oggi(request=object(), pin=""))
    assert e.value.status_code == 401


def test_la_dichiarazione_non_copre_una_temperatura_vera(responsabile, monkeypatch):
    import app.lotti.auth as auth
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno, dichiara_conformi_oggi

    db, oggi = responsabile
    run(apri_rilevazioni_del_giorno())
    run(db.temperature_positive.update_one(
        {"frigorifero_numero": 1},
        {"$set": {f"temperature.{oggi.month}.{oggi.day}": {"temp": 10.0, "allarme": True}}},
    ))
    monkeypatch.setattr(auth, "request_actor", lambda _r: {
        "id": "hr-1", "nome": "Ceraldi Vincenzo", "ruolo": "amministratore", "via": "pin"})
    assert run(dichiara_conformi_oggi(request=object(), pin=""))["dichiarate"] == 2
    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["temp"] == 10.0


def test_l_anomalia_trovata_sostituisce_la_conformita(responsabile):
    """Il frigo va a 10 gradi: il valore vero prende il posto della dichiarazione."""
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    db, oggi = responsabile
    run(apri_rilevazioni_del_giorno())
    run(db.temperature_positive.update_one(
        {"frigorifero_numero": 1},
        {"$set": {f"temperature.{oggi.month}.{oggi.day}": {
            "temp": 10.0, "allarme": True, "operatore": "Ceraldi Vincenzo",
            "azione_correttiva": "Fuori servizio, richiesta assistenza",
        }}},
    ))

    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["temp"] == 10.0 and casella["allarme"] is True
    # e un secondo giro del turno non la cancella
    run(apri_rilevazioni_del_giorno())
    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["temp"] == 10.0


def test_un_apparecchio_fuori_servizio_non_riceve_caselle(responsabile):
    """«Faccio fuori servizio»: da li' il registro non si riempie di giornate
    che nessuno poteva rilevare, e il motivo resta scritto."""
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    db, _oggi = responsabile
    run(db.attrezzature_config.update_one(
        {"tipo": "frigo", "numero": 1},
        {"$set": {"fuori_servizio": True, "fuori_servizio_motivo": "Guasto, assistenza richiesta"}},
    ))

    esito = run(apri_rilevazioni_del_giorno())

    assert esito["aperte"] == 2, "il frigorifero fermo non deve avere una casella"
