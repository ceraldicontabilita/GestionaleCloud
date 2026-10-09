"""Il titolare e' il responsabile di ogni apparecchio e firma con la sessione.

Decisione del titolare (02/10/2026): il responsabile di tutti i frigoriferi
e congelatori e' l'amministratore, che entra nel gestionale col PIN
amministratore e deve poter firmare le rilevazioni e dichiarare la
conformita' con quella sessione, senza un secondo PIN.

Nell'archivio vero i 24 apparecchi sono tutti senza `operatore_id`: dal 21/09
il turno apriva le caselle e le lasciava «senza responsabile», e nessuna si
poteva firmare perche' il token della sessione amministratore («erp:...»)
non era una persona.

Tre regole:
  - un apparecchio senza assegnazione e' del titolare, col nome scritto nelle
    Impostazioni (`responsabile_haccp`), mai cablato nel codice;
  - la sessione amministratore del Gestionale firma (`sessione_admin`);
  - un PIN sbagliato resta 401, e nessun numero si inventa.
"""
import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def archivio(monkeypatch):
    import app.lotti.routers.attrezzature as attrezzature
    import app.lotti.routers.haccp_auto as haccp
    import app.lotti.routers.temperature_negative as negative
    import app.lotti.routers.temperature_positive as positive
    from app.lotti.servizi.registro_haccp import FUSO

    db = AsyncMongoMockClient()["Lotti_Test"]
    for modulo in (haccp, attrezzature, positive, negative):
        monkeypatch.setattr(modulo, "db", db)
    oggi = datetime.now(FUSO)
    run(db.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 1, "nome": "Frigorifero N°1", "attivo": True},
        {"tipo": "frigo", "numero": 2, "nome": "Frigorifero N°2", "attivo": True,
         "operatore_id": "hr-7", "operatore_nome": "Pocci Salvatore"},
        {"tipo": "congelatore", "numero": 1, "nome": "Congelatore N°1", "attivo": True},
    ]))
    run(db.temperature_positive.insert_many([
        {"anno": oggi.year, "frigorifero_numero": n, "frigorifero_nome": f"Frigorifero N°{n}",
         "temperature": {str(m): {} for m in range(1, 13)}, "temp_min": 0, "temp_max": 4}
        for n in (1, 2)
    ]))
    run(db.temperature_negative.insert_one(
        {"anno": oggi.year, "congelatore_numero": 1, "congelatore_nome": "Congelatore N°1",
         "temperature": {str(m): {} for m in range(1, 13)}, "temp_min": -22, "temp_max": -18}
    ))
    return db, oggi


def _impostazioni(monkeypatch, responsabile="Ceraldi Vincenzo", controllo_visivo="si"):
    async def azienda():
        return {"responsabile_haccp": responsabile,
                "controllo_visivo_responsabile": controllo_visivo,
                "controllo_visivo_ogni_ore": "2"}

    monkeypatch.setattr("app.lotti.azienda.get_azienda", azienda)


def _sessione(monkeypatch, attore):
    import app.lotti.auth as auth

    monkeypatch.setattr(auth, "request_actor", lambda _r: attore)


SESSIONE_ADMIN_ANONIMA = {"id": "erp:utente-1", "nome": "Amministratore",
                          "ruolo": "amministratore", "via": "sessione_erp"}
SESSIONE_ADMIN_HR = {"id": "hr-1", "nome": "Ceraldi Vincenzo",
                     "ruolo": "amministratore", "via": "sessione_erp"}


# ── 1. Responsabile predefinito = titolare ───────────────────────────────────

