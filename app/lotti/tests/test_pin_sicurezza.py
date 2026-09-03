"""
test_pin_sicurezza.py — 25/07/2026, dopo l'audit (Enzo: «procedi per i pin,
si usa la soluzione migliore»).

Tutto su MONGO DI PROVA (mongomock-motor, DB "Gestionale_Test").
NESSUN PIN reale: qui si usano numeri inventati per il test.

Copre i tre difetti veri trovati nell'audit:
  1. il PIN era salvato IN CHIARO nel database → adesso non ci finisce più, e
     quello già presente viene cancellato all'avvio (dopo aver salvato
     l'impronta, così nessuno resta fuori);
  2. cambiare il PIN a un dipendente NON revocava il vecchio: al riavvio del
     server la lista scritta nel codice rimetteva il PIN di partenza dentro
     `pin_chiaro`, e il login lo riaccettava;
  3. i PIN erano scritti nel codice sorgente (quindi nella cronologia del
     repository).
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")  # SOLO db di prova

import asyncio
import importlib
import inspect
import pkgutil

import pytest
from mongomock_motor import AsyncMongoMockClient

PIN_FINTO_A = "246810"
PIN_FINTO_B = "135791"


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("ciclo chiuso")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import app.lotti.routers as routers  # noqa
    cli = AsyncMongoMockClient()
    db = cli["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod
    monkeypatch.setattr(dbmod, "database", db, raising=False)
    return db


# ── 1. Il PIN non finisce più in chiaro nel database ───────────────────────
def test_creare_un_operatore_non_scrive_il_pin_in_chiaro(dbmock):
    import app.lotti.routers.tablet_operatori as t
    run(t.crea_dipendente(t.NuovoDipendente(nome="Prova", pin=PIN_FINTO_A)))
    doc = run(dbmock.tablet_operatori.find_one({"nome": "Prova"}))
    assert "pin_chiaro" not in doc, "il PIN non deve MAI finire in chiaro nel database"
    assert doc["pin"].startswith("$2"), "il PIN deve restare cifrato con bcrypt"
    assert doc["pin_lookup"] and doc["pin_lookup"] != PIN_FINTO_A
    # l'impronta non deve contenere il PIN in nessuna forma leggibile
    assert PIN_FINTO_A not in doc["pin_lookup"]


def test_la_bonifica_cancella_i_pin_in_chiaro_senza_lasciare_fuori_nessuno(dbmock):
    """Chi entrava prima deve entrare anche dopo: si calcola l'impronta DAL
    vecchio pin in chiaro e solo dopo lo si cancella."""
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_one({
        "id": "vecchio", "nome": "Storico", "ruolo": "operatore", "attivo": True,
        "pin": t._hash_pin(PIN_FINTO_A), "pin_chiaro": PIN_FINTO_A,
    }))
    run(t.seed_operatori())

    doc = run(dbmock.tablet_operatori.find_one({"id": "vecchio"}))
    assert "pin_chiaro" not in doc, "il PIN in chiaro deve sparire dal database"
    assert doc.get("pin_lookup"), "…ma l'impronta deve esserci, altrimenti l'accesso rallenta"
    esito = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    assert esito["operatore"]["nome"] == "Storico", "chi entrava prima deve entrare anche dopo"


def test_la_bonifica_ricrea_bcrypt_se_il_backup_aveva_solo_pin_chiaro(dbmock):
    """Regressione produzione 24/08/2026: un backup incompleto non deve
    perdere l'accesso quando il PIN leggibile viene eliminato."""
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_one({
        "id": "backup-incompleto", "nome": "Storico", "ruolo": "amministratore",
        "attivo": True, "pin": "", "pin_chiaro": PIN_FINTO_A,
    }))
    run(t.seed_operatori())

    doc = run(dbmock.tablet_operatori.find_one({"id": "backup-incompleto"}))
    assert "pin_chiaro" not in doc
    assert t._verify_pin(PIN_FINTO_A, doc["pin"])
    assert run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))["operatore"]["nome"] == "Storico"


