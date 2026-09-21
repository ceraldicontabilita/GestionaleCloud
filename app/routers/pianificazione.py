"""Pianificazione router - Budget planning."""
from fastapi import APIRouter, Body, Depends, Path, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/costi-previsionali",
    summary="Get planned costs"
)
async def get_costi_previsionali(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of planned costs."""
    db = Database.get_db()
    costi = await db["costi_previsionali"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return costi


@router.post(
    "/costi-previsionali",
    status_code=status.HTTP_201_CREATED,
    summary="Create planned cost"
)
async def create_costo(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a planned cost entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db["costi_previsionali"].insert_one(data.copy())
    return {"message": "Cost created", "id": data["id"]}


@router.delete(
    "/costi-previsionali/{costo_id}",
    summary="Delete planned cost"
)
async def delete_costo(
    costo_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a planned cost."""
    db = Database.get_db()
    await db["costi_previsionali"].delete_one({"id": costo_id})
    return {"message": "Cost deleted"}

@router.get("/events")
async def list_events(
    skip: int = 0,
    limit: int = 10000,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Lista eventi della pianificazione, con compatibilita' schema storico."""
    db = Database.get_db()
    events = await db["planning_events"].find({}, {"_id": 0}).to_list(limit or 10000)
    events.sort(key=lambda ev: ev.get("scheduled_date") or ev.get("start_date") or "")
    return events[skip: skip + (limit or 10000)]


@router.post("/events")
async def create_event(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Crea evento mantenendo leggibili i campi storici della pianificazione."""
    db = Database.get_db()
    scheduled = data.get("scheduled_date") or data.get("start_date") or ""
    event_type = data.get("event_type") or data.get("type") or "event"
    notes = data.get("notes") or data.get("description") or ""
    event = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "scheduled_date": scheduled,
        "start_date": scheduled,
        "end_date": data.get("end_date", ""),
        "event_type": event_type,
        "type": event_type,
        "notes": notes,
        "description": notes,
        "status": data.get("status", "scheduled"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["planning_events"].insert_one(event.copy())
    event.pop("_id", None)
    return event
