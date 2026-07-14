"""
Router ingest cedolini paga da Google Drive.

Endpoint (montati sotto /api/cedolini):
  POST /api/cedolini/drive/sync    -> esegue subito un ciclo di import dalla cartella Drive

Il job schedulato (ogni ora) chiama la stessa `drive_cedolini_ingest.sync`.

GET /drive/status, GET /{cedolino_id}/pdf, POST /drive/quadratura: smontati
(audit 14/07/2026, piano residuo op.3/op.7) — zero chiamanti verificati.
drive_cedolini_ingest.verifica_quadratura_elaborate resta viva: chiamata
direttamente dallo scheduler (job settimanale).
"""
from typing import Dict, Any

from fastapi import APIRouter

from app.database import Database
from app.services import drive_cedolini_ingest

router = APIRouter()


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
