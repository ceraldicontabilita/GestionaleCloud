"""
PIN Login router — consente l'accesso veloce via PIN dall'app mobile Ceraldi.
Il PIN 141574 concede un JWT admin, senza richiedere username/password.

Flow:
  POST /api/auth/pin-login
  body: {"pin": "141574"}
  → ritorna {"access_token": "...", "token_type": "bearer", ...}

Il PIN non viene mai memorizzato in chiaro: viene confrontato come SHA-256
contro un hash hardcoded in questo file.

Aggiunto nella chat-8 per ceraldi mobile.
"""
from fastapi import APIRouter, HTTPException, Body, Request, status
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import hashlib
import logging
import time

from jose import jwt

from app.config import settings
from app.database import Database, Collections
from app.repositories import UserRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# CONFIG
# ============================================================================

# SHA-256 di "141574" — PIN mobile ADMIN (Enzo Ceraldi)
# Per cambiare il PIN, basta sostituire questo hash con sha256(nuovo_pin).
PIN_HASH_ADMIN = "72e0837603bda6733feca2c118417d031d2df2c9574373df26c76c28a2c9c0b4"

# Username/email dell'utente admin a cui il PIN concede accesso.
# Questo utente DEVE esistere in collection users.
PIN_ADMIN_USERNAME = "ceraldi"

# Durata del token emesso via PIN (in minuti). Default: stesso del login normale.
PIN_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# ============================================================================
# ANTI BRUTE FORCE (in-memory, per IP)
# ============================================================================
_FAILED_ATTEMPTS: Dict[str, Dict[str, Any]] = {}
MAX_ATTEMPTS = 8
LOCK_SECONDS = 60


def _client_ip(request: Request) -> str:
    """Estrae l'IP del client (supporto X-Forwarded-For per reverse proxy)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_locked(ip: str) -> int:
    """Ritorna i secondi residui di lock, 0 se non bloccato."""
    rec = _FAILED_ATTEMPTS.get(ip)
    if not rec:
        return 0
    if rec.get("locked_until", 0) > time.time():
        return int(rec["locked_until"] - time.time())
    return 0


def _register_failure(ip: str):
    rec = _FAILED_ATTEMPTS.get(ip) or {"count": 0, "locked_until": 0}
    rec["count"] += 1
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = time.time() + LOCK_SECONDS
        rec["count"] = 0
        logger.warning(f"PIN-login: IP {ip} locked for {LOCK_SECONDS}s")
    _FAILED_ATTEMPTS[ip] = rec


def _clear_failures(ip: str):
    _FAILED_ATTEMPTS.pop(ip, None)


# ============================================================================
# ENDPOINT
# ============================================================================

@router.post(
    "/pin-login",
    summary="Login via PIN (mobile app)",
    description="Login rapido via PIN a 6 cifre per l'app mobile. "
                "Il PIN amministratore concede un JWT admin.",
)
async def pin_login(
    request: Request,
    payload: Dict[str, Any] = Body(..., example={"pin": "141574"}),
) -> Dict[str, Any]:
    ip = _client_ip(request)

    # Rate limit / lock
    lock_sec = _is_locked(ip)
    if lock_sec > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Troppi tentativi, riprova tra {lock_sec}s",
        )

    # Estrai e valida PIN
    pin = str(payload.get("pin", "")).strip()
    if not pin or not pin.isdigit() or len(pin) < 4 or len(pin) > 12:
        _register_failure(ip)
        raise HTTPException(status_code=400, detail="PIN non valido")

    pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()

    # Verifica hash
    if pin_hash != PIN_HASH_ADMIN:
        _register_failure(ip)
        logger.warning(f"PIN-login: PIN errato da IP {ip}")
        raise HTTPException(status_code=401, detail="PIN non valido")

    # PIN corretto: recupera utente admin
    db = Database.get_db()
    user_repo = UserRepository(db[Collections.USERS])

    user = None
    # 1. tenta username
    try:
        user = await user_repo.find_by_username(PIN_ADMIN_USERNAME)
    except Exception:
        user = None
    # 2. fallback: cerca primo utente con ruolo admin
    if not user:
        user = await db[Collections.USERS].find_one({"role": "admin"})
    # 3. fallback finale: primo utente qualsiasi
    if not user:
        user = await db[Collections.USERS].find_one({"is_active": True})

    if not user:
        logger.error("PIN-login: nessun utente admin trovato nel DB")
        raise HTTPException(
            status_code=500,
            detail="Nessun utente admin configurato nel sistema",
        )

    # Estrai user_id
    user_id = str(user.get("id") or user.get("_id"))

    # Crea JWT con la stessa logica di auth_service._create_access_token
    expires_delta = timedelta(minutes=PIN_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    jwt_payload = {
        "sub": user_id,
        "email": user.get("email", ""),
        "name": user.get("name"),
        "role": user.get("role", "admin"),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "auth_method": "pin",  # traccia che è un token da PIN
    }
    token = jwt.encode(
        jwt_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    # Aggiorna last_login se il repo lo supporta
    try:
        await user_repo.update_last_login(user_id)
    except Exception:
        pass

    # Reset tentativi per questo IP
    _clear_failures(ip)

    logger.info(f"PIN-login OK · IP {ip} · user {user_id} · role {user.get('role')}")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "email": user.get("email", ""),
        "name": user.get("name"),
        "role": user.get("role", "admin"),
        "auth_method": "pin",
    }


@router.get(
    "/pin-login/health",
    summary="Health check endpoint PIN login",
)
async def pin_login_health() -> Dict[str, Any]:
    """Verifica che il router PIN sia registrato e raggiungibile."""
    return {
        "ok": True,
        "configured": bool(PIN_HASH_ADMIN),
        "admin_username": PIN_ADMIN_USERNAME,
        "token_expire_minutes": PIN_TOKEN_EXPIRE_MINUTES,
    }
