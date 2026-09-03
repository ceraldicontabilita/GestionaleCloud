"""Notifiche in-app per i dipendenti (collection `notifiche`)."""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

COLL = "notifiche"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def crea_notifica(db, dipendente_id: str, tipo: str, titolo: str,
                        messaggio: str, extra: Optional[Dict[str, Any]] = None) -> str:
    nid = f"ntf_{uuid.uuid4().hex[:12]}"
    await db[COLL].insert_one({
        "id": nid,
        "dipendente_id": dipendente_id,
        "tipo": tipo,
        "titolo": titolo,
        "messaggio": messaggio,
        "extra": extra or {},
        "letta": False,
        "creato_il": _now(),
        "letta_il": None,
    })
    return nid
