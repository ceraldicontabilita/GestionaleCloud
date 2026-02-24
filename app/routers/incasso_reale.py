"""Incasso Reale router - Real income tracking."""
from fastapi import APIRouter, Depends, Path, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get real income entries"
)
async def get_incassi(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of real income entries."""
    db = Database.get_db()
    incassi = await db["incasso_reale"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return incassi


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create income entry"
)
async def create_incasso(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a new income entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    data["user_id"] = current_user["user_id"]
    await db["incasso_reale"].insert_one(data.copy())
    return {"message": "Income entry created", "id": data["id"]}


@router.delete(
    "/{entry_id}",
    summary="Delete income entry"
)
async def delete_incasso(
    entry_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete an income entry."""
    db = Database.get_db()
    await db["incasso_reale"].delete_one({"id": entry_id})
    return {"message": "Income entry deleted"}


@router.delete(
    "/all",
    summary="Delete all income entries"
)
async def delete_all_incassi(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete all income entries."""
    db = Database.get_db()
    result = await db["incasso_reale"].delete_many({})
    return {"message": f"Deleted {result.deleted_count} entries"}