def test_login_ripara_hash_storico_disallineato_dalla_sua_impronta(dbmock):
    """Se la vecchia migrazione ha già cancellato pin_chiaro lasciando un
    bcrypt vecchio, il PIN digitato che coincide con la HMAC salvata ripara
    bcrypt senza memorizzare il valore leggibile."""
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_one({
        "id": "hash-disallineato", "nome": "Ceraldi Vincenzo",
        "ruolo": "amministratore", "attivo": True,
        "pin": t._hash_pin(PIN_FINTO_B),
        "pin_lookup": t._pin_lookup(PIN_FINTO_A),
    }))

    esito = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    assert esito["operatore"]["nome"] == "Ceraldi Vincenzo"
    doc = run(dbmock.tablet_operatori.find_one({"id": "hash-disallineato"}))
    assert t._verify_pin(PIN_FINTO_A, doc["pin"])
    assert doc["pin_hash_riparato"] is True
    assert PIN_FINTO_A not in str(doc)


def test_recupero_admin_da_render_crea_vincenzo_senza_pin_in_chiaro(dbmock, monkeypatch):
    import app.lotti.routers.tablet_operatori as t
    monkeypatch.setenv("ADMIN_PIN_RECOVERY", PIN_FINTO_A)
    run(dbmock.tablet_operatori.insert_one({
        "id": "op-esistente", "nome": "Mario", "ruolo": "operatore",
        "attivo": True, "pin": t._hash_pin(PIN_FINTO_B),
        "pin_lookup": t._pin_lookup(PIN_FINTO_B),
    }))

    run(t.seed_operatori())

    vincenzo = run(dbmock.tablet_operatori.find_one({"nome": "Ceraldi Vincenzo"}))
    valerio = run(dbmock.tablet_operatori.find_one({"nome": "Ceraldi Valerio"}))
    assert vincenzo["ruolo"] == "amministratore"
    assert valerio["ruolo"] == "amministratore"
    assert vincenzo["attivo"] is True
    assert valerio["attivo"] is True
    assert vincenzo["gruppo_pin"] == valerio["gruppo_pin"] == t.GRUPPO_PIN_ADMIN_CERALDI
    assert t._verify_pin(PIN_FINTO_A, vincenzo["pin"])
    assert t._verify_pin(PIN_FINTO_A, valerio["pin"])
    assert "pin_chiaro" not in vincenzo
    assert PIN_FINTO_A not in str(vincenzo)
    prima_scelta = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    assert prima_scelta["scelta_operatore"] is True
    assert {o["nome"] for o in prima_scelta["operatori"]} == {
        "Ceraldi Vincenzo", "Ceraldi Valerio"
    }
    assert "token" not in prima_scelta
    assert run(t.login_pin(t.PinLogin(
        pin=PIN_FINTO_A, operatore_id=vincenzo["id"]
    )))["operatore"] == {
        "id": vincenzo["id"], "nome": "Ceraldi Vincenzo", "ruolo": "amministratore"
    }
    assert run(t.login_pin(t.PinLogin(
        pin=PIN_FINTO_A, operatore_id=valerio["id"]
    )))["operatore"] == {
        "id": valerio["id"], "nome": "Ceraldi Valerio", "ruolo": "amministratore"
    }


def test_stesso_recupero_non_resuscita_il_pin_dopo_modifica(dbmock, monkeypatch):
    import app.lotti.routers.tablet_operatori as t
    monkeypatch.setenv("ADMIN_PIN_RECOVERY", PIN_FINTO_A)
    run(t.seed_operatori())
    vincenzo = run(dbmock.tablet_operatori.find_one({"nome": "Ceraldi Vincenzo"}))
    run(t.reimposta_pin(vincenzo["id"], t.ReimpostaPin(pin_nuovo=PIN_FINTO_B)))

    run(t.seed_operatori())

    with pytest.raises(Exception):
        run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    scelta = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_B)))
    assert scelta["scelta_operatore"] is True
    assert {o["nome"] for o in scelta["operatori"]} == {
        "Ceraldi Vincenzo", "Ceraldi Valerio"
    }


