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


def test_lotti_admin_canonico_scelta_identita_e_vecchio_pin_revocato(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from app.lotti.routers import tablet_operatori as module
    db = AsyncMongoMockClient()["pin_unico_test"]
    monkeypatch.setattr(module, "db", db)

    async def scenario():
        for ident in ("a", "b"):
            await db.tablet_operatori.insert_one({
                "id": ident, "nome": "Admin " + ident, "attivo": True,
                "ruolo": "amministratore", "pin": module._hash_pin(OLD_PIN),
                "pin_lookup": module._pin_lookup(OLD_PIN),
            })
        result = await module.login_pin(module.PinLogin(pin=PIN))
        assert result["scelta_operatore"] is True
        assert "token" not in result
        assert {x["id"] for x in result["operatori"]} == {"a", "b"}
        assert await module.trova_operatori_per_pin(OLD_PIN) == []
        assert await module.pin_amministratore_valido(PIN)
        assert not await module.pin_amministratore_valido(OLD_PIN)
        with pytest.raises(HTTPException) as exc:
            await module.login_pin(module.PinLogin(pin=PIN, operatore_id="estraneo"))
        assert exc.value.status_code == 403
        assert (await module.login_pin(module.PinLogin(pin=PIN, operatore_id="b")))["operatore"]["id"] == "b"
        # Gli hash storici non vengono copiati, riscritti o riparati dal login.
        assert (await db.tablet_operatori.find_one({"id": "a"}))["pin_lookup"] == module._pin_lookup(OLD_PIN)
    asyncio.run(scenario())


def test_hr_rifiuta_pin_alternativo_e_non_promuove_utente(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from app.hr.routers import pin_login as module
    db = AsyncMongoMockClient()["hr_pin_test"]
    monkeypatch.setattr(module.Database, "get_db", lambda: db)
    module._FAILED_ATTEMPTS.clear()
    request = Request({"type": "http", "headers": [], "client": ("test", 1)})

    async def scenario():
        await db[module.Collections.USERS].insert_one({"id": "admin-test", "username": module.settings.PIN_ADMIN_USERNAME, "role": "admin", "name": "Admin test"})
        assert (await module.pin_login(request, {"pin": PIN}))["role"] == "admin"
        with pytest.raises(HTTPException) as exc:
            await module.pin_login(request, {"pin": OLD_PIN})
        assert exc.value.status_code == 401
        await db[module.Collections.USERS].update_one({"id": "admin-test"}, {"$set": {"role": "dipendente"}})
        with pytest.raises(HTTPException):
            await module.pin_login(request, {"pin": PIN})
    asyncio.run(scenario())


@pytest.mark.parametrize("admin_pin", [PIN, "872461938274"])
def test_hr_admin_personale_non_aggira_pin_centrale(monkeypatch, admin_pin):
    from mongomock_motor import AsyncMongoMockClient
    from app.hr.services import auth_dipendenti as module
    db = AsyncMongoMockClient()["hr_dip_pin_test"]
    monkeypatch.setattr(module.Database, "get_db", lambda: db)
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(admin_pin.encode()).hexdigest())

    async def scenario():
        await db[module.Collections.EMPLOYEES].insert_one({"id": "admin", "nome_completo": "Admin test", "ruolo_app": "admin", "pin_hash": module.hash_pin(OLD_PIN)})
        assert await module.login_dipendente("admin", OLD_PIN) is None
        assert (await module.login_dipendente("admin", admin_pin))["role"] == "admin"
        assert (await module.login_dipendente_per_nome("Admin test", admin_pin))["role"] == "admin"
        await db[module.Collections.EMPLOYEES].update_one({"id": "admin"}, {"$set": {"attivo": False}})
        assert await module.login_dipendente("admin", admin_pin) is None
    asyncio.run(scenario())
