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