def test_senza_assegnazione_il_responsabile_e_il_titolare(archivio, monkeypatch):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    _impostazioni(monkeypatch)
    db, oggi = archivio
    esito = run(apri_rilevazioni_del_giorno())

    assert esito["aperte"] == 3
    assert esito["senza_responsabile"] == [], "il titolare risponde di tutto cio' che nessuno ha preso"
    assert esito["responsabile_predefinito"] == "Ceraldi Vincenzo"
    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["operatore_nome"] == "Ceraldi Vincenzo"
    assert casella["operatore_id"] == "titolare"
    assert casella["responsabile_predefinito"] is True
    assert casella["temp"] is None and casella["stato"] == "da_rilevare"
    # l'assegnazione esplicita a un dipendente vince ancora
    casella2 = run(db.temperature_positive.find_one({"frigorifero_numero": 2}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella2["operatore_nome"] == "Pocci Salvatore"
    assert casella2["responsabile_predefinito"] is False


def test_senza_nome_nelle_impostazioni_non_si_inventa_un_responsabile(archivio, monkeypatch):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno

    _impostazioni(monkeypatch, responsabile="")
    db, oggi = archivio
    esito = run(apri_rilevazioni_del_giorno())

    assert esito["senza_responsabile"] == ["Frigorifero N°1", "Congelatore N°1"]
    casella = run(db.temperature_positive.find_one({"frigorifero_numero": 1}))[
        "temperature"][str(oggi.month)][str(oggi.day)]
    assert casella["operatore_nome"] == "" and casella["operatore_id"] == ""


def test_nessun_nome_del_titolare_cablato_nel_codice():
    import inspect

    from app.lotti import azienda
    from app.lotti.routers import attrezzature, haccp_auto
    from app.lotti.servizi import responsabile_haccp

    for modulo in (responsabile_haccp, haccp_auto, attrezzature, azienda):
        assert "Ceraldi" not in inspect.getsource(modulo).replace("Ceraldi Group", ""), modulo.__name__


def test_l_elenco_apparecchi_porta_il_responsabile_risolto(archivio, monkeypatch):
    from app.lotti.routers.attrezzature import elenco_assegnazioni, get_attrezzature

    _impostazioni(monkeypatch)
    lista = run(get_attrezzature())
    per_nome = {r["nome"]: r for r in lista["tutti"]}
    assert per_nome["Frigorifero N°1"]["operatore_nome"] == "Ceraldi Vincenzo"
    assert per_nome["Frigorifero N°1"]["responsabile_predefinito"] is True
    assert per_nome["Frigorifero N°2"]["operatore_nome"] == "Pocci Salvatore"
    assert per_nome["Frigorifero N°2"]["responsabile_predefinito"] is False

    assegnazioni = run(elenco_assegnazioni())
    assert assegnazioni["senza_responsabile"] == []
    assert assegnazioni["assegnate"] == 3


def test_put_responsabile_titolare_dipendente_o_nessuno(archivio, monkeypatch):
    from app.lotti.routers.attrezzature import AssegnaResponsabile, assegna_responsabile

    _impostazioni(monkeypatch)
    db, _oggi = archivio

    async def per_id(operatore_id):
        return {"id": "hr-9", "nome_completo": "Moscato Antonio"} if operatore_id == "hr-9" else None

    monkeypatch.setattr("app.lotti.routers.tablet_operatori.operatore_per_id", per_id)

    esito = run(assegna_responsabile("frigo", 1, AssegnaResponsabile(operatore_id="titolare")))
    assert esito["operatore_nome"] == "Ceraldi Vincenzo"
    doc = run(db.attrezzature_config.find_one({"tipo": "frigo", "numero": 1}))
    assert doc["operatore_id"] == "titolare" and doc["operatore_nome"] == "Ceraldi Vincenzo"

    esito = run(assegna_responsabile("frigo", 1, AssegnaResponsabile(operatore_id="hr-9")))
    assert esito["operatore_nome"] == "Moscato Antonio", "il nome viene da HR, non dal client"

    esito = run(assegna_responsabile("frigo", 1, AssegnaResponsabile(operatore_id="")))
    assert esito["responsabile_predefinito"] is True
    doc = run(db.attrezzature_config.find_one({"tipo": "frigo", "numero": 1}))
    assert doc["operatore_id"] == "" and doc["operatore_nome"] == ""

    with pytest.raises(HTTPException) as e:
        run(assegna_responsabile("frigo", 1, AssegnaResponsabile(operatore_id="hr-404")))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        run(assegna_responsabile("forno", 1, AssegnaResponsabile(operatore_id="")))
    assert e.value.status_code == 400


def test_put_responsabile_titolare_senza_nome_e_un_409(archivio, monkeypatch):
    from app.lotti.routers.attrezzature import AssegnaResponsabile, assegna_responsabile

    _impostazioni(monkeypatch, responsabile="")
    with pytest.raises(HTTPException) as e:
        run(assegna_responsabile("frigo", 1, AssegnaResponsabile(operatore_id="titolare")))
    assert e.value.status_code == 409


# ── 2. Firma con la sessione amministratore ──────────────────────────────────

def test_la_sessione_admin_anonima_firma_col_nome_delle_impostazioni(monkeypatch):
    from app.lotti.servizi.registro_haccp import firma_registrazione

    _impostazioni(monkeypatch)
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)
    firma = run(firma_registrazione(object(), "", ""))

    assert firma == {"operatore": "Ceraldi Vincenzo", "dipendente_id": "",
                     "firma_verificata": True, "firma_via": "sessione_admin"}


def test_la_sessione_admin_con_identita_hr_firma_col_nome_del_token(monkeypatch):
    from app.lotti.servizi.registro_haccp import firma_registrazione

    _impostazioni(monkeypatch, responsabile="Altro Nome")
    _sessione(monkeypatch, SESSIONE_ADMIN_HR)
    firma = run(firma_registrazione(object(), "", ""))

    assert firma == {"operatore": "Ceraldi Vincenzo", "dipendente_id": "hr-1",
                     "firma_verificata": True, "firma_via": "sessione_admin"}


def test_senza_nessun_nome_la_sessione_admin_non_firma(monkeypatch):
    """«Amministratore» non e' una persona: senza il nome nelle Impostazioni
    il token erp:... apre le pagine ma non firma."""
    from app.lotti.servizi.registro_haccp import firma_registrazione

    _impostazioni(monkeypatch, responsabile="")
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)
    firma = run(firma_registrazione(object(), "", ""))

    assert firma["firma_verificata"] is False and firma["operatore"] == ""


