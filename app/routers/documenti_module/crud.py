"""
Documenti Module - CRUD documenti e download email.
"""
from fastapi import HTTPException, BackgroundTasks
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import os
import uuid
import asyncio

from app.database import Database
from app.services.email_document_downloader import (
    download_documents_from_email
)
from .common import COL_DOCUMENTS, CATEGORIES, logger

# Store per task download
_download_tasks: Dict[str, Dict] = {}
_email_operation_lock = asyncio.Lock()
_current_operation: Optional[str] = None


async def lista_documenti(
    categoria: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> Dict[str, Any]:
    """Lista documenti scaricati dalle email."""
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["category"] = categoria
    if status:
        query["status"] = status
    
    documents = await db[COL_DOCUMENTS].find(
        query, {"_id": 0}
    ).sort("downloaded_at", -1).skip(skip).limit(limit).to_list(limit)
    
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    by_category = {doc["_id"]: doc["count"] async for doc in db[COL_DOCUMENTS].aggregate(pipeline)}
    
    pipeline_status = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    by_status = {doc["_id"]: doc["count"] async for doc in db[COL_DOCUMENTS].aggregate(pipeline_status)}
    
    total = await db[COL_DOCUMENTS].count_documents(query)
    
    return {
        "documents": documents,
        "total": total,
        "by_category": by_category,
        "by_status": by_status,
        "categories": CATEGORIES
    }


async def get_lock_status() -> Dict[str, Any]:
    """Stato del lock per operazioni email."""
    return {
        "locked": _email_operation_lock.locked(),
        "operation": _current_operation,
        "message": f"Operazione in corso: {_current_operation}" if _current_operation else "Nessuna operazione in corso"
    }


async def _execute_email_download(task_id: str, db, email_user: str, email_password: str, 
                                   giorni: int, folder: str, keywords: List[str]):
    """Esegue download in background."""
    global _current_operation
    
    try:
        async with _email_operation_lock:
            _current_operation = "download_documenti_email"
            _download_tasks[task_id]["status"] = "in_progress"
            _download_tasks[task_id]["message"] = "Connessione al server email..."
            
            result = await download_documents_from_email(
                db=db,
                email_user=email_user,
                email_password=email_password,
                since_days=giorni,
                folder=folder,
                search_keywords=keywords if keywords else None
            )
            
            _download_tasks[task_id]["status"] = "completed"
            _download_tasks[task_id]["result"] = result
            _download_tasks[task_id]["message"] = "Download completato!"
            _download_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            _current_operation = None
        
    except Exception as e:
        logger.error(f"Errore download task {task_id}: {e}")
        _download_tasks[task_id]["status"] = "error"
        _download_tasks[task_id]["error"] = str(e)
        _download_tasks[task_id]["message"] = f"Errore: {str(e)}"
        _current_operation = None


async def scarica_documenti_email(
    background_tasks: BackgroundTasks,
    giorni: int = 30,
    folder: str = "INBOX",
    parole_chiave: Optional[str] = None,
    background: bool = False
) -> Dict[str, Any]:
    """Scarica documenti allegati dalle email."""
    email_user = os.environ.get("ARUBA_EMAIL_USER", "")
    email_password = os.environ.get("ARUBA_EMAIL_PASSWORD", "")
    
    if not email_user or not email_password:
        raise HTTPException(status_code=400, detail="Credenziali email non configurate")
    
    keywords = [k.strip() for k in parole_chiave.split(",")] if parole_chiave else []
    
    if background:
        if _email_operation_lock.locked():
            return {
                "success": False,
                "message": f"Operazione già in corso: {_current_operation}",
                "operation_in_progress": _current_operation
            }
        
        task_id = str(uuid.uuid4())
        _download_tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "message": "Task in coda...",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "params": {"giorni": giorni, "folder": folder, "keywords": keywords}
        }
        
        db = Database.get_db()
        background_tasks.add_task(
            _execute_email_download, task_id, db, email_user, email_password, giorni, folder, keywords
        )
        
        return {
            "success": True,
            "background": True,
            "task_id": task_id,
            "message": "Download avviato in background"
        }
    
    # Esecuzione sincrona
    if _email_operation_lock.locked():
        return {
            "success": False,
            "message": f"Operazione già in corso: {_current_operation}"
        }
    
    db = Database.get_db()
    result = await download_documents_from_email(
        db=db,
        email_user=email_user,
        email_password=email_password,
        since_days=giorni,
        folder=folder,
        search_keywords=keywords if keywords else None
    )
    
    return {"success": True, "result": result}


