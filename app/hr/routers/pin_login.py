"""
PIN Login router — accesso rapido via PIN dall'app mobile Ceraldi.

Il PIN amministratore è quello di ERP/Menu. Il verificatore condiviso usa
esclusivamente PIN_HASH_ADMIN dalle env Render, mai un PIN alternativo HR.
L'identità e il ruolo amministrativo devono già esistere nell'archivio HR.

Flow:
  POST /api/auth/pin-login   body: {"pin": "<pin>"}
  -> {"access_token": "...", "token_type": "bearer", ...}
"""
from fastapi import APIRouter, HTTPException, Body, Request, status
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import logging
import os

from jose import jwt

from app.hr.config import settings
from app.hr.database import Database, Collections
from app.hr.repositories import UserRepository as HrUserRepository
from app.hr.services.auth_dipendenti import (
    login_dipendente, login_dipendente_per_nome,
    elenco_dipendenti_per_login,
)
from app.services import pin_authentication
from app.utils import login_lockout

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

# Anti brute force condiviso con ERP/email login.
_client_ip = login_lockout.client_ip
_is_locked = login_lockout.seconds_locked
_register_failure = login_lockout.register_failure
_clear_failures = login_lockout.clear_failures


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

    # --- Ramo admin: credenziale e identita risolte dal motore canonico. ---
    if not pin_authentication.admin_pin_is_configured():
        logger.error("PIN-login: PIN amministratore centrale non configurato")
        raise HTTPException(503, "Login PIN non configurato")

    if not pin.isdigit() or not (4 <= len(pin) <= 12):
        _register_failure(ip)
        raise HTTPException(400, "PIN non valido")

    db = Database.get_db()
    identity = await pin_authentication.authenticate_admin_pin(
        db,
        pin,
        users_collection=Collections.USERS,
        username=settings.PIN_ADMIN_USERNAME,
        repository_factory=HrUserRepository,
        require_existing=True,
        require_active=True,
        allow_synthetic=False,
    )
    if identity is None:
        _register_failure(ip)
        logger.warning(f"PIN-login admin HR fallito da IP {ip}")
        raise HTTPException(401, "PIN non valido o amministratore non configurato")

    user = identity.as_user()
    user_repo = identity.user_repo

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
        "configured": pin_authentication.admin_pin_is_configured(),
        "admin_username": settings.PIN_ADMIN_USERNAME,
        "token_expire_minutes": PIN_TOKEN_EXPIRE_MINUTES,
    }
