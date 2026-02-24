"""Lotti router - Batch/Lot tracking."""
from fastapi import APIRouter, Depends, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/in",
    summary="Get incoming lots"
)
async def get_lotti_in(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of incoming lots."""
    db = Database.get_db()
    lotti = await db["lotti"].find({"type": "in"}, {"_id": 0}).sort("date", -1).to_list(500)
    return lotti


@router.post(
    "/in",
    status_code=status.HTTP_201_CREATED,
    summary="Create incoming lot"
)
async def create_lotto_in(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create an incoming lot entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["type"] = "in"
    data["created_at"] = datetime.now(timezone.utc)
    await db["lotti"].insert_one(data.copy())
    return {"message": "Lot created", "id": data["id"]}


@router.get(
    "/out",
    summary="Get outgoing lots"
)
async def get_lotti_out(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of outgoing lots."""
    db = Database.get_db()
    lotti = await db["lotti"].find({"type": "out"}, {"_id": 0}).sort("date", -1).to_list(500)
    return lotti


@router.post(
    "/out",
    status_code=status.HTTP_201_CREATED,
    summary="Create outgoing lot"
)
async def create_lotto_out(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create an outgoing lot entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["type"] = "out"
    data["created_at"] = datetime.now(timezone.utc)
    await db["lotti"].insert_one(data.copy())
    return {"message": "Lot created", "id": data["id"]}
