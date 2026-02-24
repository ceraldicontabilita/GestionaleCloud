"""
Router Comparatore Prezzi - Confronto prezzi fornitori.
Parsing fatture, normalizzazione prodotti, carrello acquisti.
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import re
import logging
import uuid

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


def normalize_product_name_simple(description: str) -> str:
    """
    Normalizzazione semplice senza AI.
    Estrae parole chiave significative.
    """
    if not description:
        return "PRODOTTO"
    
    desc = re.sub(r'\b[A-Z]{2,3}\d{4,}\b', '', description.upper())
    desc = re.sub(r'\bCOD\.?\s*\d+\b', '', desc)
    desc = re.sub(r'\bRIF\.?\s*\d+\b', '', desc)
    
    words = [w for w in desc.split() if len(w) > 3 and not w.isdigit()]
    
    if words:
        return ' '.join(words[:3])
    
    return description[:30].strip().upper() if description else "PRODOTTO"


# ============== API ENDPOINTS ==============

@router.get("/")
async def comparatore_root():
    """Root endpoint comparatore."""
    return {"message": "Comparatore Prezzi API", "version": "1.0"}


@router.get("/invoices")
async def get_invoices(supplier: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista fatture per comparatore."""
    db = Database.get_db()
    
    query = {}
    if supplier:
        query["supplier_name"] = {"$regex": supplier, "$options": "i"}
    
    invoices = await db["invoices"].find(query, {"_id": 0}).sort("invoice_date", -1).limit(500).to_list(500)
    
    result = []
    for inv in invoices:
        result.append({
            "id": inv.get("id"),
            "supplier_name": inv.get("supplier_name", ""),
            "supplier_vat": inv.get("supplier_vat", ""),
            "invoice_number": inv.get("invoice_number", ""),
            "invoice_date": inv.get("invoice_date", ""),
            "total_amount": float(inv.get("total_amount", 0) or 0),
            "lines_count": len(inv.get("linee", [])),
            "uploaded_at": inv.get("created_at", "")
        })
    
    return result


@router.get("/suppliers")
async def get_suppliers() -> List[str]:
    """Lista fornitori distinti."""
    db = Database.get_db()
    suppliers = await db["invoices"].distinct("supplier_name")
    return sorted([s for s in suppliers if s])


@router.get("/unmapped-products")
async def get_unmapped_products() -> List[Dict[str, Any]]:
    """Prodotti non ancora mappati."""
    db = Database.get_db()
    
    six_months_ago = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    
    invoices = await db["invoices"].find(
        {"created_at": {"$gte": six_months_ago}},
        {"_id": 0, "linee": 1, "supplier_name": 1, "supplier_vat": 1}
    ).limit(200).to_list(200)
    
    descriptions = {}
    for inv in invoices:
        for line in inv.get("linee", []):
            desc = line.get("descrizione", "")
            if desc and desc not in descriptions:
                descriptions[desc] = {
                    "original_description": desc,
                    "supplier_name": inv.get("supplier_name", ""),
                    "supplier_vat": inv.get("supplier_vat", ""),
                    "unit_price": float(line.get("prezzo_unitario", 0) or 0)
                }
    
    catalog = await db["product_catalog"].find(
        {"product_name": {"$exists": True, "$ne": ""}},
        {"_id": 0, "original_description": 1}
    ).to_list(5000)
    
    mapped_descs = {c.get("original_description") for c in catalog}
    unmapped = [v for k, v in descriptions.items() if k not in mapped_descs]
    
    return unmapped[:100]


@router.get("/mapped-products")
async def get_mapped_products() -> List[Dict[str, Any]]:
    """Prodotti già mappati."""
    db = Database.get_db()
    
    products = await db["product_catalog"].find(
        {"product_name": {"$exists": True, "$ne": ""}},
        {"_id": 0}
    ).limit(1000).to_list(1000)
    
    return products


