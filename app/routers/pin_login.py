"""
PIN Login router — consente l'accesso veloce via PIN (tastierino web/mobile).
Il PIN corretto concede un JWT admin, senza richiedere username/password.

Flow:
  POST /api/auth/pin-login
  body: {"pin": "123456"}
  → ritorna {"access_token": "...", "token_type": "bearer", ...}

Configurazione (variabili d'ambiente, basta UNA delle due):
  ADMIN_PIN      = PIN in chiaro (es. ADMIN_PIN=123456) — logica semplice,
                   stessa filosofia di ADMIN_PASSWORD nel login email.
  PIN_HASH_ADMIN = SHA-256 hex del PIN, per chi preferisce non tenere il PIN
                   in chiaro nell'ambiente:
                   python -c "import hashlib;print(hashlib.sha256(b'PIN').hexdigest())"

Se nessuna delle due è impostata, il login via PIN è disattivato (fail-safe)
e l'endpoint risponde 503 con un messaggio chiaro invece di un 401 generico.

Le variabili vengono lette A OGNI RICHIESTA (non all'import del modulo):
elimina i problemi di ordine di caricamento del file .env.
"""
from fastapi import APIRouter, HTTPException, Body, Request, Response, status
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import os
import hashlib
import hmac
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

# Username dell'utente admin a cui il PIN concede accesso, se esiste in
# collection users. Se non esiste NESSUN utente, il login funziona comunque
# con un'identita' admin sintetica (il sistema e' mono-utente: stesso
# comportamento del login email/password che vive solo di variabili ambiente).
PIN_ADMIN_USERNAME = "ceraldi"
PIN_ADMIN_EMAIL_DEFAULT = os.getenv("ADMIN_EMAIL", "ceraldigroupsrl@gmail.com")

# Durata del token emesso via PIN (in minuti). Default: stesso del login normale.
PIN_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def _verifica_pin(pin: str) -> Optional[bool]:
    """Confronta il PIN con la configurazione in ambiente.

    Ritorna True/False se il confronto e' possibile, None se il login PIN
    non e' configurato affatto (nessuna variabile impostata).
    """
    admin_pin = os.getenv("ADMIN_PIN", "").strip()
    pin_hash_admin = os.getenv("PIN_HASH_ADMIN", "").strip().lower()

    if admin_pin:
        return hmac.compare_digest(pin, admin_pin)
    if pin_hash_admin:
        pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
        return hmac.compare_digest(pin_hash, pin_hash_admin)
    return None

# ============================================================================
# ANTI BRUTE FORCE — modulo condiviso con il login email (5 tentativi / 5 min)
# ============================================================================
from app.utils import login_lockout

_client_ip = login_lockout.client_ip
_is_locked = login_lockout.seconds_locked
_register_failure = login_lockout.register_failure
_clear_failures = login_lockout.clear_failures


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
    response: Response,
    payload: Dict[str, Any] = Body(..., example={"pin": "<ADMIN_PIN>"}),
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

    # 1) PIN amministratore (ADMIN_PIN in chiaro o PIN_HASH_ADMIN SHA-256).
    esito = _verifica_pin(pin)
    user = None
    user_repo = None
    db = Database.get_db()

    if esito is True:
        # Admin: recupera l'identità dal DB se esiste, altrimenti sintetica.
        try:
            user_repo = UserRepository(db[Collections.USERS])
            try:
                user = await user_repo.find_by_username(PIN_ADMIN_USERNAME)
            except Exception:
                user = None
            if not user:
                user = await db[Collections.USERS].find_one({"role": "admin"})
            if not user:
                user = await db[Collections.USERS].find_one({"is_active": True})
        except Exception:
            logger.exception("PIN-login: lookup utente admin fallito, uso identita' sintetica")
            user_repo = None
        if not user:
            user = {
                "id": "admin",
                "email": PIN_ADMIN_EMAIL_DEFAULT,
                "name": "Amministratore",
                "role": "admin",
            }
    else:
        # 2) PIN di un utente creato dall'admin (Operatore / Sola lettura).
        from app.services import utenti_pin as _utenti_pin
        match = await _utenti_pin.verifica_pin(db, pin)
        if match:
            user = {
                "id": match["id"],
                "email": "",
                "name": match.get("nome"),
                "role": match.get("ruolo", "operatore"),
            }
        else:
            # Nessuna corrispondenza. Se NEANCHE l'admin-PIN è configurato e non
            # esistono utenti, il login PIN è del tutto disattivato → 503.
            _register_failure(ip)
            if esito is None:
                try:
                    n_utenti = await db[_utenti_pin.COLLECTION].count_documents({"attivo": True})
                except Exception:
                    n_utenti = 0
                if n_utenti == 0:
                    logger.error("PIN-login: nessun ADMIN_PIN e nessun utente PIN configurato")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Login PIN non configurato sul server",
                    )
            logger.warning(f"PIN-login: PIN errato da IP {ip}")
            try:
                from app.services.audit_logger import log_sicurezza
                await log_sicurezza(db, azione="login_fallito",
                                    dettaglio="PIN errato", utente="pin", ip=ip)
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="PIN non valido")

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
        "tipo": user.get("role", "admin"),
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
        if user_repo is not None:
            await user_repo.update_last_login(user_id)
    except Exception:
        pass

    # Reset tentativi per questo IP
    _clear_failures(ip)

    logger.info(f"PIN-login OK · IP {ip} · user {user_id} · role {user.get('role')}")
    try:
        from app.services.audit_logger import log_sicurezza
        await log_sicurezza(db, azione="login_ok", dettaglio="Login PIN riuscito",
                            utente=user.get("name") or user_id, ip=ip,
                            extra={"ruolo": user.get("role")})
    except Exception:
        pass

    # Cookie di sessione: permette di aprire i link diretti alle API
    # (es. "Vedi fattura" in nuova scheda) senza header Authorization.
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=PIN_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

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
    """Verifica che il router PIN sia registrato e configurato.

    Diagnostica: dice QUALE variabile e' attiva senza rivelarne il valore.
    """
    admin_pin_set = bool(os.getenv("ADMIN_PIN", "").strip())
    pin_hash_set = bool(os.getenv("PIN_HASH_ADMIN", "").strip())
    return {
        "ok": True,
        "configured": admin_pin_set or pin_hash_set,
        "fonte": "ADMIN_PIN" if admin_pin_set else ("PIN_HASH_ADMIN" if pin_hash_set else None),
        "admin_username": PIN_ADMIN_USERNAME,
        "token_expire_minutes": PIN_TOKEN_EXPIRE_MINUTES,
    }
