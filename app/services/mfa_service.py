"""MFA TOTP per amministratori e approvatori.

I segreti TOTP sono cifrati prima di essere salvati. I codici di recupero
sono salvati esclusivamente come hash e possono essere usati una sola volta.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote

from cryptography.fernet import Fernet

from app.config import settings


COLLECTION = "mfa_settings"
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1
RECOVERY_CODES_COUNT = 8


def canonical_identity(user_id: str = "", email: str = "", role: str = "") -> str:
    # L'amministratore configurato via password e quello via PIN devono usare
    # la stessa iscrizione MFA anche se i rispettivi sub JWT sono diversi.
    if role == "admin":
        return "admin"
    return (user_id or email).strip().lower()


def _identity_key(identity: str) -> str:
    return hashlib.sha256(identity.strip().lower().encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    material = hashlib.sha256(("mfa-totp:" + settings.SECRET_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("ascii")


def _normalise_secret(secret: str) -> str:
    return secret.replace(" ", "").strip().upper()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    normalised = _normalise_secret(secret)
    padding = "=" * ((8 - len(normalised) % 8) % 8)
    return base64.b32decode(normalised + padding, casefold=True)


def totp_at(secret: str, counter: int) -> str:
    digest = hmac.new(
        _secret_bytes(secret), struct.pack(">Q", counter), hashlib.sha1
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def current_totp(secret: str, at_time: Optional[float] = None) -> str:
    return totp_at(secret, int((at_time if at_time is not None else time.time()) // TOTP_PERIOD_SECONDS))


def _matching_counter(secret: str, code: str, at_time: Optional[float] = None) -> Optional[int]:
    clean = str(code).replace(" ", "").strip()
    if len(clean) != TOTP_DIGITS or not clean.isdigit():
        return None
    current = int((at_time if at_time is not None else time.time()) // TOTP_PERIOD_SECONDS)
    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        counter = current + offset
        if counter >= 0 and hmac.compare_digest(totp_at(secret, counter), clean):
            return counter
    return None


def _recovery_hash(code: str) -> str:
    clean = code.replace("-", "").replace(" ", "").upper()
    return hashlib.sha256((settings.SECRET_KEY + ":recovery:" + clean).encode("utf-8")).hexdigest()


def _new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODES_COUNT):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


async def get_status(db, identity: str) -> Dict[str, Any]:
    doc = await db[COLLECTION].find_one(
        {"identity_key": _identity_key(identity)},
        {"_id": 0, "enabled": 1, "pending_created_at": 1, "recovery_code_hashes": 1},
    )
    return {
        "enabled": bool(doc and doc.get("enabled")),
        "setup_pending": bool(doc and doc.get("pending_created_at")),
        "recovery_codes_remaining": len((doc or {}).get("recovery_code_hashes") or []),
    }


async def is_enabled(db, identity: str) -> bool:
    return (await get_status(db, identity))["enabled"]


def _enrollment_payload(secret: str, revision: str, issuer: str) -> Dict[str, str]:
    setup_id = revision[:6].upper()
    label = quote(f"{issuer}:Amministratore [{setup_id}]")
    uri = (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&period={TOTP_PERIOD_SECONDS}&digits={TOTP_DIGITS}"
    )
    return {"secret": secret, "otpauth_uri": uri, "setup_id": setup_id}


async def start_enrollment(
    db,
    identity: str,
    issuer: str = "Impresa Semplice",
    regenerate: bool = False,
) -> Dict[str, str]:
    key = _identity_key(identity)
    existing = await db[COLLECTION].find_one({"identity_key": key})
    if existing and existing.get("enabled"):
        raise ValueError("MFA gia attiva")

    # Riaprire la procedura non deve invalidare una chiave gia acquisita
    # dall'Authenticator. Solo la rigenerazione esplicita sostituisce il segreto.
    if (
        not regenerate
        and existing
        and existing.get("pending_secret_encrypted")
        and existing.get("pending_revision")
    ):
        return _enrollment_payload(
            _decrypt(existing["pending_secret_encrypted"]),
            existing["pending_revision"],
            issuer,
        )

    secret = generate_totp_secret()
    revision = secrets.token_hex(16)
    now = datetime.now(timezone.utc)
    await db[COLLECTION].update_one(
        {"identity_key": key},
        {
            "$set": {
                "identity_key": key,
                "pending_secret_encrypted": _encrypt(secret),
                "pending_revision": revision,
                "pending_created_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "enabled": False},
        },
        upsert=True,
    )
    return _enrollment_payload(secret, revision, issuer)


async def confirm_enrollment(db, identity: str, code: str) -> list[str]:
    key = _identity_key(identity)
    doc = await db[COLLECTION].find_one({"identity_key": key})
    if not doc or not doc.get("pending_secret_encrypted") or not doc.get("pending_revision"):
        raise ValueError("Configurazione MFA non avviata")
    secret = _decrypt(doc["pending_secret_encrypted"])
    counter = _matching_counter(secret, code)
    if counter is None:
        raise ValueError("Codice di verifica non valido")
    recovery_codes = _new_recovery_codes()
    result = await db[COLLECTION].update_one(
        {"identity_key": key, "pending_revision": doc["pending_revision"]},
        {
            "$set": {
                "secret_encrypted": _encrypt(secret),
                "enabled": True,
                "enabled_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_used_counter": counter,
                "recovery_code_hashes": [_recovery_hash(item) for item in recovery_codes],
            },
            "$unset": {
                "pending_secret_encrypted": "",
                "pending_revision": "",
                "pending_created_at": "",
            },
        },
    )
    if getattr(result, "modified_count", 0) != 1:
        raise ValueError("Configurazione MFA cambiata: ripetere l'iscrizione")
    return recovery_codes


async def verify_code(db, identity: str, code: str) -> bool:
    key = _identity_key(identity)
    doc = await db[COLLECTION].find_one({"identity_key": key, "enabled": True})
    if not doc or not doc.get("secret_encrypted"):
        return False

    secret = _decrypt(doc["secret_encrypted"])
    counter = _matching_counter(secret, code)
    if counter is not None:
        last_used = doc.get("last_used_counter")
        if last_used is not None and counter <= int(last_used):
            return False
        result = await db[COLLECTION].update_one(
            {
                "identity_key": key,
                "enabled": True,
                "$or": [
                    {"last_used_counter": {"$lt": counter}},
                    {"last_used_counter": {"$exists": False}},
                ],
            },
            {"$set": {"last_used_counter": counter, "last_verified_at": datetime.now(timezone.utc)}},
        )
        return getattr(result, "modified_count", 0) == 1

    recovery_hash = _recovery_hash(str(code))
    hashes: Iterable[str] = doc.get("recovery_code_hashes") or []
    if not any(hmac.compare_digest(recovery_hash, item) for item in hashes):
        return False
    result = await db[COLLECTION].update_one(
        {"identity_key": key, "enabled": True, "recovery_code_hashes": recovery_hash},
        {
            "$pull": {"recovery_code_hashes": recovery_hash},
            "$set": {"last_verified_at": datetime.now(timezone.utc)},
        },
    )
    return getattr(result, "modified_count", 0) == 1


async def disable(db, identity: str) -> None:
    await db[COLLECTION].update_one(
        {"identity_key": _identity_key(identity)},
        {
            "$set": {"enabled": False, "updated_at": datetime.now(timezone.utc)},
            "$unset": {
                "secret_encrypted": "",
                "last_used_counter": "",
                "recovery_code_hashes": "",
                "pending_secret_encrypted": "",
                "pending_revision": "",
                "pending_created_at": "",
            },
        },
    )
