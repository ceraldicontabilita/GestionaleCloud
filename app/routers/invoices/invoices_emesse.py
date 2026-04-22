"""Invoices Emesse router - Issued invoices."""
from fastapi import APIRouter, Body, Depends, File, Path, UploadFile, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Get issued invoices"
)
async def get_invoices_emesse(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of issued invoices."""
    db = Database.get_db()
    invoices = await db["invoices_emesse"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return invoices


@router.get(
    "/{invoice_id}",
    summary="Get issued invoice"
)
async def get_invoice_emessa(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get a specific issued invoice."""
    db = Database.get_db()
    invoice = await db["invoices_emesse"].find_one({"id": invoice_id}, {"_id": 0})
    return invoice or {}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create issued invoice"
)
async def create_invoice_emessa(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create an issued invoice."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    data["user_id"] = current_user["user_id"]
    await db["invoices_emesse"].insert_one(data.copy())
    return {"message": "Invoice created", "id": data["id"]}


@router.delete(
    "/{invoice_id}",
    summary="Delete issued invoice"
)
async def delete_invoice_emessa(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete an issued invoice."""
    db = Database.get_db()
    await db["invoices_emesse"].delete_one({"id": invoice_id})
    return {"message": "Invoice deleted"}


@router.post(
    "/upload-xml",
    summary="Upload issued invoice XML"
)
async def upload_invoice_xml(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Upload issued invoice XML file."""
    db = Database.get_db()
    contents = await file.read()
    
    from uuid import uuid4
    doc = {
        "id": str(uuid4()),
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(contents),
        "created_at": datetime.now(timezone.utc),
        "user_id": current_user["user_id"],
        "status": "uploaded"
    }
    await db["invoices_emesse"].insert_one(doc.copy())
    
    return {
        "message": "Invoice XML uploaded successfully",
        "id": doc["id"],
        "filename": file.filename
    }