"""
Router ingest fatture da Google Drive.

Endpoint (montati sotto /api/fatture):
  GET  /api/fatture/drive/status  -> stato configurazione + ultimo sync
  POST /api/fatture/drive/sync    -> esegue subito un ciclo di import dalla cartella Drive

Il job schedulato (ogni 15 min) chiama la stessa `drive_invoice_ingest.sync`.
"""
from typing import Dict, Any

from fastapi import APIRouter

from app.database import Database
from app.services import drive_invoice_ingest

router = APIRouter()


@router.get("/drive/status")
async def drive_status() -> Dict[str, Any]:
    """Stato dell'ingest Drive (configurato?, cartella, ultimo sync)."""
    db = Database.get_db()
    return await drive_invoice_ingest.get_status(db)


@router.post("/drive/sync")
async def drive_sync() -> Dict[str, Any]:
    """Esegue subito l'import delle fatture XML dalla cartella Drive."""
    db = Database.get_db()
    return await drive_invoice_ingest.sync(db)
