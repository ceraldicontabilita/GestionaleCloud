"""Emissione e verifica canoniche dei token operativi HR/Lotti.

ERP contabile escluso intenzionalmente: questo servizio copre soltanto il
perimetro operativo condiviso tra portale dipendenti e magazzino/HACCP.
Il payload espone entrambi i vocabolari senza promuovere ruoli.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

ALGORITHM = "HS256"

_VERSO_HR = {"operatore": "dipendente"}
_VERSO_LOTTI = {"dipendente": "operatore"}


def normalizza(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Restituisce i campi HR e Lotti senza attribuire ruoli mancanti.

    La traduzione e' direzionale: il ruolo base rimane ``dipendente`` per
    HR e ``operatore`` per Lotti. Un ruolo sconosciuto resta sconosciuto.
    """
    dati = dict(payload)
    dati["sub"] = payload.get("sub", "")
    name = payload.get("nome") or payload.get("name") or ""
    role = str(payload.get("ruolo") or payload.get("role") or "").strip().lower()
    dati["name"] = dati["nome"] = name
    dati["via"] = payload.get("via") or payload.get("auth_method") or "token"
    dati["role"] = _VERSO_HR.get(role, role)
    dati["ruolo"] = _VERSO_LOTTI.get(role, role)
    return dati


def _segreti() -> list[str]:
    """Solo i segreti HR/Lotti; il segreto ERP contabile resta escluso."""
    segreti = []
    try:
        from app.lotti.auth import _secret as segreto_lotti

        valore = segreto_lotti()
        if valore:
            segreti.append(valore)
    except Exception:  # Lotti non montato: resta HR
        pass
    try:
        from app.hr.config import settings as impostazioni_hr

        if impostazioni_hr.SECRET_KEY and impostazioni_hr.SECRET_KEY not in segreti:
            segreti.append(impostazioni_hr.SECRET_KEY)
    except Exception:
        pass
    return segreti


def verifica_token_firmato(token: str, secret: str) -> Optional[Dict[str, Any]]:
    """Verifica un token operativo con il segreto del dominio chiamante."""
    if not token or not isinstance(token, str) or not secret:
        return None
    try:
        return normalizza(jwt.decode(token, secret, algorithms=[ALGORITHM]))
    except jwt.PyJWTError:
        return None


def verifica_token_condiviso(token: str) -> Optional[Dict[str, Any]]:
    """Verifica con i segreti HR/Lotti; il segreto ERP resta escluso."""
    if not token or not isinstance(token, str):
        return None
    for segreto in _segreti():
        payload = verifica_token_firmato(token, segreto)
        if payload is not None:
            return payload
    return None


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
    sid: str = "",
) -> str:
    """Crea un JWT leggibile in modo coerente sia da HR sia da Lotti."""
    if not secret:
        raise ValueError("Segreto sessione operativa mancante")

    now = datetime.now(timezone.utc)
    payload = normalizza({
        "sub": str(sub),
        "name": name or "",
        "role": role,
        "auth_method": auth_method,
    })
    payload.update({
        "tipo": "admin" if payload["role"] == "admin" else "dipendente",
        "iat": now,
        "exp": now + expires_in,
    })
    if email:
        payload["email"] = email
    if sid:
        # Impronta della sessione del Gestionale da cui nasce il token: il
        # logout la revoca per tutte le app (`group_session`).
        payload["sid"] = sid
    return jwt.encode(payload, secret, algorithm=algorithm)
