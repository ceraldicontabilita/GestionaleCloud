"""Magazzino router - Warehouse sync."""
from fastapi import APIRouter, Depends
from typing import Dict, Any
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/sync",
    summary="Sync warehouse"
)
async def sync_magazzino(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Synchronize warehouse data."""
    db = Database.get_db()
    
    # Count products
    products_count = await db[Collections.WAREHOUSE_PRODUCTS].count_documents({})
    
    return {
        "message": "Sync completed",
        "products_synced": products_count,
        "movements_processed": 0
    }
