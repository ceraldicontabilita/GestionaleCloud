"""Cedolini acquisiti ma mai trasformati in record contabili.

Il controllo guarda soltanto il database (``documents_inbox`` e
``cedolini_email_attachments``): non legge Drive. Lo usa il job
``cedolini_bloccati`` dello scheduler.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

ORE_SOGLIA_BLOCCATO = 6


async def verifica_documenti_bloccati(db) -> Dict[str, Any]:
    """Verifica i cedolini acquisiti ma non trasformati in record contabili."""
    now = datetime.now(timezone.utc)
    soglia = (now - timedelta(hours=ORE_SOGLIA_BLOCCATO)).isoformat()

    bloccati_drive = await db["documents_inbox"].find(
        {"category": "busta_paga", "processed": {"$ne": True}, "created_at": {"$lt": soglia}},
        {"_id": 0, "id": 1, "filename": 1, "created_at": 1},
    ).to_list(500)

    bloccati_email = await db["cedolini_email_attachments"].find(
        {"processed": {"$ne": True}, "created_at": {"$lt": soglia}},
        {"_id": 0, "id": 1, "filename": 1, "created_at": 1},
    ).to_list(500)

    for d in bloccati_drive:
        d["canale"] = "drive"
    for d in bloccati_email:
        d["canale"] = "email"

    return {
        "soglia_ore": ORE_SOGLIA_BLOCCATO,
        "totale_bloccati": len(bloccati_drive) + len(bloccati_email),
        "bloccati": bloccati_drive + bloccati_email,
    }
