"""Bootstrap asincrono e condiviso della chiave JWT.

Evita accessi sincroni a Mongo durante l'import di ``config``. Su piu'
repliche, il documento con ``_id=auth_secret`` rende l'inizializzazione
atomica e tutte le istanze convergono sulla stessa chiave.
"""
from datetime import datetime, timezone
import logging
import secrets

from app.config import Settings, settings


logger = logging.getLogger(__name__)


async def initialize_auth_secret(db, cfg: Settings = settings) -> str:
    """Assicura una chiave JWT stabile prima di servire traffico."""
    if cfg.auth_secret_source == "configured":
        return "configured"

    collection = db["sistema_stato"]
    existing = await collection.find_one(
        {"$or": [{"_id": "auth_secret"}, {"chiave": "auth_secret"}]},
        {"valore": 1},
    )
    if not existing or not existing.get("valore"):
        now = datetime.now(timezone.utc).isoformat()
        await collection.update_one(
            {"_id": "auth_secret"},
            {"$setOnInsert": {
                "_id": "auth_secret",
                "chiave": "auth_secret",
                "valore": secrets.token_urlsafe(64),
                "created_at": now,
                "created_by": "auth_secret_bootstrap",
            }},
            upsert=True,
        )
        existing = await collection.find_one(
            {"_id": "auth_secret"}, {"valore": 1},
        )

    value = (existing or {}).get("valore")
    if not value:
        raise RuntimeError("Impossibile inizializzare la chiave JWT condivisa")

    cfg.set_runtime_auth_secret(value, source="mongodb")
    logger.info("Chiave JWT inizializzata da sorgente condivisa MongoDB")
    return "mongodb"
