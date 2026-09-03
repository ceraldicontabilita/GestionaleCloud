"""Identita' e permessi per il portale dipendenti.

Il token e' SEMPRE obbligatorio: nessun accesso anonimo. Usato da tutti gli
endpoint del portale (buste paga, richieste, turni, timbrature).

Ruoli applicativi (campo ``ruolo_app`` sul documento dipendente, o ``role``
nel JWT):
  - "dipendente"          -> accede solo ai propri dati
  - "responsabile_turni"  -> gestisce turni e richieste turno
  - "admin"               -> tutto (e' lo stesso admin del gestionale)
"""
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request, status

from app.hr.utils.dependencies import _payload_or_401

RUOLI_VALIDI = {"dipendente", "responsabile_turni", "admin"}


async def get_identity(request: Request) -> Dict[str, Any]:
    """Identita' corrente dal JWT. 401 se assente/invalido (nessun bypass)."""
    payload = _payload_or_401(request)
    return {
        "id": payload["sub"],
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permessi insufficienti")
        return identity

    return _checker
