"""Config router - Application configuration endpoints."""
from fastapi import APIRouter, Depends
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
    config_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update email configuration."""
    db = Database.get_db()
    config_data["type"] = "email"
    config_data["updated_at"] = datetime.now(timezone.utc)
    await db["config"].update_one({"type": "email"}, {"$set": config_data}, upsert=True)
    return {"message": "Email config updated"}


@router.get(
    "/haccp/equipment-names",
    summary="Get HACCP equipment names"
)
async def get_haccp_equipment_names(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[str]:
    """Get list of HACCP equipment names."""
    db = Database.get_db()
    config = await db["config"].find_one({"type": "haccp_equipment"}, {"_id": 0})
    return config.get("names", []) if config else []


@router.put(
    "/haccp/equipment-names",
    summary="Update HACCP equipment names"
)
async def update_haccp_equipment_names(
    names: List[str],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update HACCP equipment names."""
    db = Database.get_db()
    await db["config"].update_one(
        {"type": "haccp_equipment"},
        {"$set": {"names": names, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Equipment names updated"}


@router.get(
    "/haccp/operators",
    summary="Get HACCP operators"
)
async def get_haccp_operators(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[str]:
    """Get list of HACCP operators."""
    db = Database.get_db()
    config = await db["config"].find_one({"type": "haccp_operators"}, {"_id": 0})
    return config.get("operators", []) if config else []


@router.put(
    "/haccp/operators",
    summary="Update HACCP operators"
)
async def update_haccp_operators(
    operators: List[str],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update HACCP operators list."""
    db = Database.get_db()
    await db["config"].update_one(
        {"type": "haccp_operators"},
        {"$set": {"operators": operators, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Operators updated"}
