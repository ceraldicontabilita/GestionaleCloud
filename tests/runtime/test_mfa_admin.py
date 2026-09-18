import asyncio
import hashlib
import pytest
from fastapi import HTTPException, Response
from app.services.sheets_document_store import MemorySheetsClient
from starlette.requests import Request

from app.services import mfa_service
from app.utils.auth_tokens import create_mfa_challenge, decode_mfa_challenge
from app.utils.dependencies import get_current_admin_mfa_user


@pytest.fixture
def db():
    return MemorySheetsClient()["mfa_test"]


def _request(path: str, ip: str) -> Request:
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [], "client": (ip, 12345),
        "scheme": "https", "server": ("testserver", 443),
    })


def _enable_mfa(db, monkeypatch, now=1_800_000_000.0):
    monkeypatch.setattr(mfa_service.time, "time", lambda: now)
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    asyncio.run(mfa_service.confirm_enrollment(
        db, "admin", mfa_service.current_totp(setup["secret"])
    ))
    return setup


def test_iscrizione_cifra_segreto_e_non_salva_plaintext(db, monkeypatch):
    now = 1_800_000_000.0
    monkeypatch.setattr(mfa_service.time, "time", lambda: now)
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    secret = setup["secret"]
    doc_pending = asyncio.run(db[mfa_service.COLLECTION].find_one({}))
    assert secret not in str(doc_pending)
    assert setup["otpauth_uri"].startswith("otpauth://totp/")

    recovery = asyncio.run(mfa_service.confirm_enrollment(
        db, "admin", mfa_service.current_totp(secret)
    ))
    doc = asyncio.run(db[mfa_service.COLLECTION].find_one({}))
    assert doc["enabled"] is True
    assert secret not in str(doc)
    assert all(code not in str(doc) for code in recovery)
    assert len(recovery) == mfa_service.RECOVERY_CODES_COUNT


def test_riapertura_setup_riusa_la_stessa_configurazione(db, monkeypatch):
    monkeypatch.setattr(mfa_service.time, "time", lambda: 1_800_000_000.0)
    first = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    reopened = asyncio.run(mfa_service.start_enrollment(db, "admin"))

    assert reopened["secret"] == first["secret"]
    assert reopened["setup_id"] == first["setup_id"]
    asyncio.run(mfa_service.confirm_enrollment(
        db, "admin", mfa_service.current_totp(first["secret"])
    ))


def test_rigenerazione_esplicita_invalida_solo_la_configurazione_precedente(
    db, monkeypatch
):
    monkeypatch.setattr(mfa_service.time, "time", lambda: 1_800_000_000.0)
    first = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    regenerated = asyncio.run(
        mfa_service.start_enrollment(db, "admin", regenerate=True)
    )

    assert regenerated["secret"] != first["secret"]
    assert regenerated["setup_id"] != first["setup_id"]
    with pytest.raises(ValueError, match="Codice di verifica non valido"):
        asyncio.run(mfa_service.confirm_enrollment(
            db, "admin", mfa_service.current_totp(first["secret"])
        ))
    asyncio.run(mfa_service.confirm_enrollment(
        db, "admin", mfa_service.current_totp(regenerated["secret"])
    ))


def test_totp_non_riutilizzabile_e_finestra_temporale(db, monkeypatch):
    clock = {"value": 1_800_000_000.0}
    monkeypatch.setattr(mfa_service.time, "time", lambda: clock["value"])
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    first = mfa_service.current_totp(setup["secret"])
    asyncio.run(mfa_service.confirm_enrollment(db, "admin", first))

    assert asyncio.run(mfa_service.verify_code(db, "admin", first)) is False
    clock["value"] += mfa_service.TOTP_PERIOD_SECONDS
    second = mfa_service.current_totp(setup["secret"])
    assert asyncio.run(mfa_service.verify_code(db, "admin", second)) is True
    assert asyncio.run(mfa_service.verify_code(db, "admin", second)) is False