async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Stato di un task di download."""
    if task_id not in _download_tasks:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return _download_tasks[task_id]


async def get_categorie() -> Dict[str, Any]:
    """Lista categorie documenti."""
    db = Database.get_db()
    
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    stats = {doc["_id"]: doc["count"] async for doc in db[COL_DOCUMENTS].aggregate(pipeline)}
    
    return {
        "categories": CATEGORIES,
        "stats": stats
    }


async def get_documento(doc_id: str) -> Dict[str, Any]:
    """Dettaglio singolo documento."""
    db = Database.get_db()
    
    doc = await db[COL_DOCUMENTS].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    return doc


async def download_documento(doc_id: str):
    """
    Download file documento da MongoDB (architettura MongoDB-only).
    Restituisce il contenuto PDF decodificato da Base64.
    """
    from fastapi.responses import Response
    import base64
    
    db = Database.get_db()
    
    doc = await db[COL_DOCUMENTS].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile in MongoDB")
    
    content = base64.b64decode(pdf_data)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.get("filename", "documento.pdf")}"'}
    )


async def processa_documento(
    doc_id: str,
    categoria_destinazione: Optional[str] = None,
    azione: str = "processa"
) -> Dict[str, Any]:
    """Processa un documento (cambia categoria, archivia, etc)."""
    db = Database.get_db()
    
    doc = await db[COL_DOCUMENTS].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    update_fields = {
        "status": "processed",
        "processed_at": datetime.now(timezone.utc).isoformat()
    }
    
    if categoria_destinazione:
        update_fields["category"] = categoria_destinazione
    
    await db[COL_DOCUMENTS].update_one({"id": doc_id}, {"$set": update_fields})
    
    return {"success": True, "doc_id": doc_id, "azione": azione}


async def cambia_categoria_documento(
    doc_id: str,
    nuova_categoria: str
) -> Dict[str, Any]:
    """Cambia categoria di un documento."""
    db = Database.get_db()
    
    doc = await db[COL_DOCUMENTS].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    if nuova_categoria not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoria non valida. Valide: {list(CATEGORIES.keys())}")
    
    await db[COL_DOCUMENTS].update_one(
        {"id": doc_id},
        {"$set": {
            "category": nuova_categoria,
            "category_label": CATEGORIES[nuova_categoria],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "doc_id": doc_id, "nuova_categoria": nuova_categoria}


async def elimina_documento(doc_id: str) -> Dict[str, Any]:
    """
    Elimina un documento.
    Architettura MongoDB-only: elimina solo dal database.
    """
    db = Database.get_db()
    
    doc = await db[COL_DOCUMENTS].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    # Architettura MongoDB-only: elimina solo dal database
    await db[COL_DOCUMENTS].delete_one({"id": doc_id})
    
    return {"success": True, "deleted": doc_id}


async def elimina_documenti_processati() -> Dict[str, Any]:
    """
    Elimina tutti i documenti processati.
    Architettura MongoDB-only: elimina solo dal database.
    """
    db = Database.get_db()
    
    count_before = await db[COL_DOCUMENTS].count_documents({"status": "processed"})
    
    result = await db[COL_DOCUMENTS].delete_many({"status": "processed"})
    
    return {
        "success": True,
        "documenti_eliminati": result.deleted_count
    }


async def statistiche_documenti() -> Dict[str, Any]:
    """Statistiche documenti."""
    db = Database.get_db()
    
    totale = await db[COL_DOCUMENTS].count_documents({})
    nuovi = await db[COL_DOCUMENTS].count_documents({"status": "nuovo"})
    processati = await db[COL_DOCUMENTS].count_documents({"status": "processed"})
    errori = await db[COL_DOCUMENTS].count_documents({"status": "errore"})
    
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "size": {"$sum": "$size_bytes"}}}
    ]
    by_category = await db[COL_DOCUMENTS].aggregate(pipeline).to_list(100)
    
    return {
        "totale": totale,
        "nuovi": nuovi,
        "processati": processati,
        "errori": errori,
        "by_category": {c["_id"]: {"count": c["count"], "size_mb": round(c.get("size", 0) / 1024 / 1024, 2)} for c in by_category if c["_id"]}
    }
