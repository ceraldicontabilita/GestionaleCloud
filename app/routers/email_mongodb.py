"""
Router per download email e salvataggio su MongoDB Atlas.
TUTTO su MongoDB, NIENTE filesystem.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Dict, Any
import logging

from app.database import Database
from app.services.email_to_mongodb import (
    download_and_save_emails,
    get_email_documents_stats
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email-mongodb", tags=["Email MongoDB"])


@router.post("/sync")
async def sync_emails(
    background_tasks: BackgroundTasks,
    days_back: int = Query(default=30, description="Giorni indietro"),
    folder: str = Query(default="INBOX", description="Cartella IMAP")
) -> Dict[str, Any]:
    """
    Scarica email con PDF e salva TUTTO su MongoDB Atlas.
    """
    db = Database.get_db()
    result = await download_and_save_emails(db, days_back, folder)
    return result


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Statistiche documenti email in MongoDB."""
    db = Database.get_db()
    return await get_email_documents_stats(db)


@router.get("/documents")
async def list_documents(
    category: str = Query(default=None),
    processed: bool = Query(default=None),
    limit: int = Query(default=50, le=200)
) -> Dict[str, Any]:
    """Lista documenti email salvati in MongoDB."""
    db = Database.get_db()
    
    query = {}
    if category:
        query["category"] = category
    if processed is not None:
        query["processed"] = processed
    
    cursor = db["email_documents"].find(
        query,
        {"_id": 0, "pdf_data": 0}  # Escludi PDF pesante dalla lista
    ).sort("created_at", -1).limit(limit)
    
    docs = await cursor.to_list(limit)
    
    return {
        "count": len(docs),
        "documents": docs
    }


@router.get("/pdf/{doc_id}")
async def get_pdf(doc_id: str):
    """Scarica PDF dal MongoDB."""
    from fastapi.responses import Response
    import base64
    
    db = Database.get_db()
    doc = await db["email_documents"].find_one({"id": doc_id})
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile")
    
    pdf_bytes = base64.b64decode(pdf_data)
    filename = doc.get("filename", "documento.pdf")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