def test_codice_recupero_e_monouso(db, monkeypatch):
    monkeypatch.setattr(mfa_service.time, "time", lambda: 1_800_000_000.0)
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    codes = asyncio.run(mfa_service.confirm_enrollment(
        db, "admin", mfa_service.current_totp(setup["secret"])
    ))
    assert asyncio.run(mfa_service.verify_code(db, "admin", codes[0])) is True
    assert asyncio.run(mfa_service.verify_code(db, "admin", codes[0])) is False
    assert asyncio.run(mfa_service.get_status(db, "admin"))["recovery_codes_remaining"] == len(codes) - 1


def test_challenge_mfa_ha_scopo_e_non_contiene_segreti():
    token = create_mfa_challenge(
        {"id": "admin", "email": "admin@example.invalid", "name": "Admin", "role": "admin"},
        "pin",
    )
    payload = decode_mfa_challenge(token)
    assert payload["purpose"] == "mfa_login"
    assert payload["auth_method"] == "pin"
    assert "secret" not in payload
    assert "mfa_verified" not in payload


def test_approvazioni_falliscono_senza_iscrizione_mfa(db, monkeypatch):
    from app.database import Database
    monkeypatch.setattr(Database, "db", db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_admin_mfa_user(
            {"user_id": "admin", "role": "admin", "mfa_verified": False}
        ))
    assert exc.value.status_code == 428
    assert "Configura MFA" in exc.value.detail


def test_approvazioni_falliscono_con_mfa_non_verificata(db, monkeypatch):
    clock = 1_800_000_000.0
    monkeypatch.setattr(mfa_service.time, "time", lambda: clock)
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    asyncio.run(mfa_service.confirm_enrollment(db, "admin", mfa_service.current_totp(setup["secret"])))
    from app.database import Database
    monkeypatch.setattr(Database, "db", db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_admin_mfa_user(
            {"user_id": "admin", "role": "admin", "mfa_verified": False}
        ))
    assert exc.value.status_code == 428
    assert "Verifica MFA" in exc.value.detail

    approved = asyncio.run(get_current_admin_mfa_user(
        {"user_id": "admin", "role": "admin", "mfa_verified": True}
    ))
    assert approved["mfa_verified"] is True


def test_disattivazione_elimina_materiale_mfa(db, monkeypatch):
    monkeypatch.setattr(mfa_service.time, "time", lambda: 1_800_000_000.0)
    setup = asyncio.run(mfa_service.start_enrollment(db, "admin"))
    asyncio.run(mfa_service.confirm_enrollment(db, "admin", mfa_service.current_totp(setup["secret"])))
    asyncio.run(mfa_service.disable(db, "admin"))
    doc = asyncio.run(db[mfa_service.COLLECTION].find_one({}))
    assert doc["enabled"] is False
    assert "secret_encrypted" not in doc
    assert "recovery_code_hashes" not in doc


def test_login_password_con_mfa_non_emette_sessione(db, monkeypatch):
    import app.routers.auth as auth_mod
    from app.database import Database

    _enable_mfa(db, monkeypatch)
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(auth_mod, "_check_password", lambda _plain: True)
    response = Response()
    result = asyncio.run(auth_mod.auth_login(
        auth_mod.LoginRequest(email=auth_mod.ADMIN_EMAIL, password="non-salvata"),
        _request("/api/auth/login", "127.0.0.71"),
        response,
    ))
    assert result["mfa_required"] is True
    assert decode_mfa_challenge(result["challenge_token"])["auth_method"] == "password"
    assert "access_token" not in response.headers.get("set-cookie", "")


def test_login_pin_con_mfa_non_emette_sessione(db, monkeypatch):
    import app.routers.pin_login as pin_mod
    from app.database import Database

    _enable_mfa(db, monkeypatch)
    monkeypatch.setattr(Database, "db", db)
    pin = "135790"
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(pin.encode()).hexdigest())
    response = Response()
    result = asyncio.run(pin_mod.pin_login(
        _request("/api/auth/pin-login", "127.0.0.72"),
        response,
        {"pin": pin},
    ))
    assert result["mfa_required"] is True
    assert decode_mfa_challenge(result["challenge_token"])["auth_method"] == "pin"
    assert "access_token" not in response.headers.get("set-cookie", "")
