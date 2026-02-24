"""Notifications router - System notifications endpoints."""
from fastapi import APIRouter, Path, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get all notifications",
    description="Get all system notifications"
)
@router.get(
    "/all",
    summary="Get all notifications",
    description="Get all system notifications"
)
async def get_all_notifications(
    limit: int = Query(100, ge=1, le=500),
    tipo: Optional[str] = Query(None, description="Tipo notifica: scadenza, alert, verbale, haccp")
) -> List[Dict[str, Any]]:
    """Get all notifications."""
    db = Database.get_db()
    
    try:
        query = {}
        if tipo:
            query["tipo"] = tipo
            
        notifications = await db["notifications"].find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        return notifications
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        return []


@router.get(
    "/review",
    summary="Get notifications to review",
    description="Get pending notifications that need review"
)
async def get_review_notifications(
    limit: int = Query(50, ge=1, le=200)
) -> List[Dict[str, Any]]:
    """Get notifications pending review."""
    db = Database.get_db()
    
    try:
        notifications = await db["notifications"].find(
            {"reviewed": {"$ne": True}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        return notifications
    except Exception as e:
        logger.error(f"Error getting review notifications: {e}")
        return []


@router.get(
    "/unread-count",
    summary="Get unread notifications count"
)
async def get_unread_count() -> Dict[str, int]:
    """Get count of unread notifications."""
    db = Database.get_db()
    
    try:
        count = await db["notifications"].count_documents({"reviewed": {"$ne": True}})
        return {"count": count}
    except Exception as e:
        logger.error(f"Error counting notifications: {e}")
        return {"count": 0}


@router.post(
    "/review/{notification_id}/mark-reviewed",
    summary="Mark notification as reviewed"
)
async def mark_reviewed(
    notification_id: str = Path(...)
) -> Dict[str, str]:
    """Mark a notification as reviewed."""
    db = Database.get_db()
    
    result = await db["notifications"].update_one(
        {"id": notification_id},
        {"$set": {"reviewed": True, "reviewed_at": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count > 0:
        return {"message": "Notification marked as reviewed"}
    return {"message": "Notification not found or already reviewed"}


@router.post(
    "/mark-all-read",
    summary="Mark all notifications as read"
)
async def mark_all_read() -> Dict[str, Any]:
    """Mark all notifications as reviewed."""
    db = Database.get_db()
    
    result = await db["notifications"].update_many(
        {"reviewed": {"$ne": True}},
        {"$set": {"reviewed": True, "reviewed_at": datetime.now(timezone.utc)}}
    )
    
    return {
        "message": "All notifications marked as read",
        "count": result.modified_count
    }


@router.delete(
    "/{notification_id}",
    summary="Delete a notification"
)
async def delete_notification(
    notification_id: str = Path(...)
) -> Dict[str, str]:
    """Delete a notification."""
    db = Database.get_db()
    
    result = await db["notifications"].delete_one({"id": notification_id})
    
    if result.deleted_count > 0:
        return {"message": "Notification deleted"}
    return {"message": "Notification not found"}
