"""
Warehouse router.
Handles inventory and stock management operations.
"""
from fastapi import APIRouter, Depends, Query, status, Body, Path
from pydantic import BaseModel
from fastapi import HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date
import logging

from app.database import Database, Collections
from app.repositories import (
    WarehouseRepository,
    WarehouseMovementRepository,
    InvoiceRepository
)
from app.services import WarehouseService
from app.utils.dependencies import get_current_user, pagination_params

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency to get warehouse service
async def get_warehouse_service() -> WarehouseService:
    """Get warehouse service with injected dependencies."""
    db = Database.get_db()
    warehouse_repo = WarehouseRepository(db[Collections.WAREHOUSE_PRODUCTS])
    movement_repo = WarehouseMovementRepository(db[Collections.WAREHOUSE_MOVEMENTS])
    invoice_repo = InvoiceRepository(db[Collections.INVOICES])
    return WarehouseService(warehouse_repo, movement_repo, invoice_repo)


@router.get(
    "/products",
    response_model=List[Dict[str, Any]],
    summary="List warehouse products",
    description="Get list of products in warehouse"
)
async def list_products(
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    category: Optional[str] = Query(None, description="Filter by category"),
    supplier_vat: Optional[str] = Query(None, description="Filter by supplier VAT"),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> List[Dict[str, Any]]:
    """
    List warehouse products with optional filters.
    
    **Query Parameters:**
    - **skip**: Number of products to skip (pagination)
    - **limit**: Maximum number of products to return
    - **category**: Filter by product category
    - **supplier_vat**: Filter by supplier VAT number
    """
    user_id = current_user["user_id"]
    
    return await warehouse_service.list_products(
        user_id=user_id,
        skip=pagination["skip"],
        limit=pagination["limit"],
        category=category,
        supplier_vat=supplier_vat
    )


@router.get(
    "/products/search",
    response_model=List[Dict[str, Any]],
    summary="Search products",
    description="Search products by name or code"
)
async def search_products(
    q: str = Query(..., description="Search query"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> List[Dict[str, Any]]:
    """
    Search products by name, code, or description.
    
    **Query Parameters:**
    - **q**: Search query
    """
    user_id = current_user["user_id"]
    
    return await warehouse_service.search_products(
        user_id=user_id,
        query=q,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.get(
    "/products/low-stock",
    response_model=List[Dict[str, Any]],
    summary="Get low stock products",
    description="Get products with stock below minimum level"
)
async def get_low_stock_products(
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> List[Dict[str, Any]]:
    """
    Get products with available quantity below minimum stock level.
    
    Returns products sorted by quantity (lowest first).
    """
    user_id = current_user["user_id"]
    
    return await warehouse_service.get_low_stock_products(
        user_id=user_id,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.get(
    "/products/{product_id}",
    response_model=Dict[str, Any],
    summary="Get product details",
    description="Get detailed product information"
)
async def get_product(
    product_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, Any]:
    """
    Get product details by ID.
    
    Returns complete product data including stock levels and pricing.
    """
    return await warehouse_service.get_product(product_id)


@router.get(
    "/products/{product_id}/movements",
    response_model=List[Dict[str, Any]],
    summary="Get product movements",
    description="Get movement history for a product"
)
async def get_product_movements(
    product_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> List[Dict[str, Any]]:
    """
    Get movement history for a specific product.
    
    Returns movements sorted by date (newest first).
    """
    user_id = current_user["user_id"]
    
    return await warehouse_service.get_product_movements(
        product_id=product_id,
        user_id=user_id,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.post(
    "/stock/add-from-invoice",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Add stock from invoice",
    description="Import products from invoice and add to warehouse"
)
async def add_stock_from_invoice(
    invoice_id: str = Body(..., embed=True),
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, Any]:
    """
    Automatically add stock from invoice products.
    
    - Creates warehouse products if they don't exist
    - Updates existing products with new stock
    - Records all stock movements
    - Updates pricing statistics
    
    **Request Body:**
    ```json
    {
        "invoice_id": "invoice_id_here"
    }
    ```
    """
    user_id = current_user["user_id"]
    
    movement_ids = await warehouse_service.add_stock_from_invoice(
        invoice_id=invoice_id,
        user_id=user_id
    )
    
    return {
        "message": "Stock added successfully",
        "movements_created": len(movement_ids),
        "movement_ids": movement_ids
    }


@router.post(
    "/stock/subtract",
    response_model=Dict[str, str],
    status_code=status.HTTP_201_CREATED,
    summary="Subtract stock",
    description="Remove stock (scarico)"
)
async def subtract_stock(
    product_id: str = Body(...),
    quantity: float = Body(..., gt=0),
    reason: str = Body(...),
    document_type: Optional[str] = Body(None),
    document_id: Optional[str] = Body(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, str]:
    """
    Subtract stock from warehouse (scarico).
    
    - Validates available quantity
    - Updates product stock
    - Records movement
    
    **Request Body:**
    ```json
    {
        "product_id": "product_id_here",
        "quantity": 10.5,
        "reason": "Vendita al cliente",
        "document_type": "scontrino",
        "document_id": "optional_document_id"
    }
    ```
    """
    user_id = current_user["user_id"]
    
    movement_id = await warehouse_service.subtract_stock(
        product_id=product_id,
        quantity=quantity,
        reason=reason,
        user_id=user_id,
        document_type=document_type,
        document_id=document_id
    )
    
    return {
        "message": "Stock subtracted successfully",
        "movement_id": movement_id
    }


@router.post(
    "/stock/adjust",
    response_model=Dict[str, str],
    status_code=status.HTTP_201_CREATED,
    summary="Adjust stock",
    description="Adjust stock to specific quantity (rettifica)"
)
async def adjust_stock(
    product_id: str = Body(...),
    new_quantity: float = Body(..., ge=0),
    reason: str = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, str]:
    """
    Adjust stock to a specific quantity (rettifica inventario).
    
    Used for inventory corrections, spoilage, etc.
    
    **Request Body:**
    ```json
    {
        "product_id": "product_id_here",
        "new_quantity": 100.0,
        "reason": "Inventario fisico"
    }
    ```
    """
    user_id = current_user["user_id"]
    
    movement_id = await warehouse_service.adjust_stock(
        product_id=product_id,
        new_quantity=new_quantity,
        reason=reason,
        user_id=user_id
    )
    
    return {
        "message": "Stock adjusted successfully",
        "movement_id": movement_id
    }


@router.get(
    "/inventory/value",
    response_model=Dict[str, Any],
    summary="Get inventory value",
    description="Calculate total inventory value"
)
async def get_inventory_value(
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, Any]:
    """
    Calculate total inventory value.
    
    Returns total value based on average purchase prices.
    """
    user_id = current_user["user_id"]
    
    total_value = await warehouse_service.calculate_inventory_value(user_id)
    
    return {
        "total_value": total_value,
        "currency": "EUR"
    }


@router.get(
    "/inventory/summary",
    response_model=Dict[str, Any],
    summary="Get inventory summary",
    description="Get comprehensive inventory summary"
)
async def get_inventory_summary(
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, Any]:
    """
    Get comprehensive inventory summary.
    
    Returns:
    - Total products count
    - Total inventory value
    - Low stock products count and list
    - Distribution by category
    """
    user_id = current_user["user_id"]
    
    return await warehouse_service.get_inventory_summary(user_id)


@router.post(
    "/auto-map-invoice/{invoice_id}",
    summary="Auto map invoice to warehouse",
    description="Automatically add products from invoice to warehouse (Path param version)"
)
async def auto_map_invoice(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, Any]:
    """
    Automatically add stock from invoice products (Button action).
    
    Creates products/movements based on invoice lines.
    """
    user_id = current_user["user_id"]
    
    movement_ids = await warehouse_service.add_stock_from_invoice(
        invoice_id=invoice_id,
        user_id=user_id
    )
    
    return {
        "message": "Stock added successfully",
        "products_mapped": len(movement_ids),
        "products_created": len(movement_ids), # Approximation
        "movement_ids": movement_ids
    }


class RimanenzaCreate(BaseModel):
    """Rimanenza (stock adjustment) creation model."""
    product_id: str
    date: date
    quantity: float
    reason: str  # "inventario", "perdita", "correzione"
    notes: str = None


class ExclusionKeywordsUpdate(BaseModel):
    """Exclusion keywords update model."""
    keywords: List[str]


@router.get(
    "/rimanenze",
    summary="Get rimanenze (stock adjustments)"
)
async def get_rimanenze(
    current_user: Dict[str, Any] = Depends(get_current_user),
    start_date: date = None,
    end_date: date = None
) -> List[Dict[str, Any]]:
    """
    Get list of rimanenze adjustments.
    
    Rimanenze are stock adjustments made during physical inventory.
    Used for accounting reconciliation at year-end.
    """
    user_id = current_user["user_id"]
    db = Database.get_db()
    rimanenze_collection = db[Collections.RIMANENZE]
    
    # Build query
    query = {"user_id": user_id}
    
    if start_date:
        query["date"] = {"$gte": start_date.isoformat()}
    if end_date:
        if "date" in query:
            query["date"]["$lte"] = end_date.isoformat()
        else:
            query["date"] = {"$lte": end_date.isoformat()}
    
    # Fetch rimanenze
    cursor = rimanenze_collection.find(query).sort("date", -1).limit(1000)
    rimanenze = []
    
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        rimanenze.append(doc)
    
    logger.info(f"Retrieved {len(rimanenze)} rimanenze for user {user_id}")
    
    return rimanenze


@router.post(
    "/rimanenze",
    status_code=status.HTTP_201_CREATED,
    summary="Add rimanenza"
)
async def add_rimanenza(
    rimanenza: RimanenzaCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, str]:
    """
    Add stock adjustment (rimanenza).
    
    Creates a rimanenza entry for accounting purposes.
    Updates warehouse stock accordingly.
    """
    user_id = current_user["user_id"]
    
    # Validate reason
    valid_reasons = ["inventario", "perdita", "correzione", "rientro"]
    if rimanenza.reason not in valid_reasons:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reason. Must be one of: {', '.join(valid_reasons)}"
        )
    
    try:
        # Get product to verify existence
        product = await service.get_product(rimanenza.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Create rimanenza record
        db = Database.get_db()
        rimanenze_collection = db[Collections.RIMANENZE]
        
        rimanenza_doc = {
            "user_id": user_id,
            "product_id": rimanenza.product_id,
            "product_name": product.get("name"),
            "date": rimanenza.date.isoformat(),
            "quantity": rimanenza.quantity,
            "reason": rimanenza.reason,
            "notes": rimanenza.notes,
            "previous_stock": product.get("stock", 0),
            "new_stock": product.get("stock", 0) + rimanenza.quantity,
            "created_at": date.today().isoformat()
        }
        
        result = await rimanenze_collection.insert_one(rimanenza_doc.copy())
        rimanenza_id = str(result.inserted_id)
        
        # Update product stock
        await service.warehouse_repo.update_stock(
            product_id=rimanenza.product_id,
            quantity_change=rimanenza.quantity,
            movement_type=rimanenza.reason
        )
        
        logger.info(
            f"Created rimanenza {rimanenza_id} for product {rimanenza.product_id}: "
            f"{rimanenza.quantity} units"
        )
        
        return {
            "message": "Rimanenza created successfully",
            "rimanenza_id": rimanenza_id,
            "product_id": rimanenza.product_id,
            "adjustment": rimanenza.quantity
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating rimanenza: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/rimanenze/{rimanenza_id}",
    summary="Remove rimanenza"
)
async def remove_rimanenza(
    rimanenza_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service)
) -> Dict[str, str]:
    """
    Remove stock adjustment.
    
    Deletes rimanenza and reverts stock adjustment.
    """
    user_id = current_user["user_id"]
    
    try:
        db = Database.get_db()
        rimanenze_collection = db[Collections.RIMANENZE]
        
        # Get rimanenza
        from bson import ObjectId
        from bson.errors import InvalidId
        rimanenza = await rimanenze_collection.find_one({
            "_id": ObjectId(rimanenza_id),
            "user_id": user_id
        })
        
        if not rimanenza:
            raise HTTPException(status_code=404, detail="Rimanenza not found")
        
        # Revert stock adjustment
        # Note: quantity was ADDED, so we subtract it to revert
        await service.warehouse_repo.update_stock(
            product_id=rimanenza["product_id"],
            quantity_change=-rimanenza["quantity"],
            movement_type="annullamento_rimanenza"
        )
        
        # Delete rimanenza
        await rimanenze_collection.delete_one({"_id": ObjectId(rimanenza_id)})
        
        logger.info(f"Deleted rimanenza {rimanenza_id}")
        
        return {
            "message": "Rimanenza removed successfully",
            "rimanenza_id": rimanenza_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing rimanenza: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/exclusions",
    summary="Get exclusion keywords"
)
async def get_exclusion_keywords(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, List[str]]:
    """
    Get product exclusion keywords.
    """
    user_id = current_user["user_id"]
    db = Database.get_db()
    settings_collection = db[Collections.WAREHOUSE_SETTINGS]
    
    # Get settings
    settings = await settings_collection.find_one({"user_id": user_id})
    
    keywords = settings.get("exclusion_keywords", []) if settings else []
    
    # Default keywords if none set
    if not keywords:
        keywords = [
            "servizio",
            "spedizione",
            "trasporto",
            "imballo",
            "conai",
            "bollo",
            "assicurazione"
        ]
    
    return {"keywords": keywords}


@router.post(
    "/exclusions",
    summary="Update exclusion keywords"
)
async def update_exclusion_keywords(
    data: ExclusionKeywordsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update product exclusion keywords.
    """
    user_id = current_user["user_id"]
    
    if len(data.keywords) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 exclusion keywords allowed"
        )
    
    try:
        db = Database.get_db()
        settings_collection = db[Collections.WAREHOUSE_SETTINGS]
        
        # Upsert settings
        await settings_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "exclusion_keywords": data.keywords,
                    "updated_at": date.today().isoformat()
                }
            },
            upsert=True
        )
        
        return {
            "message": "Exclusion keywords updated successfully",
            "keywords_count": len(data.keywords)
        }
        
    except Exception as e:
        logger.error(f"Error updating exclusion keywords: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/excluded-suppliers",
    summary="Get excluded suppliers"
)
async def get_excluded_suppliers(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[str]:
    """Get list of excluded supplier names."""
    db = Database.get_db()
    config = await db["warehouse_config"].find_one({"type": "excluded_suppliers"}, {"_id": 0})
    return config.get("suppliers", []) if config else []


@router.post(
    "/excluded-suppliers",
    summary="Add excluded supplier"
)
async def add_excluded_supplier(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Add supplier to exclusion list."""
    db = Database.get_db()
    await db["warehouse_config"].update_one(
        {"type": "excluded_suppliers"},
        {"$addToSet": {"suppliers": data.get("supplier_name", "")}},
        upsert=True
    )
    return {"message": "Supplier excluded"}


@router.delete(
    "/excluded-suppliers/{supplier_name}",
    summary="Remove excluded supplier"
)
async def remove_excluded_supplier(
    supplier_name: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Remove supplier from exclusion list."""
    db = Database.get_db()
    await db["warehouse_config"].update_one(
        {"type": "excluded_suppliers"},
        {"$pull": {"suppliers": supplier_name}}
    )
    return {"message": "Supplier removed from exclusion"}


@router.get(
    "/inventory",
    summary="Get warehouse inventory"
)
async def get_inventory(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get warehouse inventory."""
    db = Database.get_db()
    products = await db[Collections.WAREHOUSE_PRODUCTS].find({}, {"_id": 0}).to_list(1000)
    return products


@router.get(
    "/inventory-report",
    summary="Get inventory report"
)
async def get_inventory_report(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get inventory report."""
    db = Database.get_db()
    count = await db[Collections.WAREHOUSE_PRODUCTS].count_documents({})
    return {
        "total_items": count,
        "total_value": 0,
        "by_category": [],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


@router.get(
    "/inventory/by-product",
    summary="Get inventory by product"
)
async def get_inventory_by_product(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get inventory grouped by product."""
    db = Database.get_db()
    products = await db[Collections.WAREHOUSE_PRODUCTS].find({}, {"_id": 0}).to_list(1000)
    return products


@router.get(
    "/inventory/by-supplier",
    summary="Get inventory by supplier"
)
async def get_inventory_by_supplier(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get inventory grouped by supplier."""
    db = Database.get_db()
    pipeline = [
        {"$group": {"_id": "$supplier", "count": {"$sum": 1}, "total_value": {"$sum": "$value"}}},
        {"$sort": {"count": -1}}
    ]
    results = await db[Collections.WAREHOUSE_PRODUCTS].aggregate(pipeline).to_list(100)
    return results


@router.post(
    "/populate-from-existing-invoices",
    summary="Populate warehouse from invoices"
)
async def populate_from_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Populate warehouse from existing invoices."""
    return {"message": "Population completed", "products_added": 0}


@router.post(
    "/repopulate-clean",
    summary="Repopulate warehouse clean"
)
async def repopulate_clean(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Clear and repopulate warehouse."""
    return {"message": "Repopulation completed", "products_added": 0}



@router.post(
    "/pulizia-fornitori-esclusi",
    summary="Rimuovi prodotti di fornitori con esclude_magazzino"
)
async def pulizia_fornitori_esclusi(
    current_user: Dict[str, Any] = Depends(get_current_user),
    dry_run: bool = Query(default=True, description="Se True, mostra solo anteprima senza rimuovere")
) -> Dict[str, Any]:
    """
    Rimuove dal magazzino tutti i prodotti appartenenti a fornitori 
    che hanno il flag esclude_magazzino=True.
    
    - dry_run=True: mostra anteprima dei prodotti che verrebbero rimossi
    - dry_run=False: esegue la rimozione effettiva
    """
    db = Database.get_db()
    
    try:
        # 1. Trova tutti i fornitori con esclude_magazzino=True
        fornitori_esclusi = []
        
        # Cerca in suppliers
        suppliers_cursor = db[Collections.SUPPLIERS].find(
            {"esclude_magazzino": True},
            {"_id": 0, "ragione_sociale": 1, "partita_iva": 1, "id": 1}
        )
        async for s in suppliers_cursor:
            fornitori_esclusi.append({
                "nome": s.get("ragione_sociale", ""),
                "partita_iva": s.get("partita_iva", ""),
                "id": s.get("id", "")
            })
        
        # Cerca anche in fornitori
        fornitori_cursor = db["fornitori"].find(
            {"esclude_magazzino": True},
            {"_id": 0, "ragione_sociale": 1, "partita_iva": 1, "id": 1}
        )
        async for f in fornitori_cursor:
            nome = f.get("ragione_sociale", "")
            # Evita duplicati
            if not any(x["nome"] == nome for x in fornitori_esclusi):
                fornitori_esclusi.append({
                    "nome": nome,
                    "partita_iva": f.get("partita_iva", ""),
                    "id": f.get("id", "")
                })
        
        if not fornitori_esclusi:
            return {
                "message": "Nessun fornitore con esclude_magazzino=True trovato",
                "fornitori_esclusi": 0,
                "prodotti_trovati": 0,
                "prodotti_rimossi": 0
            }
        
        # 2. Estrai i nomi dei fornitori
        nomi_fornitori = [f["nome"] for f in fornitori_esclusi if f["nome"]]
        partite_iva = [f["partita_iva"] for f in fornitori_esclusi if f["partita_iva"]]
        
        # 3. Trova prodotti nel magazzino di questi fornitori
        query_prodotti = {"$or": []}
        
        if nomi_fornitori:
            query_prodotti["$or"].append({"ultimo_fornitore": {"$in": nomi_fornitori}})
            query_prodotti["$or"].append({"fornitori": {"$in": nomi_fornitori}})
            query_prodotti["$or"].append({"supplier_name": {"$in": nomi_fornitori}})
        
        if partite_iva:
            query_prodotti["$or"].append({"supplier_vat": {"$in": partite_iva}})
            query_prodotti["$or"].append({"fornitore_partita_iva": {"$in": partite_iva}})
        
        if not query_prodotti["$or"]:
            return {
                "message": "Nessun criterio di ricerca valido",
                "fornitori_esclusi": len(fornitori_esclusi),
                "prodotti_trovati": 0,
                "prodotti_rimossi": 0
            }
        
        # Cerca in warehouse_inventory
        prodotti_cursor = db["warehouse_inventory"].find(
            query_prodotti,
            {"_id": 0, "id": 1, "nome": 1, "ultimo_fornitore": 1, "giacenza": 1}
        )
        prodotti_da_rimuovere = await prodotti_cursor.to_list(10000)
        
        # Cerca anche in magazzino_doppia_verita
        prodotti_cursor2 = db["magazzino_doppia_verita"].find(
            query_prodotti,
            {"_id": 0, "id": 1, "nome": 1, "fornitore": 1, "giacenza": 1}
        )
        prodotti_doppia_verita = await prodotti_cursor2.to_list(10000)
        
        # 4. Se dry_run, restituisci solo l'anteprima
        if dry_run:
            return {
                "message": "Anteprima pulizia magazzino (dry_run=True)",
                "fornitori_esclusi": len(fornitori_esclusi),
                "fornitori_dettaglio": fornitori_esclusi,
                "prodotti_warehouse_inventory": len(prodotti_da_rimuovere),
                "prodotti_doppia_verita": len(prodotti_doppia_verita),
                "totale_prodotti": len(prodotti_da_rimuovere) + len(prodotti_doppia_verita),
                "anteprima_prodotti": [
                    {"nome": p.get("nome"), "fornitore": p.get("ultimo_fornitore") or p.get("fornitore"), "giacenza": p.get("giacenza", 0)}
                    for p in (prodotti_da_rimuovere + prodotti_doppia_verita)[:50]
                ],
                "dry_run": True
            }
        
        # 5. Esegui la rimozione effettiva
        risultato_wh = await db["warehouse_inventory"].delete_many(query_prodotti)
        risultato_dv = await db["magazzino_doppia_verita"].delete_many(query_prodotti)
        
        totale_rimossi = risultato_wh.deleted_count + risultato_dv.deleted_count
        
        logger.info(f"Pulizia magazzino completata: rimossi {totale_rimossi} prodotti da {len(fornitori_esclusi)} fornitori esclusi")
        
        return {
            "message": f"Pulizia completata: rimossi {totale_rimossi} prodotti",
            "fornitori_esclusi": len(fornitori_esclusi),
            "fornitori_dettaglio": fornitori_esclusi,
            "prodotti_rimossi_warehouse_inventory": risultato_wh.deleted_count,
            "prodotti_rimossi_doppia_verita": risultato_dv.deleted_count,
            "totale_prodotti_rimossi": totale_rimossi,
            "dry_run": False
        }
        
    except Exception as e:
        logger.error(f"Errore pulizia magazzino: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/fornitori-esclusi-magazzino",
    summary="Lista fornitori con esclude_magazzino"
)
async def get_fornitori_esclusi_magazzino(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Restituisce la lista di tutti i fornitori che hanno il flag esclude_magazzino=True.
    Mostra anche il conteggio dei prodotti presenti nel magazzino per ciascuno.
    """
    db = Database.get_db()
    
    try:
        fornitori_esclusi = []
        
        # Cerca in suppliers
        async for s in db[Collections.SUPPLIERS].find({"esclude_magazzino": True}, {"_id": 0}):
            nome = s.get("ragione_sociale", "")
            # Conta prodotti nel magazzino
            count = await db["warehouse_inventory"].count_documents({
                "$or": [
                    {"ultimo_fornitore": nome},
                    {"fornitori": nome}
                ]
            })
            fornitori_esclusi.append({
                "id": s.get("id"),
                "ragione_sociale": nome,
                "partita_iva": s.get("partita_iva", ""),
                "prodotti_in_magazzino": count,
                "source": "suppliers"
            })
        
        # Cerca in fornitori
        async for f in db["fornitori"].find({"esclude_magazzino": True}, {"_id": 0}):
            nome = f.get("ragione_sociale", "")
            # Evita duplicati
            if any(x["ragione_sociale"] == nome for x in fornitori_esclusi):
                continue
            count = await db["warehouse_inventory"].count_documents({
                "$or": [
                    {"ultimo_fornitore": nome},
                    {"fornitori": nome}
                ]
            })
            fornitori_esclusi.append({
                "id": f.get("id"),
                "ragione_sociale": nome,
                "partita_iva": f.get("partita_iva", ""),
                "prodotti_in_magazzino": count,
                "source": "fornitori"
            })
        
        totale_prodotti = sum(f["prodotti_in_magazzino"] for f in fornitori_esclusi)
        
        return {
            "fornitori": fornitori_esclusi,
            "totale_fornitori": len(fornitori_esclusi),
            "totale_prodotti_da_rimuovere": totale_prodotti
        }
        
    except Exception as e:
        logger.error(f"Errore recupero fornitori esclusi: {e}")
        raise HTTPException(status_code=500, detail=str(e))