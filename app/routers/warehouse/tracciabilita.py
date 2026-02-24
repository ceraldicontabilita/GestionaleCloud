"""Tracciabilita router - Product traceability."""
from fastapi import APIRouter, Depends, Path, status, UploadFile, File, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get all traceability records"
)
async def get_tracciabilita(
    categoria: Optional[str] = Query(None, description="Filter by HACCP category"),
    fornitore: Optional[str] = Query(None, description="Filter by supplier"),
    data_da: Optional[str] = Query(None, description="From date"),
    data_a: Optional[str] = Query(None, description="To date"),
    limit: int = Query(500, description="Max records")
) -> List[Dict[str, Any]]:
    """Get all traceability records with optional filters."""
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["categoria_haccp"] = categoria
    if fornitore:
        query["fornitore"] = {"$regex": fornitore, "$options": "i"}
    if data_da:
        query["data_consegna"] = {"$gte": data_da}
    if data_a:
        if "data_consegna" in query:
            query["data_consegna"]["$lte"] = data_a
        else:
            query["data_consegna"] = {"$lte": data_a}
    
    records = await db.tracciabilita.find(query, {"_id": 0}).sort("data_consegna", -1).limit(limit).to_list(limit)
    return records


@router.get(
    "/prodotto",
    summary="Get traceable products"
)
async def get_traceable_products(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of traceable products."""
    db = Database.get_db()
    products = await db["tracciabilita"].find({}, {"_id": 0}).to_list(500)
    return products


@router.post(
    "/prodotto",
    status_code=status.HTTP_201_CREATED,
    summary="Create traceable product"
)
async def create_traceable_product(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a traceable product entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db["tracciabilita"].insert_one(data.copy())
    return {"message": "Product created", "id": data["id"]}


@router.put(
    "/prodotto/{product_id}",
    summary="Update traceable product"
)
async def update_traceable_product(
    product_id: str = Path(...),
    data: Dict[str, Any] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update a traceable product."""
    db = Database.get_db()
    if data:
        data["updated_at"] = datetime.now(timezone.utc)
        await db["tracciabilita"].update_one({"id": product_id}, {"$set": data})
    return {"message": "Product updated"}


@router.delete(
    "/prodotto/{product_id}",
    summary="Delete traceable product"
)
async def delete_traceable_product(
    product_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a traceable product."""
    db = Database.get_db()
    await db["tracciabilita"].delete_one({"id": product_id})
    return {"message": "Product deleted"}


@router.post(
    "/upload-foto",
    summary="Upload product photo"
)
async def upload_photo(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Upload product photo for traceability."""
    # TODO: Implement file storage
    return {"message": "Photo uploaded", "filename": file.filename}
