"""Config router - Application configuration endpoints."""
from fastapi import APIRouter, Body, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/email",
    summary="Get email config"
)
async def get_email_config(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get email configuration."""
    db = Database.get_db()
    config = await db["config"].find_one({"type": "email"}, {"_id": 0})
    return config or {"smtp_host": "", "smtp_port": 587, "smtp_user": "", "from_email": ""}


@router.put(
    "/email",
    summary="Update email config"
)
async def update_email_config(
    config_data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update email configuration."""
    db = Database.get_db()
    config_data["type"] = "email"
    config_data["updated_at"] = datetime.now(timezone.utc)
    await db["config"].update_one({"type": "email"}, {"$set": config_data}, upsert=True)
    return {"message": "Email config updated"}