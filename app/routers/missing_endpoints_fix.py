"""
ENDPOINT MANCANTI - Fix errori 404
===================================

Questi endpoint sono chiamati dal frontend ma mancavano nel backend.

Autore: Fix Automatico
Data: 13 Febbraio 2026
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint per monitoraggio sistema.
    """
    db = Database.get_db()
    
    # Verifica connessione database
    db_status = "connected"
    try:
        await db.command("ping")
    except:
        db_status = "disconnected"
    
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "version": "2.0.0"
    }


# =============================================================================
# ORDINI FORNITORI
# =============================================================================

@router.get("/ordini-fornitori")
@handle_errors
async def get_ordini_fornitori(
    stato: str = None,
    fornitore_id: str = None
) -> Dict[str, Any]:
    """
    Lista ordini ai fornitori.
    """
    db = Database.get_db()
    
    query = {}
    if stato:
        query["stato"] = stato
    if fornitore_id:
        query["fornitore_id"] = fornitore_id
    
    ordini = await db.ordini_fornitori.find(query).sort("data_ordine", -1).to_list(100)
    
    for o in ordini:
        o["_id"] = str(o["_id"])
    
    return {
        "success": True,
        "count": len(ordini),
        "ordini": ordini
    }


@router.post("/ordini-fornitori")
@handle_errors
async def create_ordine_fornitore(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea nuovo ordine fornitore.
    """
    db = Database.get_db()
    
    ordine = {
        **data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stato": "bozza"
    }
    
    result = await db.ordini_fornitori.insert_one(ordine)
    
    return {
        "success": True,
        "id": str(result.inserted_id),
        "message": "Ordine creato"
    }
