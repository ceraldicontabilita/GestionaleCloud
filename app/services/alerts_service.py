"""
Servizio alert centralizzato per il gestionale.
Crea, legge e gestisce alert/notifiche per scadenze, anomalie, documenti.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import uuid
import logging

logger = logging.getLogger(__name__)


def create_alert(
    tipo: str,
    messaggio: str,
    data: Optional[str] = None,
    riferimento: Optional[str] = None,
    severita: str = "info",
    categoria: str = "sistema",
) -> Dict[str, Any]:
    """
    Crea un alert strutturato.
    
    Args:
        tipo: Tipo alert (scadenza, anomalia, documento, pagamento, etc.)
        messaggio: Testo dell'alert
        data: Data riferimento (YYYY-MM-DD)
        riferimento: ID documento/fattura/verbale collegato
        severita: info | warning | error | critical
        categoria: sistema | contabilita | hr | fornitori | banca
    """
    return {
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "messaggio": messaggio,
        "data": data or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "riferimento": riferimento,
        "severita": severita,
        "categoria": categoria,
        "letto": False,
        "risolto": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def save_alert(db, alert: Dict[str, Any]) -> str:
    """Salva alert nel database."""
    await db["alerts"].insert_one(alert.copy())
    logger.info(f"[ALERT] {alert['severita'].upper()}: {alert['messaggio'][:80]}")
    return alert["id"]


async def get_alerts(
    db,
    categoria: str = None,
    severita: str = None,
    solo_non_letti: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Legge alert dal database."""
    query = {"risolto": False}
    if categoria:
        query["categoria"] = categoria
    if severita:
        query["severita"] = severita
    if solo_non_letti:
        query["letto"] = False
    
    alerts = await db["alerts"].find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return alerts


async def mark_read(db, alert_id: str) -> bool:
    """Segna alert come letto."""
    result = await db["alerts"].update_one({"id": alert_id}, {"$set": {"letto": True}})
    return result.modified_count > 0


async def resolve_alert(db, alert_id: str) -> bool:
    """Segna alert come risolto."""
    result = await db["alerts"].update_one(
        {"id": alert_id},
        {"$set": {"risolto": True, "risolto_at": datetime.now(timezone.utc).isoformat()}}
    )
    return result.modified_count > 0
