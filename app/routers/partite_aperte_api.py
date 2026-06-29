"""
Router Partite Aperte — Gestionale Ceraldi Group
==================================================
Endpoint API per la dashboard relazionale.
Legge dalla collezione partite_aperte materializzata.
"""
from fastapi import APIRouter, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/partite-aperte", tags=["Partite Aperte"])

COLL = "partite_aperte"


@router.get("/stats")
async def stats_partite() -> Dict[str, Any]:
    """Totali partite aperte raggruppati per tipo."""
    db = Database.get_db()

    pipeline = [
        {"$match": {"stato": {"$in": ["aperta", "parziale"]}}},
        {"$group": {
            "_id": "$tipo",
            "count": {"$sum": 1},
            "totale_residuo": {"$sum": "$residuo"}
        }},
        {"$sort": {"totale_residuo": -1}}
    ]

    result = {}
    async for doc in db[COLL].aggregate(pipeline):
        result[doc["_id"]] = {
            "count": doc["count"],
            "totale_residuo": round(doc["totale_residuo"], 2)
        }

    return result


@router.get("/lista")
async def lista_partite(
    tipo: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    controparte_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
) -> Dict[str, Any]:
    """Lista partite aperte con filtri."""
    db = Database.get_db()

    query: Dict[str, Any] = {}
    if tipo:
        query["tipo"] = tipo
    if stato:
        query["stato"] = stato
    else:
        query["stato"] = {"$in": ["aperta", "parziale"]}
    if controparte_id:
        query["controparte_id"] = controparte_id

    partite = await db[COLL].find(
        query, {"_id": 0}
    ).sort("data_scadenza", 1).limit(limit).to_list(limit)

    return {"partite": partite, "count": len(partite)}


@router.get("/scadute")
async def partite_scadute(
    giorni_soglia: int = Query(0, description="Giorni oltre scadenza (0 = oggi)")
) -> Dict[str, Any]:
    """Partite aperte con scadenza superata."""
    db = Database.get_db()
    from datetime import timedelta

    data_limite = (datetime.now() - timedelta(days=giorni_soglia)).strftime("%Y-%m-%d")

    partite = await db[COLL].find(
        {
            "stato": {"$in": ["aperta", "parziale"]},
            "data_scadenza": {"$lt": data_limite, "$nin": [None, ""]}
        },
        {"_id": 0}
    ).sort("data_scadenza", 1).to_list(100)

    return {"partite": partite, "count": len(partite)}
