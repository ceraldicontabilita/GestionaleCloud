"""Creazione centralizzata dei token di accesso e delle challenge MFA.

Le challenge MFA non sono token di sessione: hanno uno scopo esplicito,
durano pochi minuti e non contengono segreti TOTP.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Response
from jose import JWTError, jwt

from app.config import settings
from app.utils.session_cookie import SESSION_COOKIE_SECURE


MFA_CHALLENGE_MINUTES = 5


def create_access_token(
    *,
    user_id: str,
    email: str = "",
    name: Optional[str] = None,
    role: str = "admin",
    auth_method: str = "password",
    mfa_verified: bool = False,
    mfa_verified_at: Optional[datetime] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email or "",
        "name": name,
        "role": role,
        "tipo": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "auth_method": auth_method,
        "mfa_verified": bool(mfa_verified),
        "amr": [auth_method, "otp"] if mfa_verified else [auth_method],
    }
    if mfa_verified:
        verified_at = mfa_verified_at or now
        payload["mfa_verified_at"] = verified_at
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_mfa_challenge(user: Dict[str, Any], auth_method: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.get("id") or user.get("user_id") or user.get("_id")),
        "email": user.get("email", ""),
        "name": user.get("name") or "Amministratore",
        "role": user.get("role", "admin"),
        "auth_method": auth_method,
        "purpose": "mfa_login",
        "iat": now,
        "exp": now + timedelta(minutes=MFA_CHALLENGE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_mfa_challenge(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError("Challenge MFA non valida o scaduta") from exc
    if payload.get("purpose") != "mfa_login" or not payload.get("sub"):
        raise ValueError("Challenge MFA non valida")
    return payload


def set_session_cookies(response: Response, token: str) -> None:
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key="session_active",
        value="1",
        httponly=False,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