def test_pin_condiviso_resta_due_identita_distinte_e_si_aggiorna_insieme(dbmock):
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_one({
        "id": "admin-generico", "nome": "Amministratore",
        "ruolo": "amministratore", "attivo": True,
        "pin": t._hash_pin(PIN_FINTO_A),
        "pin_lookup": t._pin_lookup(PIN_FINTO_A),
    }))
    run(t.seed_operatori())

    vincenzo = run(dbmock.tablet_operatori.find_one({"nome": "Ceraldi Vincenzo"}))
    valerio = run(dbmock.tablet_operatori.find_one({"nome": "Ceraldi Valerio"}))
    generico = run(dbmock.tablet_operatori.find_one({"id": "admin-generico"}))
    assert vincenzo["id"] != valerio["id"]
    assert generico["attivo"] is False

    scelta = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    assert scelta["scelta_operatore"] is True
    assert len(scelta["operatori"]) == 2

    esito = run(t.reimposta_pin(
        valerio["id"], t.ReimpostaPin(pin_nuovo=PIN_FINTO_B)
    ))
    assert set(esito["operatori_aggiornati"]) == {vincenzo["id"], valerio["id"]}
    with pytest.raises(Exception):
        run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    nuova_scelta = run(t.login_pin(t.PinLogin(pin=PIN_FINTO_B)))
    assert {o["id"] for o in nuova_scelta["operatori"]} == {
        vincenzo["id"], valerio["id"]
    }


def test_login_pin_condiviso_non_scansiona_tutti_gli_altri_operatori(dbmock, monkeypatch):
    """Regressione produzione 24/08/2026: il PIN era corretto, ma il backend
    continuava a provare bcrypt su ogni dipendente e superava i 15 secondi del
    tablet. Lo stesso hash condiviso va verificato una volta sola e, trovato il
    gruppo tramite pin_lookup, il fallback globale non deve partire."""
    import app.lotti.routers.tablet_operatori as t
    pin_hash = t._hash_pin(PIN_FINTO_A)
    lookup = t._pin_lookup(PIN_FINTO_A)
    run(dbmock.tablet_operatori.insert_many([
        {
            "id": "vincenzo", "nome": "Ceraldi Vincenzo",
            "ruolo": "amministratore", "attivo": True,
            "gruppo_pin": t.GRUPPO_PIN_ADMIN_CERALDI,
            "pin": pin_hash, "pin_lookup": lookup,
        },
        {
            "id": "valerio", "nome": "Ceraldi Valerio",
            "ruolo": "amministratore", "attivo": True,
            "gruppo_pin": t.GRUPPO_PIN_ADMIN_CERALDI,
            "pin": pin_hash, "pin_lookup": lookup,
        },
        *[
            {
                "id": f"operatore-{i}", "nome": f"Operatore {i}",
                "ruolo": "operatore", "attivo": True,
                "pin": f"hash-non-correlato-{i}",
                "pin_lookup": f"lookup-non-correlato-{i}",
            }
            for i in range(30)
        ],
    ]))

    verifica_reale = t._verify_pin
    hash_verificati = []

    def verifica_contata(pin, hashed):
        hash_verificati.append(hashed)
        return verifica_reale(pin, hashed)

    monkeypatch.setattr(t, "_verify_pin", verifica_contata)
    trovati = run(t.trova_operatori_per_pin(PIN_FINTO_A))

    assert {d["id"] for d in trovati} == {"vincenzo", "valerio"}
    assert hash_verificati == [pin_hash]


def test_il_database_non_contiene_nessun_pin_leggibile(dbmock):
    import app.lotti.routers.tablet_operatori as t
    run(t.crea_dipendente(t.NuovoDipendente(nome="Uno", pin=PIN_FINTO_A)))
    run(t.crea_dipendente(t.NuovoDipendente(nome="Due", pin=PIN_FINTO_B)))
    tutti = run(dbmock.tablet_operatori.find({}).to_list(50))
    testo = str(tutti)
    assert PIN_FINTO_A not in testo and PIN_FINTO_B not in testo


