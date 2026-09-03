"""
Identità & permessi per il portale dipendenti.

A differenza di utils/dependencies.get_current_user (che ha un bypass admin
quando manca il token), qui il token è SEMPRE obbligatorio: nessun accesso
anonimo. Usato da tutti gli endpoint del portale (buste paga, richieste, turni).

Ruoli applicativi (campo `ruolo_app` sul documento dipendente, o role nel JWT):
  - "dipendente"          → accede solo ai propri dati
  - "responsabile_turni"  → Luigi: gestisce turni e richieste turno
  - "admin"               → Enzo: tutto
"""
from typing import Dict, Any, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.hr.config import settings

_bearer = HTTPBearer(auto_error=True)

RUOLI_VALIDI = {"dipendente", "responsabile_turni", "admin"}


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido o scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_identity(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Dict[str, Any]:
    """Identità corrente dal JWT. 401 se assente/invalido (nessun bypass)."""
    payload = decode_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token senza soggetto")
    return {
        "id": sub,
        "role": payload.get("role", "dipendente"),
        "tipo": payload.get("tipo", "dipendente"),
        "name": payload.get("name"),
        "auth_method": payload.get("auth_method"),
    }


def require_roles(*roles: str):
    """Dependency factory: consente solo ai ruoli indicati."""
    allowed = set(roles)

    async def _checker(identity: Dict[str, Any] = Depends(get_identity)) -> Dict[str, Any]:
        if identity.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permessi insufficienti",
            )
        return identity

    return _checker
