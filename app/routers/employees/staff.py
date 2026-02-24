"""Staff router - Staff/Employee management (legacy compatibility)."""
from fastapi import APIRouter, Depends, Path, status, UploadFile, File
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/all",
    summary="Get all staff",
    description="Get list of all staff members"
)
async def get_all_staff(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get all staff members."""
    db = Database.get_db()
    
    # Try staff collection first, fallback to employees
    try:
        staff = await db["staff"].find({}, {"_id": 0}).to_list(500)
        if not staff:
            staff = await db[Collections.EMPLOYEES].find({}, {"_id": 0}).to_list(500)
        return staff
    except Exception:
        return []


@router.get(
    "",
    summary="Get staff",
    description="Get staff with pagination"
)
async def get_staff(
    skip: int = 0,
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get staff with pagination."""
    db = Database.get_db()
    
    try:
        staff = await db["staff"].find(
            {}, {"_id": 0}
        ).skip(skip).limit(limit).to_list(limit)
        return staff
    except Exception:
        return []


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create staff member"
)
async def create_staff(
    staff_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a new staff member."""
    db = Database.get_db()
    
    from uuid import uuid4
    staff_data["id"] = str(uuid4())
    staff_data["created_at"] = datetime.now(timezone.utc)
    
    await db["staff"].insert_one(staff_data.copy())
    
    return {"message": "Staff created", "id": staff_data["id"]}


@router.put(
    "/{staff_id}",
    summary="Update staff member"
)
async def update_staff(
    staff_id: str = Path(...),
    staff_data: Dict[str, Any] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update a staff member."""
    db = Database.get_db()
    
    if staff_data:
        staff_data["updated_at"] = datetime.now(timezone.utc)
        await db["staff"].update_one(
            {"id": staff_id},
            {"$set": staff_data}
        )
    
    return {"message": "Staff updated"}


@router.delete(
    "/{staff_id}",
    summary="Delete staff member"
)
async def delete_staff(
    staff_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a staff member."""
    db = Database.get_db()
    
    await db["staff"].delete_one({"id": staff_id})
    
    return {"message": "Staff deleted"}


@router.post(
    "/import-excel",
    summary="Import staff from Excel"
)
async def import_excel(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Import staff from Excel file."""
    # TODO: Implement Excel import
    return {"message": "Import completed", "imported": 0, "errors": []}


@router.post(
    "/import-pdf-anagrafica",
    summary="Import staff from PDF"
)
async def import_pdf(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Import staff from PDF anagrafica."""
    # TODO: Implement PDF import
    return {"message": "Import completed", "imported": 0, "errors": []}
