"""Login del portale dipendenti: tocca il tuo nome + PIN personale.

Flow (portale mobile, dispositivo condiviso in negozio):
  GET  /api/hr/auth/dipendenti-attivi          -> [{id, nome}] pubblico
  POST /api/hr/auth/pin-login {dipendente_id, pin} -> JWT (7 giorni)

L'accesso amministratore NON passa piu' da qui: il PIN unico del titolare e'
quello del login del gestionale (``/login``, POST /api/auth/pin-login, con
MFA). Il portale mostra il bottone "Accesso amministratore" che porta la'.

Il PIN di ogni dipendente e' salvato solo come hash sul suo documento
(``services/auth_dipendenti.py``); si genera e si azzera dall'area gestione
(``routers/employees/accessi.py``), mai in chiaro nel database o nel codice.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request, status

from app.hr.database import Database
from app.hr.services.auth_dipendenti import elenco_dipendenti_per_login, login_dipendente
from app.utils import login_lockout

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dipendenti-attivi", summary="Nomi per il selettore di login del portale")
async def dipendenti_attivi() -> Dict[str, Any]:
    """Elenco pubblico di id+nome dei dipendenti attivi con un PIN impostato.
    Solo id e nome: nessun altro dato prima dell'autenticazione."""
    return {"dipendenti": await elenco_dipendenti_per_login()}


@router.post("/pin-login", summary="Login dipendente via PIN personale")
async def pin_login(
    request: Request,
    payload: Dict[str, Any] = Body(..., examples=[{"dipendente_id": "<id>", "pin": "******"}]),
) -> Dict[str, Any]:
    ip = login_lockout.client_ip(request)
    lock_sec = login_lockout.seconds_locked(ip)
    if lock_sec > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Troppi tentativi, riprova tra {lock_sec}s")

    pin = str(payload.get("pin", "")).strip()
    dipendente_id = str(payload.get("dipendente_id") or "").strip()
    if not dipendente_id:
        # Il PIN amministratore vive nel login del gestionale: qui non si
        # prova nemmeno a verificarlo, cosi' non esistono due porte.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Seleziona il tuo nome. L'amministratore accede dal login del gestionale.",
        )

    result = await login_dipendente(dipendente_id, pin)
    if not result:
        login_lockout.register_failure(ip)
        logger.warning("PIN-login dipendente fallito da IP %s", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide")
    login_lockout.clear_failures(ip)

    try:
        from app.hr.services.audit_logger import log_evento
        await log_evento(
            modulo="accesso", azione="login",
            entita_id=result["user_id"], entita_collection="dipendenti",
            db=Database.get_db(), fonte="portale", utente=result["user_id"],
            dettaglio="Accesso al portale via PIN", extra={"ip": ip},
        )
    except Exception:  # l'audit non deve mai bloccare il login
        logger.debug("Audit login portale non registrato", exc_info=True)
    logger.info("PIN-login dipendente OK · IP %s · %s · %s", ip, result["user_id"], result["role"])
    return result


@router.get("/pin-login/health", summary="Health check login portale")
async def pin_login_health() -> Dict[str, Any]:
    from app.hr.config import settings
    return {"ok": True, "token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES}
