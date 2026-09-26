"""Credenziali esclusivamente sintetiche; nessuna connessione ai dati reali."""
import asyncio
import hashlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.services.admin_pin import configured, verify_admin_pin

PIN = "87246193"  # fixture, non un PIN reale
OLD_PIN = "359172"  # fixture di credenziale ritirata


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(PIN.encode()).hexdigest())
    monkeypatch.setenv("AUTH_SECRET", "test-only-lotti-secret-at-least-32-chars")
    monkeypatch.delenv("LOTTI_SUPABASE_URL", raising=False)
    monkeypatch.delenv("HR_MONGO_URL", raising=False)
    monkeypatch.delenv("MONGO_URL", raising=False)


def test_verifica_unica_e_rotazione_a_runtime(monkeypatch):
    assert configured()
    assert verify_admin_pin(PIN) is True
    assert verify_admin_pin(OLD_PIN) is False
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(OLD_PIN.encode()).hexdigest())
    assert verify_admin_pin(PIN) is False
    assert verify_admin_pin(OLD_PIN) is True


@pytest.mark.parametrize("value", ["", "not-a-hash", "0" * 63])
def test_configurazione_invalida_non_accetta_fallback(monkeypatch, value):
    monkeypatch.setenv("PIN_HASH_ADMIN", value)
    monkeypatch.setenv("HR_PIN_CODE", PIN)
    monkeypatch.setenv("ADMIN_PIN", PIN)
    assert not configured()
    assert verify_admin_pin(PIN) is None


@pytest.mark.parametrize("pin", ["123", "1" * 13, "abcdefgh", "１２３４"])
def test_formati_non_validi(pin):
    assert verify_admin_pin(pin) is False


def test_lotti_il_pin_centrale_non_apre_nulla_e_il_personale_non_e_admin(monkeypatch):
    """Il PIN amministratore si digita solo nel login del Gestionale. In Lotti
    non apre pagine (niente `/verifica-admin`), non e' una firma, e il login
    del tablet non conferma nemmeno che fosse giusto. Il PIN personale del
    titolare lo fa entrare come se stesso, da operatore: l'amministrazione di
    Lotti si apre solo dalla sessione del Gestionale."""
    from mongomock_motor import AsyncMongoMockClient
    from app.lotti.routers import tablet_operatori as module
    from app.hr.database import Database as DatabaseHR
    from app.hr.services import auth_dipendenti
    db = AsyncMongoMockClient()["pin_unico_test"]
    hr = AsyncMongoMockClient()["pin_unico_hr"]
    monkeypatch.setattr(module, "db", db)
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))

    async def scenario():
        await hr.dipendenti.insert_many([
            {"id": "hr-v", "nome": "Vincenzo", "cognome": "Ceraldi", "ruolo_app": "admin", "stato": "attivo", "attivo": True,
             "pin_hash": auth_dipendenti.hash_pin(OLD_PIN)},
            {"id": "hr-b", "nome": "Valerio", "cognome": "Ceraldi", "ruolo_app": "admin", "stato": "attivo", "attivo": True},
        ])
        assert not hasattr(module, "verifica_admin")
        with pytest.raises(HTTPException) as exc:
            await module.login_pin(module.PinLogin(pin=PIN))
        assert exc.value.status_code == 401 and exc.value.detail == "PIN non riconosciuto"
        result = await module.login_pin(module.PinLogin(pin=OLD_PIN))
        assert result["operatore"]["nome"] == "Ceraldi Vincenzo" and result["operatore"]["ruolo"] == "operatore"
        assert result["operatore"]["dipendente_id"] == "hr-v" and result["token"]
        from app.lotti.auth import verify_token
        dati = verify_token(result["token"])
        assert dati["sub"] == "hr-v" and dati["ruolo"] == "operatore"
    asyncio.run(scenario())


def test_hr_nessun_login_admin_col_pin(monkeypatch):
    """HR non ha piu' un ramo amministratore nel login PIN: l'admin entra
    solo dalla sessione del Gestionale (`/session`)."""
    from mongomock_motor import AsyncMongoMockClient
    from app.hr.routers import pin_login as module
    db = AsyncMongoMockClient()["hr_pin_test"]
    monkeypatch.setattr(module.Database, "get_db", lambda: db)
    request = Request({"type": "http", "headers": [], "client": ("test", 1)})

    async def scenario():
        await db[module.Collections.USERS].insert_one({"id": "admin-test", "username": module.settings.PIN_ADMIN_USERNAME, "role": "admin", "name": "Admin test"})
        for pin in (PIN, OLD_PIN):
            with pytest.raises(HTTPException) as exc:
                await module.pin_login(request, {"pin": pin})
            assert exc.value.status_code == 400
    asyncio.run(scenario())
    assert not any(getattr(r, "path", "") == "/pin-login/health" for r in module.router.routes)


@pytest.mark.parametrize("admin_pin", [PIN, "872461938274"])
def test_hr_admin_non_entra_dal_login_dipendente(monkeypatch, admin_pin):
    from mongomock_motor import AsyncMongoMockClient
    from app.hr.services import auth_dipendenti as module
    db = AsyncMongoMockClient()["hr_dip_pin_test"]
    monkeypatch.setattr(module.Database, "get_db", lambda: db)
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(admin_pin.encode()).hexdigest())

    async def scenario():
        await db[module.Collections.EMPLOYEES].insert_one({"id": "admin", "nome_completo": "Admin test", "ruolo_app": "admin", "pin_hash": module.hash_pin(OLD_PIN)})
        # Il PIN amministratore si digita solo nel login del Gestionale: dal
        # login dipendente un amministratore non entra, ne' col PIN centrale
        # ne' col suo PIN personale (quello serve alla firma HACCP).
        assert await module.login_dipendente("admin", OLD_PIN) is None
        assert await module.login_dipendente("admin", admin_pin) is None
        assert await module.login_dipendente_per_nome("Admin test", admin_pin) is None
        assert await module.login_dipendente_per_nome("Admin test", OLD_PIN) is None
        assert await module.login_dipendente_da_chiave(module.chiave_login("admin"), admin_pin) is None
    asyncio.run(scenario())


def test_motore_pin_canonico_risolve_admin_e_utente(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from app.services import pin_authentication, utenti_pin

    db = AsyncMongoMockClient()["pin_auth_canonica"]

    async def scenario():
        admin = await pin_authentication.authenticate_pin(db, PIN)
        assert admin is not None
        assert admin.role == "admin"
        assert admin.source == "admin_pin"

        user = await utenti_pin.crea_utente(db, "Operatore test", "operatore", OLD_PIN)
        identity = await pin_authentication.authenticate_pin(db, OLD_PIN)
        assert identity is not None
        assert identity.id == user["id"]
        assert identity.role == "operatore"
        assert identity.source == "utente_pin"

        assert await pin_authentication.authenticate_pin(db, "111111") is None

    asyncio.run(scenario())


def test_utenti_pin_non_possono_riusare_il_pin_admin_canonico(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from app.services import utenti_pin

    db = AsyncMongoMockClient()["pin_collisione"]
    monkeypatch.setenv("ADMIN_PIN", OLD_PIN)

    async def scenario():
        with pytest.raises(ValueError, match="riservato"):
            await utenti_pin.crea_utente(db, "Collisione admin", "operatore", PIN)

        created = await utenti_pin.crea_utente(db, "Utente valido", "operatore", OLD_PIN)
        with pytest.raises(ValueError, match="riservato"):
            await utenti_pin.aggiorna_utente(db, created["id"], pin=PIN)

    asyncio.run(scenario())
