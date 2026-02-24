"""Failed Invoices router - Handle failed invoice imports."""
from fastapi import APIRouter, Depends, Path
from typing import Dict, Any, List
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get failed invoices",
    description="Get list of invoices that failed to import"
)
async def get_failed_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get failed invoices."""
    db = Database.get_db()
    
    try:
        failed = await db["failed_invoices"].find(
            {}, {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        return failed
    except Exception:
        return []


@router.delete(
    "/{invoice_id}",
    summary="Delete failed invoice"
)
async def delete_failed_invoice(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a failed invoice entry."""
    db = Database.get_db()
    
    await db["failed_invoices"].delete_one({"id": invoice_id})
    
    return {"message": "Failed invoice deleted"}


@router.delete(
    "",
    summary="Clear all failed invoices"
)
async def clear_failed_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear all failed invoices."""
    db = Database.get_db()
    
    result = await db["failed_invoices"].delete_many({})
    
    return {"message": f"Cleared {result.deleted_count} failed invoices"}


@router.post(
    "/{invoice_id}/retry",
    summary="Retry failed invoice import"
)
async def retry_failed_invoice(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Retry importing a failed invoice."""
    # TODO: Implement retry logic
    return {"message": "Retry queued", "invoice_id": invoice_id}
