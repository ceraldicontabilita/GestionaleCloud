"""
PIN Login router — ingresso al portale dipendenti HR.

- Dipendente: tocca il proprio nome e digita il PIN personale
  (`POST /api/auth/pin-login`).
- Amministratore: nessun PIN qui. Entra dalla sessione del Gestionale
  (`GET /api/auth/session`, cookie ERP); il token HR porta il ``sid`` di quella
  sessione e il logout del Gestionale lo revoca.
"""
from fastapi import APIRouter, HTTPException, Body, Request, status
from datetime import timedelta
from typing import Dict, Any
import logging
import os


from app.hr.config import settings
from app.hr.database import Database, Collections
from app.hr.repositories import UserRepository as HrUserRepository
from app.hr.services.auth_dipendenti import (
    login_dipendente, login_dipendente_per_nome,
    elenco_dipendenti_per_login,
)
from app.services import pin_authentication
from app.services.workforce_tokens import create_workforce_token
from app.utils import login_lockout

logger = logging.getLogger(__name__)
router = APIRouter()

# Durata del token HR dell'amministratore nato dalla sessione del Gestionale
# (default 7 giorni, come il portale: niente reingresso a ogni cambio pagina,
# richiesta del titolare del 04/09/2026). Non e' un limite di sicurezza: il
# logout del Gestionale lo revoca prima (`group_session`).
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

    # Nessun ramo amministratore: l'amministratore entra in HR solo dalla
    # sessione del Gestionale (`GET /session`), mai con un PIN digitato qui.
    raise HTTPException(400, "Serve il dipendente e il suo PIN personale")


@router.get("/session", summary="Sessione del Gestionale → accesso amministratore HR senza PIN")
async def sessione_dal_gestionale(request: Request) -> Dict[str, Any]:
    """L'amministratore gia' entrato nel Gestionale apre HR senza un secondo
    PIN: prova la sessione (cookie ERP, `app/services/group_session.py`) e
    riceve lo stesso token HR del login col PIN. Mai il token dell'ERP."""
    from app.services.group_session import sessione_erp

    sessione = await sessione_erp(request)
    if not sessione:
        raise HTTPException(401, "Nessuna sessione del Gestionale")
    identity = await pin_authentication.risolvi_identita_admin(
        Database.get_db(),
        users_collection=Collections.USERS,
        username=settings.PIN_ADMIN_USERNAME,
        repository_factory=HrUserRepository,
        require_existing=True,
        require_active=True,
        allow_synthetic=False,
    )
    if identity is None:
        raise HTTPException(401, "Amministratore HR non configurato")
    user = identity.as_user()
    user_id = str(user.get("id"))
    token = create_workforce_token(
        sub=user_id,
        name=user.get("name") or "Amministratore",
        role="admin",
        email=user.get("email", ""),
        secret=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_in=timedelta(minutes=PIN_TOKEN_EXPIRE_MINUTES),
        auth_method="sessione_erp",
        sid=sessione["sid"],
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "email": user.get("email", ""),
        "name": user.get("name"),
        "role": "admin",
        "auth_method": "sessione_erp",
    }
