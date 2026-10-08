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
mai quello del Gestionale, e mai nell'URL. Quel token porta pero' il ``sid``,
la chiave di revoca della sessione del Gestionale da cui nasce
(``token_blacklist.chiave_sessione``: stabile attraverso i rinnovi): cosi' il
logout del Gestionale chiude anche HR, Lotti e Menu, e ogni backend lo
verifica a ogni richiesta con ``sessione_derivata_valida``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

NOME_COOKIE = "access_token"

# Un token nato dalla sessione del Gestionale si riconosce da qui.
VIA_SESSIONE_ERP = "sessione_erp"

# Esito della verifica di revoca tenuto in memoria per ``sid``: una sessione
# viva si riverifica al piu' ogni 15 secondi (stessa cadenza della cache del
# runtime), una revocata resta revocata per sempre.
_TTL_SESSIONE_VIVA = 15.0
_MAX_SID_IN_MEMORIA = 2048
_sid_vivi: Dict[str, float] = {}
_sid_revocati: set = set()


def segna_revocata(sid: str) -> None:
    """Il logout di questo processo vale subito, senza aspettare la cache."""
    if sid:
        _sid_vivi.pop(sid, None)
        if len(_sid_revocati) >= _MAX_SID_IN_MEMORIA:
            _sid_revocati.clear()  # il registro su Supabase resta la fonte
        _sid_revocati.add(sid)


def _azzera_cache() -> None:
    """Per i test."""
    _sid_vivi.clear()
    _sid_revocati.clear()


async def sessione_revocata(chiave: str) -> bool:
    """Vero se la sessione con questa chiave e' stata chiusa dal logout.

    Esito in memoria (15 s per le vive, per sempre per le revocate). Solleva
    ``TokenBlacklistUnavailable`` se il registro non risponde: decide il
    chiamante, e nessuno lo tratta come «non revocata»."""
    if chiave in _sid_revocati:
        return True
    adesso = time.monotonic()
    if adesso - _sid_vivi.get(chiave, -_TTL_SESSIONE_VIVA) < _TTL_SESSIONE_VIVA:
        return False
    from app.database import Database
    from app.utils.token_blacklist import is_hash_revocato

    if await is_hash_revocato(Database.get_db(), chiave):
        segna_revocata(chiave)
        return True
    if len(_sid_vivi) >= _MAX_SID_IN_MEMORIA:
        _sid_vivi.clear()
    _sid_vivi[chiave] = adesso
    return False


async def sessione_derivata_valida(payload: Optional[Dict[str, Any]]) -> bool:
    """Vero se il token di un'app del gruppo puo' ancora essere usato.

    Solo i token nati dalla sessione del Gestionale dipendono da lei; quelli
    del PIN personale (dipendente, operatore) hanno la loro scadenza. Un token
    ``sessione_erp`` senza ``sid`` e' di prima di questo controllo: non si puo'
    revocare, quindi non vale (le app ne chiedono uno nuovo dal cookie).
    Se il registro revoche non risponde si chiude, non si apre."""
    if not payload:
        return False
    via = payload.get("via") or payload.get("auth_method")
    if via != VIA_SESSIONE_ERP:
        return True
    sid = str(payload.get("sid") or "")
    if not sid:
        return False
    from app.utils.token_blacklist import TokenBlacklistUnavailable

    try:
        return not await sessione_revocata(sid)
    except TokenBlacklistUnavailable:
        logger.warning("[sessione unica] registro revoche non disponibile: token derivato rifiutato")
        return False


RUOLI_AMMINISTRATORE = frozenset({"admin", "amministratore"})


async def token_di_gruppo_ammesso(payload: Optional[Dict[str, Any]]) -> bool:
    """Regola unica per HR e Lotti su un token gia' firmato e non scaduto.

    - nato dalla sessione del Gestionale: vale finche' il logout non la revoca;
    - con ruolo amministratore: vale SOLO se nato dalla sessione del
      Gestionale. Un token admin del vecchio PIN amministratore, del login
      email/password HR o del login Google di Lotti non apre piu' nulla, anche
      se non e' ancora scaduto;
    - PIN personale di dipendente o operatore: vale fino alla sua scadenza."""
    if not payload:
        return False
    ruolo = str(payload.get("role") or payload.get("ruolo") or "").strip().lower()
    via = payload.get("via") or payload.get("auth_method")
    if ruolo in RUOLI_AMMINISTRATORE and via != VIA_SESSIONE_ERP:
        return False
    return await sessione_derivata_valida(payload)


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
    from app.utils.token_blacklist import TokenBlacklistUnavailable, chiave_sessione, is_revocato

    for token in valori_cookie(request.headers.get("cookie", "")):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            continue  # il cookie di HR, firmato con un altro segreto
        if not payload.get("sub") or payload.get("purpose"):
            continue  # una challenge MFA non e' una sessione
        if normalizza_ruolo(payload.get("role")) != ADMIN:
            return None
        chiave = chiave_sessione(payload, token)
        try:
            if await is_revocato(Database.get_db(), token) or await sessione_revocata(chiave):
                return None
        except TokenBlacklistUnavailable:
            logger.warning("[sessione unica] registro revoche non disponibile: accesso negato")
            return None
        return {
            "user_id": str(payload["sub"]),
            "email": payload.get("email") or "",
            "name": payload.get("name") or "Amministratore",
            "role": ADMIN,
            "sid": chiave,
        }
    return None