def test_l_automazione_non_firma_mai(monkeypatch):
    from app.lotti.servizi.registro_haccp import firma_registrazione

    _impostazioni(monkeypatch)
    _sessione(monkeypatch, {"id": "github-scheduler", "nome": "Workflow mattutino Lotti",
                            "ruolo": "automazione", "via": "automation_secret"})
    firma = run(firma_registrazione(object(), "", ""))
    assert firma["firma_verificata"] is False


def test_un_pin_sbagliato_resta_401_anche_con_la_sessione_admin(monkeypatch):
    from app.lotti.servizi.registro_haccp import firma_registrazione

    _impostazioni(monkeypatch)
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)

    async def nessuno(_pin, solo_operatori_lotti=False):
        return []

    monkeypatch.setattr("app.hr.services.auth_dipendenti.trova_dipendente_per_pin", nessuno)
    monkeypatch.setattr("app.lotti.auth.check_lock", _vuota)
    monkeypatch.setattr("app.lotti.auth.register_fail", _vuota)
    monkeypatch.setattr("app.lotti.auth.ip_richiesta", lambda _r: "client")

    with pytest.raises(HTTPException) as e:
        run(firma_registrazione(object(), "0000", ""))
    assert e.value.status_code == 401


async def _vuota(*_a, **_k):
    return None


# ── 3. Dichiarazione di conformita' con la sessione admin ────────────────────

def test_il_titolare_dichiara_conformi_con_la_sessione_del_gestionale(archivio, monkeypatch):
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno, dichiara_conformi_oggi

    _impostazioni(monkeypatch)
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)
    db, oggi = archivio
    run(apri_rilevazioni_del_giorno())

    esito = run(dichiara_conformi_oggi(request=object(), pin=""))

    assert esito == {"success": True, "dichiarate": 3, "firmate": 0,
                     "gia_firmate": 0, "firmato_da": "Ceraldi Vincenzo"}
    for collezione, campo in ((db.temperature_positive, "frigorifero_numero"),
                              (db.temperature_negative, "congelatore_numero")):
        casella = run(collezione.find_one({campo: 1}))["temperature"][str(oggi.month)][str(oggi.day)]
        assert casella["temp"] is None, "mai un numero inventato"
        assert casella["stato"] == "conforme" and casella["esito"] == "conforme"
        assert casella["firma_verificata"] is True
        assert casella["firma_via"] == "sessione_admin"
        assert casella["operatore"] == "Ceraldi Vincenzo"
        assert casella["dipendente_id"] == ""


def test_senza_controllo_visivo_la_dichiarazione_e_un_409(archivio, monkeypatch):
    from app.lotti.routers.haccp_auto import dichiara_conformi_oggi

    _impostazioni(monkeypatch, controllo_visivo="no")
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)
    with pytest.raises(HTTPException) as e:
        run(dichiara_conformi_oggi(request=object(), pin=""))
    assert e.value.status_code == 409


def test_senza_nome_del_titolare_la_dichiarazione_e_un_401(archivio, monkeypatch):
    from app.lotti.routers.haccp_auto import dichiara_conformi_oggi

    _impostazioni(monkeypatch, responsabile="")
    _sessione(monkeypatch, SESSIONE_ADMIN_ANONIMA)
    with pytest.raises(HTTPException) as e:
        run(dichiara_conformi_oggi(request=object(), pin=""))
    assert e.value.status_code == 401


def test_turno_oggi_dice_quali_apparecchi_non_hanno_la_casella(archivio, monkeypatch):
    """Un apparecchio aggiunto dopo le 07:00 non ha la casella: il tablet lo
    sa e offre «Apri le caselle di oggi»."""
    from app.lotti.routers.haccp_auto import apri_rilevazioni_del_giorno, turno_di_oggi

    _impostazioni(monkeypatch)
    db, _oggi = archivio
    prima = run(turno_di_oggi())
    assert prima["quante_senza_casella"] == 3 and prima["quante_da_rilevare"] == 0
    assert prima["controllo_visivo_attivo"] is True

    run(apri_rilevazioni_del_giorno())
    run(db.attrezzature_config.insert_one(
        {"tipo": "frigo", "numero": 3, "nome": "Cella nuova", "attivo": True}))

    dopo = run(turno_di_oggi())
    assert dopo["quante_da_rilevare"] == 3
    assert dopo["senza_casella"] == ["Cella nuova"]
    nomi = {r["operatore_nome"] for r in dopo["da_rilevare"]}
    assert nomi == {"Ceraldi Vincenzo", "Pocci Salvatore"}

    assert run(apri_rilevazioni_del_giorno())["aperte"] == 1
    assert run(turno_di_oggi())["quante_senza_casella"] == 0
