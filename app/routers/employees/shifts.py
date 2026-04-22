"""Shifts router - Employee shift scheduling."""
from fastapi import APIRouter, Body, Depends, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/schedule",
    summary="Get shift schedule"
)
async def get_schedule(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get shift schedule."""
    db = Database.get_db()
    shifts = await db["shifts"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return shifts


@router.post(
    "/schedule",
    status_code=status.HTTP_201_CREATED,
    summary="Create shift schedule"
)
async def create_schedule(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a shift schedule."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db["shifts"].insert_one(data.copy())
    return {"message": "Schedule created", "id": data["id"]}