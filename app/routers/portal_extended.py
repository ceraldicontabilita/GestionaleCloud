"""Portal Extended router - Additional portal endpoints."""
from fastapi import APIRouter, Depends
from typing import Dict, Any, List
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/documents",
    summary="Get portal documents"
)
async def get_portal_documents(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get portal documents for user."""
    db = Database.get_db()
    docs = await db["portal_documents"].find(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    ).to_list(100)
    return docs


@router.get(
    "/me",
    summary="Get current portal user"
)
async def get_portal_me(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current portal user info."""
    return {
        "user_id": current_user["user_id"],
        "email": current_user.get("email", ""),
        "name": current_user.get("name", "")
    }


@router.get(
    "/payslips",
    summary="Get payslips"
)
async def get_payslips(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get payslips for user (da collection cedolini unificata)."""
    db = Database.get_db()
    # Usa cedolini - collection unificata
    payslips = await db["cedolini"].find(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(100)
    return payslips
