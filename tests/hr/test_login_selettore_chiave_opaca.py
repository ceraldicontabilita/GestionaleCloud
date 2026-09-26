"""Selettore «tocca il tuo nome» del portale HR: i nomi si vedono, gli id no.

`/hr/api/auth/dipendenti-attivi` e' pubblico. Prima restituiva l'id interno
dell'anagrafica (quello che usano router HR, Lotti e ponti del gestionale);
ora per ogni nome da' solo una chiave opaca che vale soltanto per il login.
Credenziali esclusivamente sintetiche; nessuna connessione ai dati reali.
"""
import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

PIN_MARIO = "4821"  # fixture, non un PIN reale
PIN_ANNA = "7302"
PIN_ALTRA_ANNA = "9154"


@pytest.fixture
def ambiente(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from app.hr.config import settings
    from app.hr.routers import pin_login
    from app.hr.services import auth_dipendenti
    from app.utils import login_lockout

    monkeypatch.setattr(settings, "SECRET_KEY", "segreto-hr-del-test-chiave-opaca-123456")
    db = AsyncMongoMockClient()["hr_selettore_test"]
    monkeypatch.setattr(auth_dipendenti.Database, "get_db", lambda: db)
    monkeypatch.setattr(pin_login.Database, "get_db", lambda: db)
    login_lockout.clear_failures("test")
    hp = auth_dipendenti.hash_pin

    async def semina():
        await db[auth_dipendenti.Collections.EMPLOYEES].insert_many([
            {"id": "dip-mario-001", "nome": "Mario", "cognome": "Rossi", "nome_completo": "Rossi Mario",
             "stato": "attivo", "ruolo_app": "dipendente", "pin_hash": hp(PIN_MARIO)},
            {"id": "dip-anna-002", "nome": "Anna", "cognome": "Bianchi", "nome_completo": "Bianchi Anna",
             "stato": "attivo", "ruolo_app": "dipendente", "pin_hash": hp(PIN_ANNA)},
            {"id": "dip-anna-003", "nome": "Anna", "cognome": "Verdi", "nome_completo": "Verdi Anna",
             "stato": "attivo", "ruolo_app": "dipendente", "pin_hash": hp(PIN_ALTRA_ANNA)},
            # senza PIN: non selezionabile
            {"id": "dip-nopin-004", "nome": "Luca", "cognome": "Neri", "stato": "attivo"},
            # cessato: non selezionabile
            {"id": "dip-cessato-005", "nome": "Paolo", "cognome": "Gialli", "stato": "cessato",
             "pin_hash": hp("5555")},
            # amministratore, con o senza PIN personale: entra dal Gestionale
            {"id": "dip-admin-006", "nome": "Titolare", "cognome": "Ceraldi", "stato": "attivo",
             "ruolo_app": "admin"},
            {"id": "dip-admin-007", "nome": "Socio", "cognome": "Ceraldi", "stato": "attivo",
             "ruolo_app": "admin", "pin_hash": hp("6666")},
        ])
    asyncio.run(semina())
    return pin_login, auth_dipendenti


def _richiesta():
    return Request({"type": "http", "headers": [], "client": ("test", 1)})


def test_elenco_senza_id_interni_e_con_nomi_distinti(ambiente):
    pin_login, _ = ambiente
    risposta = asyncio.run(pin_login.dipendenti_attivi())
    testo = json.dumps(risposta)
    for id_interno in ("dip-mario-001", "dip-anna-002", "dip-anna-003", "dip-admin-006", "dip-admin-007"):
        assert id_interno not in testo
    voci = risposta["dipendenti"]
    assert all(set(v) == {"chiave", "nome"} for v in voci)
    # omonimi di nome: iniziale del cognome; gli altri solo il nome
    assert [v["nome"] for v in voci] == ["Anna B.", "Anna V.", "Mario"]
    # niente amministratori, cessati o persone senza PIN
    assert not any(n in testo for n in ("Titolare", "Socio", "Luca", "Paolo"))


def test_login_con_chiave_opaca_funziona(ambiente):
    pin_login, _ = ambiente
    voci = asyncio.run(pin_login.dipendenti_attivi())["dipendenti"]
    mario = next(v for v in voci if v["nome"] == "Mario")
    esito = asyncio.run(pin_login.pin_login(_richiesta(), {"dipendente_id": mario["chiave"], "pin": PIN_MARIO}))
    assert esito["user_id"] == "dip-mario-001" and esito["role"] == "dipendente"
    # due omonimi: ognuno entra solo col proprio PIN
    anna_b = next(v for v in voci if v["nome"] == "Anna B.")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pin_login.pin_login(_richiesta(), {"dipendente_id": anna_b["chiave"], "pin": PIN_ALTRA_ANNA}))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("chiave", [
    "0" * 32,                 # inventata, formato giusto
    "dip-mario-001",          # l'id interno non vale piu' come chiave
    "zz" * 16,                # non esadecimale
])
def test_chiave_inventata_o_id_interno_falliscono(ambiente, chiave):
    pin_login, auth_dipendenti = ambiente
    assert asyncio.run(auth_dipendenti.login_dipendente_da_chiave(chiave, PIN_MARIO)) is None
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pin_login.pin_login(_richiesta(), {"dipendente_id": chiave, "pin": PIN_MARIO}))
    assert exc.value.status_code == 401
    assert asyncio.run(auth_dipendenti.login_dipendente_da_chiave("", PIN_MARIO)) is None


def test_chiave_di_non_selezionabili_non_apre(ambiente):
    _, auth_dipendenti = ambiente
    for id_interno, pin in (("dip-cessato-005", "5555"), ("dip-admin-007", "6666")):
        chiave = auth_dipendenti.chiave_login(id_interno)
        assert asyncio.run(auth_dipendenti.login_dipendente_da_chiave(chiave, pin)) is None


def test_chiave_dipende_dal_segreto(ambiente, monkeypatch):
    _, auth_dipendenti = ambiente
    from app.hr.config import settings
    prima = auth_dipendenti.chiave_login("dip-mario-001")
    monkeypatch.setattr(settings, "SECRET_KEY", "un-altro-segreto-hr-del-test-987654321")
    assert auth_dipendenti.chiave_login("dip-mario-001") != prima
    assert asyncio.run(auth_dipendenti.login_dipendente_da_chiave(prima, PIN_MARIO)) is None
