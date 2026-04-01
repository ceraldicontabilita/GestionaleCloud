"""
API Tracciabilità Fatture — segna le fatture come processate per la tracciabilità.
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from app.database import Database

router = APIRouter(prefix="/fatture-tracciabilita", tags=["API Tracciabilita"])


@router.get("/non-processate")
async def get_fatture_non_processate(limit: int = Query(50, le=200)):
    db = Database.get_db()
    fatture = await db["invoices"].find(
        {"processata_tracciabilita": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"fatture": fatture, "totale": len(fatture)}


@router.post("/segna-processata/{fattura_id}")
async def segna_fattura_processata(fattura_id: str):
    db = Database.get_db()
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "processata_tracciabilita": True,
            "processata_tracciabilita_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"status": "ok", "fattura_id": fattura_id}


@router.get("/status")
async def status():
    db = Database.get_db()
    totale = await db["invoices"].count_documents({})
    non_proc = await db["invoices"].count_documents({"processata_tracciabilita": {"$ne": True}})
    return {
        "status": "ok",
        "totale_fatture": totale,
        "non_processate_da_tracciabilita": non_proc
    }
