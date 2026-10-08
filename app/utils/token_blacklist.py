"""
Revoca token JWT lato server (audit sicurezza 19/07/2026).

Prima del logout non esisteva alcuna invalidazione server-side: un token
rubato restava valido fino a scadenza naturale anche dopo logout. Questa
blacklist copre il caso più importante e a rischio più basso da introdurre
stanotte senza supervisione: il logout esplicito. Non copre (ancora) la
disattivazione utente o il cambio ruolo — richiede toccare utenti_pin.py,
lasciato per una revisione dedicata.

Fail-closed: se il registro non è interrogabile non è possibile distinguere
un token valido da uno revocato. La richiesta viene quindi sospesa con errore
temporaneo, senza concedere accesso.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION = "token_blacklist"


class TokenBlacklistUnavailable(RuntimeError):
    """Il registro di revoca non può essere letto o scritto in sicurezza."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def chiave_sessione(payload: dict, token: str) -> str:
    """Chiave con cui si revoca una sessione del Gestionale.

    Il token dell'ERP si rinnova ogni mezz'ora (sessione scorrevole): la sua
    impronta cambia, la sessione no. Dal login porta quindi un ``sid`` stabile,
    e la sessione si revoca per quello. I token emessi prima del ``sid`` si
    revocano ancora per impronta."""
    sid = str((payload or {}).get("sid") or "")
    return f"sid:{sid}" if sid else _hash(token)


async def revoca_chiave(db, chiave: str, exp: Optional[float] = None) -> None:
    """Scrive una chiave di revoca (impronta di token o ``sid:<id>``)."""
    if not chiave:
        return
    try:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await db[COLLECTION].update_one(
            {"token_hash": chiave},
            {"$setOnInsert": {
                "token_hash": chiave,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "exp": exp_dt,
            }},
            upsert=True,
        )
    except Exception as e:
        logger.error("Revoca sessione non riuscita (%s)", type(e).__name__)
        raise TokenBlacklistUnavailable("Registro revoche non disponibile") from e


async def revoca_token(db, token: str, exp: Optional[float] = None) -> None:
    """Invalida un token (da chiamare al logout, prima di cancellare i cookie).

    `exp` (claim JWT, epoch seconds) viene salvato come datetime BSON perché
    l'indice TTL su questo campo (Database._create_indexes) lo richiede per
    la pulizia automatica (review Codex su PR #65: gli scarti non venivano
    mai rimossi)."""
    if not token:
        return
    try:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await db[COLLECTION].update_one(
            {"token_hash": _hash(token)},
            {"$setOnInsert": {
                "token_hash": _hash(token),
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "exp": exp_dt,
            }},
            upsert=True,
        )
    except Exception as e:
        logger.error("Revoca token non riuscita")
        raise TokenBlacklistUnavailable("Registro revoche non disponibile") from e


async def is_revocato(db, token: str) -> bool:
    """True se il token è stato invalidato (es. logout) prima della scadenza naturale."""
    if not token:
        return False
    try:
        doc = await db[COLLECTION].find_one({"token_hash": _hash(token)}, {"_id": 0})
        return doc is not None
    except Exception as e:
        logger.error("Verifica blacklist token non riuscita")
        raise TokenBlacklistUnavailable("Registro revoche non disponibile") from e


async def is_hash_revocato(db, token_hash: str) -> bool:
    """Come `is_revocato`, ma per chi conosce solo l'impronta del token.

    Le app del gruppo (HR, Lotti, Menu) non vedono mai il token dell'ERP: i
    loro token portano soltanto la sua impronta (`sid`), che e' la stessa
    chiave con cui il logout scrive qui."""
    if not token_hash:
        return False
    try:
        doc = await db[COLLECTION].find_one({"token_hash": token_hash}, {"_id": 0})
        return doc is not None
    except Exception as e:
        logger.error("Verifica blacklist token non riuscita")
        raise TokenBlacklistUnavailable("Registro revoche non disponibile") from e
