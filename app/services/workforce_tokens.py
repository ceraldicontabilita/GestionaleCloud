"""Emissione canonica dei token operativi HR/Lotti.

ERP contabile escluso intenzionalmente: questo servizio copre soltanto il
perimetro operativo condiviso tra portale dipendenti e magazzino/HACCP.
Il payload espone entrambi i vocabolari senza promuovere ruoli.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

ALGORITHM = "HS256"

_VERSO_HR = {"operatore": "dipendente"}
_VERSO_LOTTI = {"dipendente": "operatore"}


def create_workforce_token(
    *,
    sub: str,
    name: str,
    role: str,
    secret: str,
    expires_in: timedelta,
    auth_method: str,
    algorithm: str = ALGORITHM,
    email: str = "",
) -> str:
    """Crea un JWT leggibile in modo coerente sia da HR sia da Lotti."""
    if not secret:
        raise ValueError("Segreto sessione operativa mancante")

    now = datetime.now(timezone.utc)
    normalized_role = str(role or "").strip().lower()
    hr_role = normalized_role if normalized_role == "admin" else _VERSO_HR.get(normalized_role, normalized_role)
    lotti_role = normalized_role if normalized_role == "admin" else _VERSO_LOTTI.get(normalized_role, normalized_role)
    payload = {
        "sub": str(sub),
        "name": name or "",
        "nome": name or "",
        "role": hr_role,
        "ruolo": lotti_role,
        "tipo": "dipendente" if hr_role != "admin" else "admin",
        "auth_method": auth_method,
        "via": auth_method,
        "iat": now,
        "exp": now + expires_in,
    }
    if email:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm=algorithm)
