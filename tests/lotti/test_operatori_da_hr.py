"""Operatori del tablet = anagrafica HR (titolare 14/09/2026, regole R1-R6).

Tutto su database finti (mongomock): nessun PIN reale, numeri inventati.
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")

import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

PIN_A = "246810"
PIN_B = "135791"
PIN_ADMIN_TEST = "990011"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def basi(monkeypatch):
    import app.lotti.routers.tablet_operatori as t
    import app.lotti.routers.scheduler as sched
    from app.hr.database import Database as DatabaseHR
    import hashlib

    db = AsyncMongoMockClient()["lotti_test"]
    hr = AsyncMongoMockClient()["hr_test"]
    monkeypatch.setattr(t, "db", db)
    monkeypatch.setattr(sched, "db", db, raising=False)
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(PIN_ADMIN_TEST.encode()).hexdigest())
    return t, db, hr


def _persone_hr():
    return [
        {"id": "hr-pocci", "nome": "Salvatore", "cognome": "Pocci", "codice_fiscale": "PCCSVT69P30F839G",
         "ruolo": "6.5.1.3.1 - Pasticcieri e cioccolatai", "stato": "attivo", "attivo": True},
        {"id": "hr-lesina", "nome": "Angela", "cognome": "Lesina", "codice_fiscale": "LSNNGL96H58F839P",
         "ruolo": "5.2.2.3.2 - Camerieri di ristorante", "stato": "attivo", "attivo": True},
        {"id": "hr-moscato", "nome": "Emanuele", "cognome": "Moscato", "codice_fiscale": "MSCMNL88R26F839C",
         "ruolo": "5.2.2.3.2.4 - cameriere di bar", "stato": "cessato", "attivo": False,
         "data_fine_rapporto": "2026-07-01", "motivo_cessazione": "dimissioni"},
        {"id": "hr-iazzetta", "nome": "Francesco", "cognome": "Iazzetta", "codice_fiscale": "ZZTFNC07A05F839D",
         "stato": "attivo", "attivo": True, "lotti_operatore": False},
        {"id": "hr-nuovo", "nome": "Anna", "cognome": "Rossi", "codice_fiscale": "RSSNNA00A00F839X",
         "ruolo": "5.2.2.4.0.5 - barista", "stato": "attivo", "attivo": True},
        {"id": "hr-vince", "nome": "Vincenzo", "cognome": "Ceraldi", "codice_fiscale": "CRLVCN74L15F839W",
         "ruolo_app": "admin", "stato": "attivo", "attivo": True},
        {"id": "hr-fuso", "nome": "Antonella", "cognome": "Ceraldi", "merged_into": "x", "stato": "attivo"},
    ]


def _operatori_lotti(t):
    import bcrypt
    h = lambda p: bcrypt.hashpw(p.encode(), bcrypt.gensalt(4)).decode()
    return [
        {"id": "op-pocci", "nome": "Pocci", "ruolo": "operatore", "attivo": True, "pin": "", "pin_da_impostare": True},
        {"id": "op-lisina", "nome": "Lisina", "ruolo": "operatore", "attivo": True, "pin": h(PIN_A),
         "pin_lookup": "abc", "postazione": "sala", "libretto_sanitario_scadenza": "2027-01-31"},
        {"id": "op-moscato", "nome": "Moscato", "ruolo": "operatore", "attivo": True, "pin": "", "pin_da_impostare": True},
        {"id": "op-viviana", "nome": "Viviana", "ruolo": "operatore", "attivo": True, "pin": h(PIN_B), "pin_lookup": "zzz"},
        {"id": "op-vince", "nome": "Ceraldi Vincenzo", "ruolo": "amministratore", "attivo": True,
         "codice_fiscale": "CRLVCN74L15F839W", "pin": h(PIN_B), "gruppo_pin": "amministratori_ceraldi"},
        {"id": "op-admin-legacy", "nome": "Amministratore", "ruolo": "amministratore", "attivo": False,
         "sostituito_da_gruppo": "amministratori_ceraldi", "pin": h(PIN_B)},
    ]


def test_sincronizzazione_allinea_gli_operatori_all_anagrafica_hr(basi):
    t, db, hr = basi
    run(hr.dipendenti.insert_many(_persone_hr()))
    run(db.tablet_operatori.insert_many(_operatori_lotti(t)))

    esito = run(t.sincronizza_operatori_da_hr())
    assert esito["esito"] == "ok" and esito["creati"] == 1 and esito["disattivati"] == 1

    ops = {o["id"]: o for o in run(db.tablet_operatori.find({}, {"_id": 0}).to_list(50))}
    # Pocci: agganciato per cognome, nome completo da HR, postazione dal ruolo
    assert ops["op-pocci"]["hr_id"] == "hr-pocci" and ops["op-pocci"]["nome"] == "Pocci Salvatore"
    assert ops["op-pocci"]["attivo"] is True and ops["op-pocci"]["postazione"] == "pasticceria"
    # Lisina = Lesina (alias): storico conservato, postazione e libretto NON toccati
    assert ops["op-lisina"]["hr_id"] == "hr-lesina" and ops["op-lisina"]["nome"] == "Lesina Angela"
    assert ops["op-lisina"]["postazione"] == "sala" and ops["op-lisina"]["libretto_sanitario_scadenza"] == "2027-01-31"
    # Moscato cessato in HR -> non piu' in carico, con data e motivo, riga conservata
    assert ops["op-moscato"]["attivo"] is False and ops["op-moscato"]["in_carico"] is False
    assert ops["op-moscato"]["data_fine_rapporto"] == "2026-07-01" and ops["op-moscato"]["motivo_fine_rapporto"] == "dimissioni"
    # Viviana non e' in HR -> disattivata, non cancellata
    assert ops["op-viviana"]["attivo"] is False and ops["op-viviana"]["hr_stato"] == "non_in_hr"
    # Iazzetta: attivo in HR ma NON operatore Lotti -> nessuna riga
    assert not any(o.get("hr_id") == "hr-iazzetta" for o in ops.values())
    # Anna Rossi (nuova in HR) -> creata al bar
    nuova = next(o for o in ops.values() if o.get("hr_id") == "hr-nuovo")
    assert nuova["attivo"] is True and nuova["postazione"] == "bar" and nuova["nome"] == "Rossi Anna"
    # Vincenzo: amministratore, agganciato per CF, PIN condiviso rimosso
    assert ops["op-vince"]["ruolo"] == "amministratore" and "gruppo_pin" not in ops["op-vince"]
    # nessun PIN resta in Lotti
    assert all(not o.get("pin") and not o.get("pin_lookup") for o in ops.values())
    # idempotente
    assert run(t.sincronizza_operatori_da_hr())["creati"] == 0


def test_migrazione_pin_in_hr_una_volta_sola_e_mai_i_condivisi(basi):
    t, db, hr = basi
    from app.hr.services import auth_dipendenti
    persone = _persone_hr()
    persone[0]["pin_hash"] = auth_dipendenti.hash_pin("777777")  # Pocci ha gia' un PIN in HR
    run(hr.dipendenti.insert_many(persone))
    ops = _operatori_lotti(t)
    ops[0]["pin"] = ops[1]["pin"]  # Pocci in Lotti ha un bcrypt (diverso da HR)
    ops[0]["pin_da_impostare"] = False
    run(db.tablet_operatori.insert_many(ops))

    esito = run(t.migra_pin_in_hr())
    assert esito == {"migrati": 1, "gia_in_hr": 1, "senza_persona": 1, "condivisi_scartati": 1}
    lesina = run(hr.dipendenti.find_one({"id": "hr-lesina"}, {"_id": 0}))
    assert lesina["pin_hash"].startswith("$2") and lesina.get("pin_migrato_da_lotti")
    assert auth_dipendenti.verify_pin(PIN_A, lesina["pin_hash"])
    pocci = run(hr.dipendenti.find_one({"id": "hr-pocci"}, {"_id": 0}))
    assert auth_dipendenti.verify_pin("777777", pocci["pin_hash"])  # HR vince
    vince = run(hr.dipendenti.find_one({"id": "hr-vince"}, {"_id": 0}))
    assert "pin_hash" not in vince  # R4: il condiviso non si migra
    run(t.sincronizza_operatori_da_hr())
    assert run(t.migra_pin_in_hr())["migrati"] == 0


def test_login_tablet_usa_il_pin_della_scheda_hr(basi):
    t, db, hr = basi
    from app.hr.services import auth_dipendenti
    run(hr.dipendenti.insert_many(_persone_hr()))
    run(db.tablet_operatori.insert_many(_operatori_lotti(t)))
    run(t.migra_pin_in_hr())
    run(t.sincronizza_operatori_da_hr())

    # Lesina entra col PIN migrato (bcrypt, senza impronta -> ripara e la salva)
    res = run(t.login_pin(t.PinLogin(pin=PIN_A)))
    assert res["operatore"] == {"dipendente_id": "hr-lesina", "nome": "Lesina Angela", "ruolo": "operatore"} and res["token"]
    from app.lotti.auth import verify_token
    assert verify_token(res["token"])["sub"] == "hr-lesina"
    assert run(hr.dipendenti.find_one({"id": "hr-lesina"}))["pin_lookup"]
    # PIN impostato in HR per una persona nuova (senza riga Lotti gia' pronta)
    run(hr.dipendenti.update_one({"id": "hr-nuovo"}, {"$set": {"pin_hash": auth_dipendenti.hash_pin("4321"),
                                                             "pin_lookup": auth_dipendenti.pin_lookup("4321")}}))
    res = run(t.login_pin(t.PinLogin(pin="4321")))
    assert res["operatore"]["nome"] == "Rossi Anna"
    assert res["operatore"]["dipendente_id"] == "hr-nuovo"
    # un cessato con PIN ancora salvato non entra
    run(hr.dipendenti.update_one({"id": "hr-moscato"}, {"$set": {"pin_hash": auth_dipendenti.hash_pin("5555")}}))
    with pytest.raises(HTTPException) as exc:
        run(t.login_pin(t.PinLogin(pin="5555")))
    assert exc.value.status_code == 401
    # Viviana (non in HR) non entra piu' col vecchio PIN Lotti
    with pytest.raises(HTTPException):
        run(t.login_pin(t.PinLogin(pin=PIN_B)))
    # PIN amministratore centrale: pagine admin si', firma no
    assert run(t.verifica_admin(t.PinAdmin(pin=PIN_ADMIN_TEST)))["ok"] is True
    with pytest.raises(HTTPException) as exc:
        run(t.login_pin(t.PinLogin(pin=PIN_ADMIN_TEST)))
    assert "personale" in exc.value.detail


def test_un_solo_percorso_pin_lotti():
    from app.lotti.auth import router as auth_router
    from app.lotti.routers.tablet_operatori import router as tablet_router

    assert not any("POST" in route.methods and route.path == "/auth/login" for route in auth_router.routes)
    assert sum("POST" in route.methods and route.path == "/tablet-operatori/login" for route in tablet_router.routes) == 1


def test_pin_non_univoco_non_sceglie_una_persona_a_caso(monkeypatch):
    from app.lotti.routers import tablet_operatori as t

    async def due_persone(_pin):
        return [
            {"dipendente_id": "hr-1", "nome": "Uno", "ruolo": "operatore"},
            {"dipendente_id": "hr-2", "nome": "Due", "ruolo": "operatore"},
        ]

    monkeypatch.setattr(t, "trova_operatori_per_pin", due_persone)
    with pytest.raises(HTTPException) as error:
        run(t.login_pin(t.PinLogin(pin="1234")))
    assert error.value.status_code == 409


def test_pin_unico_fra_gli_attivi_e_revoca_alla_cessazione(basi):
    t, db, hr = basi
    from app.hr.services import auth_dipendenti
    run(hr.dipendenti.insert_many(_persone_hr()))
    assert run(auth_dipendenti.imposta_pin("hr-pocci", "2468"))
    with pytest.raises(ValueError):
        run(auth_dipendenti.imposta_pin("hr-lesina", "2468"))
    assert run(auth_dipendenti.imposta_pin("hr-lesina", "8642"))
    trovati = run(auth_dipendenti.trova_dipendente_per_pin("2468"))
    assert [d["id"] for d in trovati] == ["hr-pocci"]
    # Iazzetta non e' operatore Lotti: col filtro non viene restituito
    assert run(auth_dipendenti.imposta_pin("hr-iazzetta", "1357"))
    assert run(auth_dipendenti.trova_dipendente_per_pin("1357", solo_operatori_lotti=True)) == []
    assert [d["id"] for d in run(auth_dipendenti.trova_dipendente_per_pin("1357"))] == ["hr-iazzetta"]
    # PIN di un cessato non blocca l'unicita' e non viene trovato
    run(hr.dipendenti.update_one({"id": "hr-moscato"}, {"$set": {"pin_hash": auth_dipendenti.hash_pin("2468")}}))
    assert run(auth_dipendenti.trova_dipendente_per_pin("2468"))[0]["id"] == "hr-pocci"
    assert run(auth_dipendenti.rimuovi_pin("hr-pocci"))
    assert run(auth_dipendenti.trova_dipendente_per_pin("2468")) == []


def test_lista_e_modifica_solo_dati_haccp(basi):
    t, db, hr = basi
    run(hr.dipendenti.insert_many(_persone_hr()))
    run(db.tablet_operatori.insert_many(_operatori_lotti(t)))
    run(t.sincronizza_operatori_da_hr())

    in_carico = run(t.lista_dipendenti())
    assert {o["nome"] for o in in_carico} == {"Pocci Salvatore", "Lesina Angela", "Rossi Anna", "Ceraldi Vincenzo"}
    assert all("pin" not in o and "pin_lookup" not in o for o in in_carico)
    tutti = run(t.lista_dipendenti(tutti=True))
    non_in_carico = [o for o in tutti if not o["in_carico"]]
    assert {o["nome"] for o in non_in_carico} == {"Moscato Emanuele", "Viviana"}
    assert not any(o["nome"] == "Amministratore" for o in tutti)

    esito = run(t.aggiorna_dipendente("op-pocci", t.AggiornaDipendente(postazione="laboratorio",
                                                                       libretto_sanitario_scadenza="2026-12-31")))
    assert esito["modificato"] is True and esito["salvato_alle"]
    with pytest.raises(HTTPException):
        run(t.aggiorna_dipendente("op-pocci", t.AggiornaDipendente(postazione="cucina")))
    op = run(db.tablet_operatori.find_one({"id": "op-pocci"}, {"_id": 0}))
    assert op["postazione"] == "laboratorio" and op["libretto_sanitario_scadenza"] == "2026-12-31"
    # una nuova sincronizzazione non sovrascrive la postazione scelta a mano
    run(t.sincronizza_operatori_da_hr())
    assert run(db.tablet_operatori.find_one({"id": "op-pocci"}))["postazione"] == "laboratorio"


def test_senza_database_hr_nessun_operatore_e_nessun_login(basi, monkeypatch):
    t, db, hr = basi
    from app.hr.database import Database as DatabaseHR, DatabaseNonConfigurato
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: DatabaseNonConfigurato()))
    assert run(t.sincronizza_operatori_da_hr())["esito"] == "hr_non_configurato"
    with pytest.raises(HTTPException):
        run(t.login_pin(t.PinLogin(pin=PIN_A)))


def test_postazione_dal_ruolo_hr():
    import app.lotti.routers.tablet_operatori as t
    assert t.postazione_da_ruolo("6.5.1.3.1 - Pasticcieri e cioccolatai") == "pasticceria"
    assert t.postazione_da_ruolo("5.2.2.4.0.5 - barista") == "bar"
    assert t.postazione_da_ruolo("5.2.2.4.0.3 - banconiere di bar") == "bar"
    assert t.postazione_da_ruolo("5.2.2.3.2.4 - cameriere di bar") == "sala"
    assert t.postazione_da_ruolo("5.2.2.1.0.11 - cuoco di partita di rosticceria") == "laboratorio"
    assert t.postazione_da_ruolo("") == ""


def test_nessun_pin_scritto_nel_codice():
    import inspect
    import app.lotti.routers.tablet_operatori as t
    src = inspect.getsource(t)
    assert "NOMI_DEFAULT" not in src
    assert "hashpw" not in src and "_hash_pin" not in src  # Lotti non salva piu' nessun PIN
