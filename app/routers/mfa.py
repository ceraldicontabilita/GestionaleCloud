"""Endpoint MFA: iscrizione, verifica login, step-up e disattivazione."""
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.database import Database
from app.services import mfa_service
from app.utils import login_lockout
from app.utils.auth_tokens import (
    create_access_token,
    decode_mfa_challenge,
    set_session_cookies,
)
from app.utils.dependencies import get_current_admin_user


router = APIRouter()


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaLoginRequest(MfaCodeRequest):
    challenge_token: str = Field(min_length=20)


def _identity(user: Dict[str, Any]) -> str:
    return mfa_service.canonical_identity(
        str(user.get("user_id") or user.get("id") or user.get("sub") or ""),
        str(user.get("email") or ""),
        str(user.get("role") or ""),
    )


async def _audit(azione: str, request: Request, extra: Dict[str, Any] | None = None) -> None:
    try:
        from app.services.audit_logger import log_sicurezza

        await log_sicurezza(
            Database.get_db(),
            azione=azione,
            dettaglio="Verifica in due passaggi",
            utente="amministratore",
            ip=login_lockout.client_ip(request),
            extra=extra or {},
        )
    except Exception:
        pass


@router.get("/mfa/status")
async def mfa_status(admin: Dict[str, Any] = Depends(get_current_admin_user)):
    data = await mfa_service.get_status(Database.get_db(), _identity(admin))
    data["verified_in_session"] = bool(admin.get("mfa_verified"))
    return data


@router.post("/mfa/setup/start")
async def mfa_setup_start(
    regenerate: bool = False,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    try:
        return await mfa_service.start_enrollment(
            Database.get_db(), _identity(admin), regenerate=regenerate
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/mfa/setup/confirm")
async def mfa_setup_confirm(
    body: MfaCodeRequest,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    ip = login_lockout.client_ip(request)
    if login_lockout.seconds_locked(ip) > 0:
        raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova piu tardi.")
    try:
        recovery_codes = await mfa_service.confirm_enrollment(
            Database.get_db(), _identity(admin), body.code
        )
    except ValueError as exc:
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    login_lockout.clear_failures(ip)
    await _audit("mfa_attivata", request)
    return {
        "ok": True,
        "recovery_codes": recovery_codes,
        "warning": "Salva questi codici adesso: non verranno mostrati di nuovo.",
    }


@router.post("/mfa/verify-login")
async def mfa_verify_login(body: MfaLoginRequest, request: Request, response: Response):
    ip = login_lockout.client_ip(request)
    lock = login_lockout.seconds_locked(ip)
    if lock > 0:
        raise HTTPException(status_code=429, detail=f"Troppi tentativi. Riprova tra {lock} secondi.")
    try:
        challenge = decode_mfa_challenge(body.challenge_token)
    except ValueError as exc:
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    identity = mfa_service.canonical_identity(
        challenge.get("sub", ""), challenge.get("email", ""), challenge.get("role", "")
    )
    if not await mfa_service.verify_code(Database.get_db(), identity, body.code):
        login_lockout.register_failure(ip)
        await _audit("mfa_login_fallita", request)
        raise HTTPException(status_code=401, detail="Codice MFA non valido o gia usato")
    login_lockout.clear_failures(ip)
    token = create_access_token(
        user_id=challenge["sub"],
        email=challenge.get("email", ""),
        name=challenge.get("name"),
        role=challenge.get("role", "admin"),
        auth_method=challenge.get("auth_method", "password"),
        mfa_verified=True,
    )
    set_session_cookies(response, token)
    await _audit("login_ok", request, {"mfa": True})
    return {
        "ok": True,
        "access_token": token,
        "user_id": challenge["sub"],
        "email": challenge.get("email", ""),
        "name": challenge.get("name"),
        "role": challenge.get("role", "admin"),
        "auth_method": challenge.get("auth_method", "password"),
        "mfa_verified": True,
    }


@router.post("/mfa/step-up")
async def mfa_step_up(
    body: MfaCodeRequest,
    request: Request,
    response: Response,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    ip = login_lockout.client_ip(request)
    if not await mfa_service.verify_code(Database.get_db(), _identity(admin), body.code):
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=401, detail="Codice MFA non valido o gia usato")
    login_lockout.clear_failures(ip)
    token = create_access_token(
        user_id=admin["user_id"],
        email=admin.get("email", ""),
        name=admin.get("name"),
        role=admin.get("role", "admin"),
        auth_method=admin.get("auth_method", "password"),
        mfa_verified=True,
        mfa_verified_at=datetime.now(timezone.utc),
    )
    set_session_cookies(response, token)
    await _audit("mfa_step_up_ok", request)
    return {"ok": True, "access_token": token, "mfa_verified": True}


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaCodeRequest,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    identity = _identity(admin)
    if not await mfa_service.verify_code(Database.get_db(), identity, body.code):
        raise HTTPException(status_code=401, detail="Codice MFA non valido o gia usato")
    await mfa_service.disable(Database.get_db(), identity)
    await _audit("mfa_disattivata", request)
    return {"ok": True}
