"""
Router ingest corrispettivi RT (XML) da Google Drive.

Endpoint (montati sotto /api/corrispettivi):
  GET  /api/corrispettivi/drive/status  -> stato configurazione + ultimo sync
  POST /api/corrispettivi/drive/sync    -> esegue subito un ciclo di import

Il job schedulato (ogni ora) chiama la stessa `drive_corrispettivi_ingest.sync`.
"""
from typing import Dict, Any

from fastapi import APIRouter

from app.database import Database
from app.services import drive_corrispettivi_ingest

router = APIRouter()


@router.get("/drive/status")
async def drive_status() -> Dict[str, Any]:
    """Stato dell'ingest corrispettivi da Drive (configurato?, cartella, ultimo sync)."""
    db = Database.get_db()
    return await drive_corrispettivi_ingest.get_status(db)


@router.post("/drive/sync")
async def drive_sync() -> Dict[str, Any]:
    """Avvia l'import dalla cartella Drive in background e risponde subito.

    Lo stato si segue con polling su /drive/status (campo sync_running).
    """
    db = Database.get_db()
    if not drive_corrispettivi_ingest.is_configured():
        return await drive_corrispettivi_ingest.sync(db)  # ritorna il not_configured
    if not drive_corrispettivi_ingest.start_background_sync(db):
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    return {"status": "started", "message": "Sincronizzazione avviata"}


@router.post("/drive/quadratura")
async def drive_quadratura() -> Dict[str, Any]:
    """Doppio controllo Elaborate ↔ gestionale per i corrispettivi.

    Ripassa gli XML archiviati in "Elaborate" e recupera i buchi (file
    archiviato senza record nel gestionale). Idempotente, non sposta file.
    Gira anche da sola una volta a settimana.
    """
    db = Database.get_db()
    return await drive_corrispettivi_ingest.verifica_quadratura_elaborate(db)