# ── 2. Cambiare il PIN REVOCA il vecchio ───────────────────────────────────
def test_reimpostare_il_pin_revoca_subito_il_vecchio(dbmock):
    import app.lotti.routers.tablet_operatori as t
    creato = run(t.crea_dipendente(t.NuovoDipendente(nome="Rossi", pin=PIN_FINTO_A)))
    run(t.reimposta_pin(creato["id"], t.ReimpostaPin(pin_nuovo=PIN_FINTO_B)))

    assert run(t.login_pin(t.PinLogin(pin=PIN_FINTO_B)))["operatore"]["nome"] == "Rossi"
    with pytest.raises(Exception):
        run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))


def test_il_riavvio_non_resuscita_il_pin_vecchio(dbmock):
    """IL DIFETTO PRINCIPALE: prima, a ogni riavvio, la lista scritta nel
    codice rimetteva il PIN di partenza e il vecchio tornava valido."""
    import app.lotti.routers.tablet_operatori as t
    creato = run(t.crea_dipendente(t.NuovoDipendente(nome="Bianchi", pin=PIN_FINTO_A)))
    run(t.reimposta_pin(creato["id"], t.ReimpostaPin(pin_nuovo=PIN_FINTO_B)))
    run(t.seed_operatori())  # simula il riavvio del server

    with pytest.raises(Exception):
        run(t.login_pin(t.PinLogin(pin=PIN_FINTO_A)))
    assert run(t.login_pin(t.PinLogin(pin=PIN_FINTO_B)))["operatore"]["nome"] == "Bianchi"


def test_due_dipendenti_non_possono_avere_lo_stesso_pin(dbmock):
    import app.lotti.routers.tablet_operatori as t
    run(t.crea_dipendente(t.NuovoDipendente(nome="Uno", pin=PIN_FINTO_A)))
    due = run(t.crea_dipendente(t.NuovoDipendente(nome="Due", pin=PIN_FINTO_B)))
    with pytest.raises(Exception):
        run(t.reimposta_pin(due["id"], t.ReimpostaPin(pin_nuovo=PIN_FINTO_A)))


# ── 3. Nessun PIN scritto nel codice ───────────────────────────────────────
def test_nessun_pin_scritto_nel_codice():
    """La lista dei dipendenti di partenza non deve contenere PIN: finivano
    nella cronologia del repository."""
    import app.lotti.routers.tablet_operatori as t
    src = inspect.getsource(t)
    assert not hasattr(t, "PIN_DEFAULT_MAP"), "la mappa dei PIN di partenza non deve più esistere"
    assert all(isinstance(n, str) for n in t.NOMI_DEFAULT)
    # nessuna sequenza di 4-6 cifre isolata dentro la lista dei nomi
    inizio = src.index("NOMI_DEFAULT = [")
    blocco = src[inizio: src.index("]", inizio)]
    import re
    assert not re.search(r"\b\d{4,6}\b", blocco), "niente PIN dentro la lista di partenza"


# ── 4. Nessuna risposta dell'API restituisce un PIN ────────────────────────
def test_le_api_non_restituiscono_mai_un_pin(dbmock):
    import app.lotti.routers.tablet_operatori as t
    run(t.crea_dipendente(t.NuovoDipendente(nome="Verdi", pin=PIN_FINTO_A, ruolo="amministratore")))

    lista = run(t.lista_dipendenti())
    assert PIN_FINTO_A not in str(lista)

    gestione = run(t.pin_operatori(t.PinAdmin(pin=PIN_FINTO_A)))
    assert PIN_FINTO_A not in str(gestione)
    assert gestione["pin_visibili"] is False
    assert gestione["operatori"][0]["pin_impostato"] is True


