"""Router Registro Attività — chi è entrato/uscito e chi ha preso/prodotto cosa."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from app.lotti.db import database as db

router = APIRouter(prefix="/log-attivita", tags=["Log Attività"])


@router.get("")
async def lista_attivita(
    tipo: str = Query(None, description="login|logout|magazzino|produzione"),
    operatore: str = Query(None),
    giorni: int = Query(30, le=365),
    limit: int = Query(300, le=1000),
):
    """Registro attività ordinato dal più recente, con filtri per tipo/operatore/giorni."""
    q = {}
    if tipo:
        q["tipo"] = tipo
    if operatore:
        q["operatore"] = {"$regex": operatore, "$options": "i"}
    if giorni:
        da = (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()
        q["timestamp"] = {"$gte": da}
    docs = await db.log_attivita.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    tipi = await db.log_attivita.distinct("tipo")
    operatori = await db.log_attivita.distinct("operatore")
    return {"totale": len(docs), "tipi": sorted([t for t in tipi if t]),
            "operatori": sorted([o for o in operatori if o]), "log": docs}
