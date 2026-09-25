"""Sessione unica del gruppo: il login del Gestionale apre HR, Lotti e Menu.

Il Gestionale, al login (PIN piu' MFA), mette un cookie ``access_token``
HttpOnly, Secure, SameSite=Lax con ``path=/``. Tutte le app stanno sullo
stesso dominio, quindi il cookie arriva gia' anche a ``/hr``, ``/lotti`` e
``/menu``. Qui lo si legge e lo si verifica con le stesse regole del
middleware dell'ERP (firma, scadenza, revoca al logout, ruolo), cosi'
l'amministratore entra nelle altre app senza un secondo PIN.

Due accortezze:
  - sotto ``/hr`` il browser manda **due** cookie ``access_token`` (quello
    dell'ERP con path ``/`` e quello di HR con path ``/hr``, firmato con un
    altro segreto): si provano tutti, e vale solo quello che l'ERP ha firmato;
  - la revoca si controlla sempre; se il registro delle revoche non risponde
    la sessione non vale (si chiude, non si apre).

Il token ERP non esce mai da qui: le app ricevono un loro token di sessione,
mai quello del Gestionale, e mai nell'URL.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

NOME_COOKIE = "access_token"


def valori_cookie(intestazione: str, nome: str = NOME_COOKIE) -> List[str]:
    """Tutti i valori di un cookie, anche ripetuto (path diversi)."""
    valori = []
    for parte in (intestazione or "").split(";"):
        chiave, _, valore = parte.strip().partition("=")
        if chiave == nome and valore:
            valori.append(valore.strip().strip('"'))
    return valori


async def sessione_erp(request) -> Optional[Dict[str, Any]]:
    """Identita' dell'amministratore del Gestionale, o None.

    Solo il ruolo amministratore apre le altre app: un operatore o un account
    in sola lettura dell'ERP non diventa amministratore di HR, Lotti o Menu.
    """
    from app.config import settings
    from app.database import Database
    from app.utils.ruoli import ADMIN, normalizza_ruolo
    from app.utils.token_blacklist import TokenBlacklistUnavailable, is_revocato

    for token in valori_cookie(request.headers.get("cookie", "")):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            continue  # il cookie di HR, firmato con un altro segreto
        if not payload.get("sub") or payload.get("purpose"):
            continue  # una challenge MFA non e' una sessione
        if normalizza_ruolo(payload.get("role")) != ADMIN:
            return None
        try:
            if await is_revocato(Database.get_db(), token):
                return None
        except TokenBlacklistUnavailable:
            logger.warning("[sessione unica] registro revoche non disponibile: accesso negato")
            return None
        return {
            "user_id": str(payload["sub"]),
            "email": payload.get("email") or "",
            "name": payload.get("name") or "Amministratore",
            "role": ADMIN,
        }
    return None
