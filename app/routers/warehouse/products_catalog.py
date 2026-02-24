"""
Products Catalog Router - Catalogo prodotti con prezzi e fornitori.
Refactored from public_api.py
"""
from fastapi import APIRouter, HTTPException, Body, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import uuid
import logging

from app.database import Database, Collections
from app.utils.warehouse_helpers import get_product_catalog, search_products_predictive, get_suppliers_for_product

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== WAREHOUSE PRODUCTS ==============

@router.get("/warehouse")
async def list_warehouse_products(skip: int = 0, limit: int = 10000, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista prodotti magazzino."""
    db = Database.get_db()
    query = {"category": category} if category else {}
    return await db[Collections.WAREHOUSE_PRODUCTS].find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)


@router.post("/warehouse")
async def create_warehouse_product(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea prodotto magazzino."""
    db = Database.get_db()
    product = {
        "id": str(uuid.uuid4()),
        "name": data.get("name", ""),
        "code": data.get("code", ""),
        "quantity": data.get("quantity", 0),
        "unit": data.get("unit", "pz"),
        "unit_price": data.get("unit_price", 0),
        "category": data.get("category", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.WAREHOUSE_PRODUCTS].insert_one(product.copy())
    product.pop("_id", None)
    return product


@router.delete("/warehouse/{product_id}")
async def delete_warehouse_product(product_id: str) -> Dict[str, Any]:
    """Elimina prodotto magazzino."""
    db = Database.get_db()
    result = await db[Collections.WAREHOUSE_PRODUCTS].delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"success": True, "deleted_id": product_id}


# ============== CATALOGO CON BEST PRICE ==============

@router.get("/catalog")
async def get_catalog(
    category: Optional[str] = None, 
    search: Optional[str] = None, 
    days: int = 30,
    exact: bool = Query(False, description="Se True, cerca match esatto")
) -> List[Dict[str, Any]]:
    """Catalogo prodotti con miglior prezzo ultimi N giorni."""
    db = Database.get_db()
    return await get_product_catalog(db, category=category, search=search, days=days, exact=exact)


@router.get("/search")
async def search_products(q: str = "", limit: int = 10) -> List[Dict[str, Any]]:
    """Ricerca predittiva prodotti."""
    db = Database.get_db()
    return await search_products_predictive(db, query=q, limit=limit)


@router.get("/categories")
async def get_categories() -> List[str]:
    """Lista categorie distinte."""
    db = Database.get_db()
    categories = await db["warehouse_inventory"].distinct("categoria")
    return sorted([c for c in categories if c])


@router.get("/{product_id}/suppliers")
async def get_product_suppliers(product_id: str, days: int = 90) -> List[Dict[str, Any]]:
    """Fornitori e prezzi per prodotto."""
    db = Database.get_db()
    return await get_suppliers_for_product(db, product_id=product_id, days=days)


# ============== STORICO PREZZI ==============

@router.get("/price-history")
async def get_price_history(
    product_id: Optional[str] = None,
    supplier_name: Optional[str] = None,
    days: int = 90
) -> List[Dict[str, Any]]:
    """Storico prezzi con filtri."""
    db = Database.get_db()
    
    date_threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query = {"created_at": {"$gte": date_threshold}}
    
    if product_id:
        query["product_id"] = product_id
    if supplier_name:
        query["supplier_name"] = {"$regex": supplier_name, "$options": "i"}
    
    return await db["price_history"].find(query, {"_id": 0}).sort("created_at", -1).limit(1000).to_list(1000)
