"""
PIN Login router — accesso rapido via PIN dall'app mobile Ceraldi.

Il PIN è UNICO e FISSO, concede un JWT admin. Il valore vive SOLO nelle env
di Render (PIN_CODE): non è mai scritto nel codice. Viene confrontato come
hash SHA-256 calcolato a runtime, mai persistito in chiaro.

Flow:
  POST /api/auth/pin-login   body: {"pin": "<pin>"}
  -> {"access_token": "...", "token_type": "bearer", ...}
"""
from fastapi import APIRouter, HTTPException, Body, Request, status
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import hashlib
import hmac
import logging
import os
import time

from jose import jwt

from app.hr.config import settings
from app.hr.database import Database, Collections
from app.hr.repositories import UserRepository
from app.hr.services.auth_dipendenti import (
    login_dipendente, login_dipendente_per_nome, operatore_amministratore,
    elenco_dipendenti_per_login,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Durata della sessione admin (PIN) — default 7 giorni, stessa durata e stessa
# filosofia della sessione dipendente/portale: resta valida finché non scade
# davvero o non si preme "Esci" esplicitamente, niente re-login a metà lavoro
# solo per un cambio pagina. (Prima erano 2 ore: con RequireRole che controlla
# l'exp del JWT a OGNI navigazione in main.jsx, bastava restare sull'app oltre
# le 2 ore perché il primo cambio pagina seguente rimandasse al PIN — richiesta
# titolare 04/09/2026: "non devo reinserirlo ad ogni cambio pagina o uscita".)
# Configurabile via env Render HR_ADMIN_TOKEN_EXPIRE_MINUTES. Riguarda SOLO i
# token admin emessi qui; il token del portale dipendente ha la sua scadenza
# nel service (ACCESS_TOKEN_EXPIRE_MINUTES, anch'esso 7 giorni).
PIN_TOKEN_EXPIRE_MINUTES = int(os.environ.get("HR_ADMIN_TOKEN_EXPIRE_MINUTES")
                               or os.environ.get("ADMIN_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))

# ---- anti brute force (in-memory, per IP) ----
_FAILED_ATTEMPTS: Dict[str, Dict[str, Any]] = {}
MAX_ATTEMPTS = 8
LOCK_SECONDS = 60


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_locked(ip: str) -> int:
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
        logger.warning(f"PIN-login: IP {ip} bloccato per {LOCK_SECONDS}s")
    _FAILED_ATTEMPTS[ip] = rec


def _clear_failures(ip: str):
    _FAILED_ATTEMPTS.pop(ip, None)


def _pin_ok(pin: str) -> bool:
    """Confronto costante tra l'hash del PIN inviato e quello configurato (env)."""
    configured = settings.PIN_CODE or ""
    if not configured:
        return False
    sent = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    expected = hashlib.sha256(configured.encode("utf-8")).hexdigest()
    return hmac.compare_digest(sent, expected)


@router.get("/dipendenti-attivi", summary="Nomi per il selettore di login del portale")
async def dipendenti_attivi() -> Dict[str, Any]:
    """Elenco pubblico (nessuna autenticazione) di id+nome dei dipendenti
    attivi, per il tocca-il-tuo-nome in login — niente digitazione. Include
    anche chi usa solo il PIN condiviso della cassa (nessun pin_hash proprio),
    perché login_dipendente() accetta entrambe le fonti. Solo id+nome: nessun
    altro dato (PIN, ruolo, mansione...) esposto qui."""
    return {"dipendenti": await elenco_dipendenti_per_login()}


@router.post("/pin-login", summary="Login via PIN (mobile app)")
async def pin_login(
    request: Request,
    payload: Dict[str, Any] = Body(..., example={"pin": "******"}),
) -> Dict[str, Any]:
    ip = _client_ip(request)

    lock_sec = _is_locked(ip)
    if lock_sec > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Troppi tentativi, riprova tra {lock_sec}s")

    pin = str(payload.get("pin", "")).strip()
    dipendente_id = payload.get("dipendente_id")
    nome = str(payload.get("nome", "")).strip()

    # --- Ramo dipendente: cognome (o nome e cognome) + PIN personale.
    # Nessun elenco di nomi viene mai esposto prima dell'autenticazione. ---
    if nome and not dipendente_id:
        result = await login_dipendente_per_nome(nome, pin)
        if not result:
            _register_failure(ip)
            logger.warning(f"PIN-login per nome fallito da IP {ip}")
            raise HTTPException(401, "Nome o PIN non validi")
        _clear_failures(ip)
        try:
            from app.hr.services.audit_logger import log_evento
            await log_evento(
                modulo="accesso", azione="login",
                entita_id=result["user_id"], entita_collection="dipendenti",
                db=Database.get_db(), fonte="portale", utente=result["user_id"],
                dettaglio="Accesso al portale via nome+PIN", extra={"ip": ip},
            )
        except Exception:
            pass
        logger.info(f"PIN-login per nome OK · IP {ip} · {result['user_id']} · {result['role']}")
        return result

    # --- Ramo dipendente (legacy): dipendente_id + PIN personale ---
    if dipendente_id:
        result = await login_dipendente(str(dipendente_id), pin)
        if not result:
            _register_failure(ip)
            logger.warning(f"PIN-login dipendente fallito da IP {ip}")
            raise HTTPException(401, "Credenziali non valide")
        _clear_failures(ip)
        try:
            from app.hr.services.audit_logger import log_evento
            await log_evento(
                modulo="accesso", azione="login",
                entita_id=result["user_id"], entita_collection="dipendenti",
                db=Database.get_db(), fonte="portale", utente=result["user_id"],
                dettaglio="Accesso al portale via PIN", extra={"ip": ip},
            )
        except Exception:
            pass
        logger.info(f"PIN-login dipendente OK · IP {ip} · {result['user_id']} · {result['role']}")
        return result

    # --- Ramo admin via fonte operatori condivisa (PIN unico cassa) ---
    if pin.isdigit() and 4 <= len(pin) <= 12:
        db_op = Database.get_db()
        op = await operatore_amministratore(db_op, pin)
        if op:
            _clear_failures(ip)
            expire = datetime.now(timezone.utc) + timedelta(minutes=PIN_TOKEN_EXPIRE_MINUTES)
            token = jwt.encode(
                {"sub": op.get("id", "admin"), "name": op.get("nome", "Amministratore"),
                 "role": "admin", "tipo": "admin", "exp": expire,
                 "iat": datetime.now(timezone.utc), "auth_method": "pin_operatore"},
                settings.SECRET_KEY, algorithm=settings.ALGORITHM,
            )
            logger.info(f"PIN-login admin (operatore cassa) OK · IP {ip}")
            return {"access_token": token, "token_type": "bearer",
                    "user_id": op.get("id", "admin"), "name": op.get("nome", "Amministratore"),
                    "role": "admin", "tipo": "admin", "auth_method": "pin_operatore"}

    # --- Ramo admin: PIN unico da env ---
    if not settings.PIN_CODE:
        logger.error("PIN-login: PIN_CODE non configurato nelle env")
        raise HTTPException(503, "Login PIN non configurato")

    if not pin.isdigit() or not (4 <= len(pin) <= 12):
        _register_failure(ip)
        raise HTTPException(400, "PIN non valido")

    if not _pin_ok(pin):
        _register_failure(ip)
        logger.warning(f"PIN-login: PIN errato da IP {ip}")
        raise HTTPException(401, "PIN non valido")

    db = Database.get_db()
    user_repo = UserRepository(db[Collections.USERS])

    user = None
    try:
        user = await user_repo.find_by_username(settings.PIN_ADMIN_USERNAME)
    except Exception:
        user = None
    if not user:
        user = await db[Collections.USERS].find_one({"role": "admin"})
    if not user:
        user = await db[Collections.USERS].find_one({"is_active": True})
    if not user:
        logger.error("PIN-login: nessun utente admin nel DB")
        raise HTTPException(500, "Nessun utente admin configurato")

    user_id = str(user.get("id") or user.get("_id"))
    expire = datetime.now(timezone.utc) + timedelta(minutes=PIN_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "sub": user_id,
            "email": user.get("email", ""),
            "name": user.get("name"),
            "role": user.get("role", "admin"),
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "auth_method": "pin",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    try:
        await user_repo.update_last_login(user_id)
    except Exception:
        pass

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


@router.get("/pin-login/health", summary="Health check PIN login")
async def pin_login_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "configured": bool(settings.PIN_CODE),
        "admin_username": settings.PIN_ADMIN_USERNAME,
        "token_expire_minutes": PIN_TOKEN_EXPIRE_MINUTES,
    }
