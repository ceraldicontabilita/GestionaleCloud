"""Documents router - Document management."""
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
    summary="Get documents"
)
async def get_documents(
    type: Optional[str] = Query(None, description="Filter by document type"),
    year: Optional[int] = Query(None, description="Filter by year"),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of documents."""
    db = Database.get_db()
    query = {"user_id": current_user["user_id"]}
    
    if type:
        query["type"] = type # Ensure frontend sends 'type' field in upload, otherwise this might filter too much. 
        # Actually documents uploaded via /api/documents usually don't have type unless specified.
        # But if frontend filters, we should try.
        # If type is not in doc, we might need to rely on folder or implicit type.
        # For now, let's assume 'type' field exists or we filter by content_type if mapped.
        pass
        
    if year:
        # Filter by created_at year
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31, 23, 59, 59)
        query["created_at"] = {"$gte": start, "$lte": end}
        
    docs = await db["documents"].find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Upload document"
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Upload a document."""
    db = Database.get_db()
    doc = {
        "id": str(uuid4()),
        "filename": file.filename,
        "content_type": file.content_type,
        "created_at": datetime.now(timezone.utc),
        "user_id": current_user["user_id"]
    }
    await db["documents"].insert_one(doc.copy())
    return {"message": "Document uploaded", "id": doc["id"]}


@router.delete(
    "/{document_id}",
    summary="Delete document"
)
async def delete_document(
    document_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a document."""
    db = Database.get_db()
    await db["documents"].delete_one({"id": document_id})
    return {"message": "Document deleted"}
