"""
Router ingest cedolini paga da Google Drive.

Endpoint (montati sotto /api/cedolini):
  GET  /api/cedolini/drive/status  -> stato configurazione + ultimo sync
  POST /api/cedolini/drive/sync    -> esegue subito un ciclo di import dalla cartella Drive

Il job schedulato (ogni ora) chiama la stessa `drive_cedolini_ingest.sync`.
"""
from typing import Dict, Any

from fastapi import APIRouter

from app.database import Database
from app.services import drive_cedolini_ingest

router = APIRouter()


@router.get("/drive/status")
async def drive_status() -> Dict[str, Any]:
    """Stato dell'ingest cedolini da Drive (configurato?, cartella, ultimo sync)."""
    db = Database.get_db()
    return await drive_cedolini_ingest.get_status(db)


@router.post("/drive/sync")
async def drive_sync() -> Dict[str, Any]:
    """Avvia l'import dalla cartella Drive in background e risponde subito.

    Con molti file l'elaborazione può superare il timeout HTTP del browser:
    il lavoro gira in background e lo stato si segue facendo polling su
    /drive/status (campo sync_running).
    """
    db = Database.get_db()
    if not drive_cedolini_ingest.is_configured():
        return await drive_cedolini_ingest.sync(db)  # ritorna il not_configured
    if not drive_cedolini_ingest.start_background_sync(db):
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    return {"status": "started", "message": "Sincronizzazione avviata"}


@router.post("/drive/quadratura")
async def drive_quadratura() -> Dict[str, Any]:
    """Doppio controllo Elaborate ↔ gestionale per i cedolini.

    Ripassa i PDF archiviati in "Elaborate" e recupera i buchi (file
    archiviato senza documento nel gestionale). Idempotente, non sposta
    file. Gira anche da sola una volta a settimana.
    """
    db = Database.get_db()
    return await drive_cedolini_ingest.verifica_quadratura_elaborate(db)
