"""Cart router - Shopping cart functionality."""
from fastapi import APIRouter, Depends, Path, status
from typing import Dict, Any
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get cart"
)
async def get_cart(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current cart."""
    db = Database.get_db()
    cart = await db["carts"].find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    return cart or {"items": [], "total": 0}


@router.post(
    "/item",
    status_code=status.HTTP_201_CREATED,
    summary="Add item to cart"
)
async def add_to_cart(
    item: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Add item to cart."""
    db = Database.get_db()
    await db["carts"].update_one(
        {"user_id": current_user["user_id"]},
        {"$push": {"items": item}},
        upsert=True
    )
    return {"message": "Item added"}


@router.delete(
    "/item/{index}",
    summary="Remove item from cart"
)
async def remove_from_cart(
    index: int = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Remove item from cart by index."""
    db = Database.get_db()
    cart = await db["carts"].find_one({"user_id": current_user["user_id"]})
    if cart and "items" in cart and 0 <= index < len(cart["items"]):
        cart["items"].pop(index)
        await db["carts"].update_one(
            {"user_id": current_user["user_id"]},
            {"$set": {"items": cart["items"]}}
        )
    return {"message": "Item removed"}


@router.delete(
    "/clear",
    summary="Clear cart"
)
async def clear_cart(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear all items from cart."""
    db = Database.get_db()
    await db["carts"].delete_one({"user_id": current_user["user_id"]})
    return {"message": "Cart cleared"}
