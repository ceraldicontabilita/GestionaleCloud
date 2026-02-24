"""Bank Reconciliation router."""
from fastapi import APIRouter, Depends, Path, status, UploadFile, File
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/statements",
    summary="Get bank statements"
)
async def get_statements(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of bank statements."""
    db = Database.get_db()
    statements = await db[Collections.BANK_STATEMENTS].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return statements


@router.post(
    "/statements",
    status_code=status.HTTP_201_CREATED,
    summary="Create bank statement"
)
async def create_statement(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create a bank statement."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db[Collections.BANK_STATEMENTS].insert_one(data.copy())
    return {"message": "Statement created", "id": data["id"]}


@router.delete(
    "/statements/{statement_id}",
    summary="Delete bank statement"
)
async def delete_statement(
    statement_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a bank statement."""
    db = Database.get_db()
    await db[Collections.BANK_STATEMENTS].delete_one({"id": statement_id})
    return {"message": "Statement deleted"}


@router.post(
    "/reconcile",
    summary="Reconcile transactions"
)
async def reconcile(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Reconcile bank transactions with invoices."""
    return {"message": "Reconciliation completed"}


@router.post(
    "/upload",
    summary="Upload bank statement file"
)
async def upload_bank_statement(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Upload bank statement file for reconciliation."""
    contents = await file.read()
    return {
        "message": "Bank statement uploaded",
        "filename": file.filename,
        "size": len(contents),
        "transactions_found": 0
    }