def test_il_pin_admin_resta_riconosciuto(dbmock):
    """La verifica del PIN amministratore (usata anche da ordini e da
    require_admin) deve funzionare senza il PIN in chiaro."""
    import app.lotti.routers.tablet_operatori as t
    run(t.crea_dipendente(t.NuovoDipendente(nome="Capo", pin=PIN_FINTO_A, ruolo="amministratore")))
    run(t.crea_dipendente(t.NuovoDipendente(nome="Operaio", pin=PIN_FINTO_B)))
    assert run(t.pin_amministratore_valido(PIN_FINTO_A)) is True
    assert run(t.pin_amministratore_valido(PIN_FINTO_B)) is False
    assert run(t.pin_amministratore_valido("0000")) is False


def test_dipendenti_gestionale_usano_id_stabile_non_il_solo_nome(dbmock, monkeypatch):
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_many([
        {
            "id": "op-collegato", "nome": "Operatore collegato", "attivo": True,
            "gestionale_dipendente_id": "dip-1", "codice_fiscale": "",
        },
        {
            "id": "op-esistente", "nome": "Anna Rossi", "attivo": True,
            "gestionale_dipendente_id": "", "codice_fiscale": "",
        },
    ]))

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [
                {"source_id": "dip-1", "nome": "Anna Rossi"},
                {"source_id": "dip-2", "nome": "Anna Rossi"},
            ]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setenv("GESTIONALECLOUD_API_URL", "https://gestionale.test")
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    monkeypatch.setattr(t.httpx, "AsyncClient", lambda **_kwargs: Client())

    result = run(t.nuovi_dipendenti())

    assert result["totale"] == 1
    assert result["nuovi"][0]["gestionale_dipendente_id"] == "dip-2"
    assert result["nuovi"][0]["candidato_operatore"]["id"] == "op-esistente"


def test_abilitazione_gestionale_non_duplica_lo_stesso_id(dbmock):
    import app.lotti.routers.tablet_operatori as t
    payload = t.AbilitaDipendente(
        gestionale_dipendente_id="dip-1", codice_fiscale="", nome="Anna",
        pin=PIN_FINTO_A,
    )
    run(t.abilita_dipendente(payload))
    with pytest.raises(Exception):
        run(t.abilita_dipendente(payload))


def test_collega_dipendente_conserva_operatore_e_pin(dbmock):
    import app.lotti.routers.tablet_operatori as t
    creato = run(t.crea_dipendente(t.NuovoDipendente(nome="Rossi", pin=PIN_FINTO_A)))
    prima = run(dbmock.tablet_operatori.find_one({"id": creato["id"]}))
    run(t.collega_dipendente(t.CollegaDipendente(
        operatore_id=creato["id"], gestionale_dipendente_id="dip-1",
        codice_fiscale="RSSNNA00A00F839X",
    )))
    dopo = run(dbmock.tablet_operatori.find_one({"id": creato["id"]}))

    assert dopo["id"] == prima["id"]
    assert dopo["pin"] == prima["pin"]
    assert dopo["gestionale_dipendente_id"] == "dip-1"
    assert dopo["codice_fiscale"] == "RSSNNA00A00F839X"


def test_propone_operatore_storico_con_solo_cognome(dbmock, monkeypatch):
    import app.lotti.routers.tablet_operatori as t
    run(dbmock.tablet_operatori.insert_one({
        "id": "op-pocci", "nome": "Pocci", "attivo": True,
        "gestionale_dipendente_id": "", "codice_fiscale": "",
    }))

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"data": [{
                "source_id": "dip-pocci", "nome": "SALVATORE POCCI",
                "cognome": "", "codice_fiscale": "PCCSVT69P30F839G",
            }]}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, *_args, **_kwargs): return Response()

    monkeypatch.setenv("GESTIONALECLOUD_API_URL", "https://gestionale.test")
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "secret-test")
    monkeypatch.setattr(t.httpx, "AsyncClient", lambda **_kwargs: Client())

    result = run(t.nuovi_dipendenti())
    assert result["nuovi"][0]["candidato_operatore"]["id"] == "op-pocci"
