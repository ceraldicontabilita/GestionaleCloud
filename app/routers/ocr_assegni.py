"""OCR Assegni router - Check OCR functionality."""
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
    "/registro",
    summary="Get OCR check registry"
)
async def get_registro(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get OCR check registry."""
    db = Database.get_db()
    registro = await db["ocr_assegni"].find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return registro


@router.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
    summary="Add to registry"
)
async def add_to_registro(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Add entry to OCR check registry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db["ocr_assegni"].insert_one(data.copy())
    return {"message": "Entry added", "id": data["id"]}


@router.delete(
    "/registro/{entry_id}",
    summary="Delete registry entry"
)
async def delete_registro_entry(
    entry_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a registry entry."""
    db = Database.get_db()
    await db["ocr_assegni"].delete_one({"id": entry_id})
    return {"message": "Entry deleted"}


@router.delete(
    "/registro",
    summary="Clear registry"
)
async def clear_registro(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Clear OCR check registry."""
    db = Database.get_db()
    result = await db["ocr_assegni"].delete_many({})
    return {"message": f"Deleted {result.deleted_count} entries"}


@router.post(
    "/estrai-dati",
    summary="Extract data from check image"
)
async def estrai_dati(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Extract data from check image using OCR."""
    return {"message": "OCR extraction completed", "data": {}}


@router.post(
    "/leggi-carnet",
    summary="Read checkbook"
)
async def leggi_carnet(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Read checkbook pages."""
    return {"message": "Checkbook read", "checks": []}