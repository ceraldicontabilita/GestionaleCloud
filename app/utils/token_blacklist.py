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
