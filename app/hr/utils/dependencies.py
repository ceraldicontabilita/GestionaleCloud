"""Dependency FastAPI del modulo HR: autenticazione e parametri comuni.

Il token e' quello unico del gestionale (stesso ``SECRET_KEY``): puo'
arrivare nello header ``Authorization: Bearer`` (chiamate del frontend e del
portale) o nel cookie di sessione ``access_token`` (link aperti direttamente
nel browser, es. il PDF di una busta paga). Fail-closed: senza token valido
e' sempre 401, nessun utente implicito.

Ruoli ammessi nell'area gestione HR:
- ``admin``              -> tutto (``require_admin``);
- ``operatore``          -> area gestione, come per il resto del gestionale;
- ``sola_lettura``       -> area gestione in sola lettura (le scritture sono
                            gia' bloccate dal middleware globale);
- ``responsabile_turni`` -> solo le rotte "staff" (la pagina Turni);
- ``dipendente``         -> solo il portale (``utils/identity.py``).
"""
from datetime import datetime
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.hr.config import settings, FEATURES
from app.hr.database import get_database

RUOLI_ADMIN = {"admin"}
RUOLI_STAFF = {"admin", "operatore", "sola_lettura", "responsabile_turni"}


def _token_from_request(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return request.cookies.get("access_token") or None


def _decode(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessione scaduta o token non valido. Effettua di nuovo l'accesso.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _payload_or_401(request: Request) -> Dict[str, Any]:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticazione richiesta",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode(token)
    if not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token senza soggetto")
    return payload


async def get_current_user(request: Request) -> Dict[str, Any]:
    payload = _payload_or_401(request)
    return {
        "user_id": payload["sub"],
        "email": payload.get("email"),
        "name": payload.get("name"),
        "role": payload.get("role", "non_autorizzato"),
    }


async def get_current_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user.get("role") not in RUOLI_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accesso riservato all'amministratore")
    return current_user


async def require_admin(request: Request) -> Dict[str, Any]:
    payload = _payload_or_401(request)
    if payload.get("role") not in RUOLI_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accesso riservato all'amministratore")
    return payload


async def require_staff(request: Request) -> Dict[str, Any]:
    """Rotte dell'area gestione raggiungibili anche dal responsabile turni."""
    payload = _payload_or_401(request)
    if payload.get("role") not in RUOLI_STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accesso riservato")
    return payload


def require_feature(feature_name: str):
    def check_feature():
        if not FEATURES.get(feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Feature '{feature_name}' is not enabled",
            )
    return check_feature


async def get_user_db(current_user: Dict[str, Any] = Depends(get_current_user), db=Depends(get_database)):
    return db, current_user["user_id"]


def pagination_params(skip: int = 0, limit: int = 100, sort_by: Optional[str] = None, sort_order: str = "asc") -> Dict[str, Any]:
    limit = max(1, min(limit, 1000))
    skip = max(0, skip)
    sort = None
    if sort_by:
        sort = [(sort_by, 1 if sort_order.lower() == "asc" else -1)]
    return {"skip": skip, "limit": limit, "sort": sort}


def date_range_params(date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Optional[datetime]]:
    result: Dict[str, Optional[datetime]] = {"date_from": None, "date_to": None}
    for key, value in (("date_from", date_from), ("date_to", date_to)):
        if value:
            try:
                result[key] = datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Formato {key} non valido (atteso YYYY-MM-DD): {value}")
    if result["date_from"] and result["date_to"] and result["date_from"] > result["date_to"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from deve precedere date_to")
    return result
