"""Invoices Export router."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any
import logging

from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/export-excel",
    summary="Export invoices to Excel"
)
async def export_invoices_excel(
    year: int = Query(None),
    month: int = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Export invoices to Excel."""
    # TODO: Implement Excel export
    return {
        "message": "Excel export not yet implemented",
        "url": None
    }
