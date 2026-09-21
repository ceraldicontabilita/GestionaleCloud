"""Identita' e permessi per il portale personale HR.

Il token e' sempre obbligatorio. Il portale usa il verificatore operativo
canonico con il solo segreto HR: il sub del token tablet Lotti e' ancora l'ID
della proiezione operatore, non l'ID dipendente che possiede il fascicolo.
Questa separazione resta necessaria finche' la corrispondenza non e' risolta
su identita' canonica stabile.

Ruoli applicativi (campo `ruolo_app` sul documento dipendente, o role nel JWT):
  - "dipendente"          → accede solo ai propri dati
  - "responsabile_turni"  → Luigi: gestisce turni e richieste turno
  - "admin"               → Enzo: tutto
"""
from typing import Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.hr.config import settings
from app.services.workforce_tokens import verifica_token_firmato

_bearer = HTTPBearer(auto_error=True)

RUOLI_VALIDI = {"dipendente", "responsabile_turni", "admin"}


def decode_token(token: str) -> Dict[str, Any]:
    payload = verifica_token_firmato(token, settings.SECRET_KEY)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido o scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_identity(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Dict[str, Any]:
    """Identità corrente dal JWT. 401 se assente/invalido (nessun bypass)."""
    payload = decode_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token senza soggetto")
    role = str(payload.get("role") or "").strip().lower()
    if role not in RUOLI_VALIDI:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token senza ruolo HR valido")
    return {
        "id": sub,
        "role": role,
        "tipo": payload.get("tipo") or ("admin" if role == "admin" else "dipendente"),
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
