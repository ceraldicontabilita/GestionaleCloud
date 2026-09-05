"""Menu: PIN centrale, firma obbligatoria, nessuna credenziale storica accettata."""
import asyncio
import hashlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.menu.models.qrcode_models import AdminPinLogin
from app.menu.routes import qrcode_routes as module

PIN = "74926183"  # fixture, non una credenziale reale


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(PIN.encode()).hexdigest())
    monkeypatch.setattr(module, "SECRET_KEY", "synthetic-menu-signing-key-for-tests-only")
    module.login_lockout._FAILED.clear()


def login(pin=PIN):
    request = Request({"type": "http", "headers": [], "client": ("menu-test", 1)})
    return asyncio.run(module.admin_login(AdminPinLogin(pin=pin), request))


def test_senza_firma_fallisce_chiuso(monkeypatch):
    monkeypatch.setattr(module, "SECRET_KEY", "")
    with pytest.raises(HTTPException) as exc:
        login()
    assert exc.value.status_code == 503


def test_senza_pin_centrale_non_accetta_credentiali_alternative(monkeypatch):
    monkeypatch.delenv("PIN_HASH_ADMIN", raising=False)
    monkeypatch.setenv("MENU_ADMIN_PASSWORD", PIN)
    with pytest.raises(HTTPException) as exc:
        login()
    assert exc.value.status_code == 503


def test_pin_centrale_corretto():
    result = login()
    assert result.success is True
    assert result.token


def test_pin_errato_non_emette_token():
    result = login("123456")
    assert result.success is False
    assert not result.token


def test_blocco_tentativi_condiviso():
    for _ in range(module.login_lockout.MAX_ATTEMPTS):
        login("123456")
    with pytest.raises(HTTPException) as exc:
        login()
    assert exc.value.status_code == 429


@pytest.mark.parametrize("token", [
    "non-un-token",
    module.jwt.encode({"sub": "admin"}, "different-synthetic-key-for-tests-only", algorithm="HS256"),
    module.jwt.encode({"sub": "admin"}, "synthetic-menu-signing-key-for-tests-only", algorithm="HS384"),
])
def test_token_corrotto_firma_errata_o_algoritmo_non_ammesso_risponde_401(token):
    with pytest.raises(HTTPException) as exc:
        module.verify_token(f"Bearer {token}")
    assert exc.value.status_code == 401


def test_token_emesso_dal_login_e_verificabile():
    assert module.verify_token(f"Bearer {login().token}") == module.ADMIN_USERNAME


def test_token_scaduto_risponde_401():
    token = module.jwt.encode({"sub": "admin", "exp": 1}, module.SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        module.verify_token(f"Bearer {token}")
    assert exc.value.status_code == 401
