"""Products router - Product catalog management."""
from fastapi import APIRouter, Body, Depends, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get products"
)
async def get_products(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of products."""
    db = Database.get_db()
    products = await db[Collections.WAREHOUSE_PRODUCTS].find({}, {"_id": 0}).to_list(1000)
    return products


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create product"
)
async def create_product(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a new product."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db[Collections.WAREHOUSE_PRODUCTS].insert_one(data.copy())
    return {"message": "Product created", "id": data["id"]}


@router.delete(
    "/clear-all-data",
    summary="Clear all product data"
)
async def clear_all_data(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear all product data."""
    db = Database.get_db()
    await db[Collections.WAREHOUSE_PRODUCTS].delete_many({})
    return {"message": "All products cleared"}


@router.delete(
    "/clear-mappings",
    summary="Clear product mappings"
)
async def clear_mappings(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear product mappings."""
    db = Database.get_db()
    await db["product_mappings"].delete_many({})
    return {"message": "Mappings cleared"}


@router.delete(
    "/clear-price-history",
    summary="Clear price history"
)
async def clear_price_history(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear price history."""
    db = Database.get_db()
    await db["price_history"].delete_many({})
    return {"message": "Price history cleared"}