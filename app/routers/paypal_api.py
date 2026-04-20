from fastapi import APIRouter, HTTPException, Body
from datetime import datetime, timezone
from typing import Dict, Any

from app.database import Database
from app.services.paypal_api_sync import sync_paypal_period

router = APIRouter(prefix="/paypal-api", tags=["paypal-api"])


@router.post("/sync")
async def sync_period(body: Dict[str, Any] = Body(...)):
    try:
        start = datetime.fromisoformat(body["start_date"]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(body["end_date"]).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"Formato data non valido: {e}")

    db = Database.get_db()
    result = await sync_paypal_period(db, start, end)
    return result


@router.post("/sync/month")
async def sync_current_month():
    from calendar import monthrange
    now = datetime.now(timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(day=last_day, hour=23, minute=59, second=59)

    db = Database.get_db()
    return await sync_paypal_period(db, start, end)


@router.get("/status")
async def status():
    db = Database.get_db()
    total = await db["paypal_transactions"].count_documents({})
    enriched = await db["paypal_transactions"].count_documents({"source": "paypal_api"})
    pagopa = await db["paypal_transactions"].count_documents({"is_pagopa": True})

    last = await db["paypal_transactions"].find_one(
        {"source": "paypal_api"},
        sort=[("enriched_at", -1)],
        projection={"_id": 0, "enriched_at": 1},
    )
    return {
        "total_transazioni": total,
        "arricchite_da_api": enriched,
        "identificate_pagopa": pagopa,
        "ultimo_sync": last.get("enriched_at") if last else None,
    }