@router.post("/map-product")
async def map_product(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Mappa un prodotto singolo."""
    db = Database.get_db()
    
    original_desc = data.get("original_description", "")
    if not original_desc:
        raise HTTPException(status_code=400, detail="Descrizione richiesta")
    
    normalized = data.get("normalized_name")
    if not normalized:
        normalized = normalize_product_name_simple(original_desc)
    else:
        normalized = normalized.strip().upper()
    
    await db["product_catalog"].update_one(
        {"original_description": original_desc},
        {"$set": {
            "original_description": original_desc,
            "product_name": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {"success": True, "original": original_desc, "normalized": normalized}


@router.post("/map-all-products")
async def map_all_products(limit: int = 50) -> Dict[str, Any]:
    """Mappa automaticamente prodotti non mappati."""
    db = Database.get_db()
    
    unmapped = await get_unmapped_products()
    
    results = {"processed": 0, "mapped": 0, "errors": 0}
    
    for product in unmapped[:limit]:
        try:
            desc = product.get("original_description", "")
            if not desc:
                continue
            
            normalized = normalize_product_name_simple(desc)
            
            await db["product_catalog"].update_one(
                {"original_description": desc},
                {"$set": {
                    "original_description": desc,
                    "product_name": normalized,
                    "supplier_name": product.get("supplier_name", ""),
                    "supplier_vat": product.get("supplier_vat", ""),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            
            results["mapped"] += 1
            results["processed"] += 1
            
        except Exception as e:
            logger.error(f"Error mapping product: {e}")
            results["errors"] += 1
            results["processed"] += 1
    
    return results


@router.get("/products")
async def get_products(
    search: Optional[str] = None,
    supplier: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Prodotti con confronto prezzi."""
    db = Database.get_db()
    
    catalog = await db["product_catalog"].find(
        {"product_name": {"$exists": True, "$ne": ""}},
        {"_id": 0}
    ).to_list(5000)
    
    desc_to_name = {c.get("original_description"): c.get("product_name") for c in catalog}
    
    six_months_ago = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    
    query = {"created_at": {"$gte": six_months_ago}}
    if supplier:
        query["supplier_name"] = {"$regex": supplier, "$options": "i"}
    
    invoices = await db["invoices"].find(query, {"_id": 0}).limit(1000).to_list(1000)
    
    excluded = await db["comparatore_supplier_exclusions"].distinct("supplier_name")
    
    products_map = {}
    
    for inv in invoices:
        if inv.get("supplier_name") in excluded:
            continue
        
        for line in inv.get("linee", []):
            desc = line.get("descrizione", "")
            normalized = desc_to_name.get(desc, normalize_product_name_simple(desc))
            
            if search and search.upper() not in normalized.upper() and search.upper() not in desc.upper():
                continue
            
            price = float(line.get("prezzo_unitario", 0) or 0)
            if price <= 0:
                continue
            
            if normalized not in products_map:
                products_map[normalized] = {
                    "normalized_name": normalized,
                    "suppliers": [],
                    "best_price": price,
                    "best_supplier": inv.get("supplier_name", ""),
                    "prices_count": 0
                }
            
            products_map[normalized]["suppliers"].append({
                "supplier_name": inv.get("supplier_name", ""),
                "supplier_vat": inv.get("supplier_vat", ""),
                "price": price,
                "unit": line.get("unita_misura", "PZ"),
                "original_description": desc,
                "invoice_date": inv.get("invoice_date", "")
            })
            
            products_map[normalized]["prices_count"] += 1
            
            if price < products_map[normalized]["best_price"]:
                products_map[normalized]["best_price"] = price
                products_map[normalized]["best_supplier"] = inv.get("supplier_name", "")
    
    result = list(products_map.values())
    result.sort(key=lambda x: x["normalized_name"])
    
    return result[:500]


# ============== CARRELLO ==============

@router.post("/cart/add")
async def add_to_cart(item: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiunge prodotto al carrello."""
    db = Database.get_db()
    
    cart_item = {
        "id": str(uuid.uuid4()),
        "normalized_name": item.get("normalized_name", ""),
        "original_description": item.get("original_description", ""),
        "supplier_name": item.get("supplier_name", ""),
        "supplier_vat": item.get("supplier_vat", ""),
        "price": float(item.get("price", 0) or 0),
        "unit": item.get("unit", "PZ"),
        "quantity": float(item.get("quantity", 1) or 1),
        "invoice_date": item.get("invoice_date", ""),
        "added_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["comparatore_cart"].insert_one(cart_item.copy())
    cart_item.pop("_id", None)
    
    return {"success": True, "item": cart_item}


@router.get("/cart")
async def get_cart() -> Dict[str, Any]:
    """Restituisce carrello con raggruppamento per fornitore."""
    db = Database.get_db()
    
    items = await db["comparatore_cart"].find({}, {"_id": 0}).to_list(500)
    
    by_supplier = {}
    for item in items:
        supplier = item.get("supplier_name", "Altro")
        if supplier not in by_supplier:
            by_supplier[supplier] = {"supplier": supplier, "items": [], "subtotal": 0}
        by_supplier[supplier]["items"].append(item)
        by_supplier[supplier]["subtotal"] += float(item.get("price", 0) or 0) * float(item.get("quantity", 1) or 1)
    
    total = sum(s["subtotal"] for s in by_supplier.values())
    
    return {
        "by_supplier": list(by_supplier.values()),
        "total_items": len(items),
        "total_amount": round(total, 2)
    }


@router.delete("/cart/{item_id}")
async def remove_from_cart(item_id: str) -> Dict[str, Any]:
    """Rimuove prodotto dal carrello."""
    db = Database.get_db()
    
    result = await db["comparatore_cart"].delete_one({"id": item_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    
    return {"success": True, "deleted_id": item_id}


@router.delete("/cart")
async def clear_cart() -> Dict[str, Any]:
    """Svuota carrello."""
    db = Database.get_db()
    result = await db["comparatore_cart"].delete_many({})
    return {"success": True, "deleted_count": result.deleted_count}


# ============== ESCLUSIONE FORNITORI ==============

@router.post("/exclude-supplier")
async def exclude_supplier(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiunge/rimuove fornitore dalla lista esclusioni."""
    db = Database.get_db()
    
    supplier_name = data.get("supplier_name", "")
    exclude = data.get("exclude", True)
    
    if exclude:
        await db["comparatore_supplier_exclusions"].update_one(
            {"supplier_name": supplier_name},
            {"$set": {
                "supplier_name": supplier_name,
                "excluded_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        return {"success": True, "message": f"{supplier_name} escluso"}
    else:
        await db["comparatore_supplier_exclusions"].delete_one({"supplier_name": supplier_name})
        return {"success": True, "message": f"{supplier_name} riammesso"}


@router.get("/excluded-suppliers")
async def get_excluded_suppliers() -> List[str]:
    """Lista fornitori esclusi."""
    db = Database.get_db()
    excluded = await db["comparatore_supplier_exclusions"].distinct("supplier_name")
    return excluded
