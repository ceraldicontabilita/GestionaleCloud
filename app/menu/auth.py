"""Chi puo' fare cosa nel modulo Menu.

Sessione unica del gestionale (stesso ``SECRET_KEY``): nessun username/
password separato come nella vecchia app Menu.

- ``require_menu_staff``: qualunque sessione valida, comprese quelle del
  portale dipendenti (``dipendente``, ``responsabile_turni``): cassa,
  cucina, ordini e magazzino bar sono lavoro di banco.
- ``require_menu_gestione``: ``admin`` e ``operatore`` (prodotti, sale,
  immagini, QR code).
- ``require_menu_admin``: solo ``admin`` (ripristino backup, migrazione).
"""
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, status

from app.config import settings

RUOLI_STAFF = {"admin", "operatore", "sola_lettura", "dipendente", "responsabile_turni"}
RUOLI_GESTIONE = {"admin", "operatore"}
RUOLI_ADMIN = {"admin"}


def _token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return request.cookies.get("access_token") or None


def sessione(request: Request) -> Dict[str, Any]:
    token = _token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticazione richiesta", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta o token non valido", headers={"WWW-Authenticate": "Bearer"})
    if not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token senza soggetto")
    return payload


def _richiedi(ruoli: set, messaggio: str):
    async def _dep(request: Request) -> Dict[str, Any]:
        payload = sessione(request)
        if payload.get("role") not in ruoli:
            raise HTTPException(status.HTTP_403_FORBIDDEN, messaggio)
        return payload
    return _dep


require_menu_staff = _richiedi(RUOLI_STAFF, "Accesso riservato allo staff")
require_menu_gestione = _richiedi(RUOLI_GESTIONE, "Operazione riservata alla gestione del menu")
require_menu_admin = _richiedi(RUOLI_ADMIN, "Operazione riservata all'amministratore")


def nome_utente(payload: Dict[str, Any]) -> str:
    return str(payload.get("name") or payload.get("email") or payload.get("sub") or "staff")
