"""
Router ingest fatture da Google Drive.

Endpoint (montati sotto /api/fatture):
  GET  /api/fatture/drive/status  -> stato configurazione + ultimo sync
  POST /api/fatture/drive/sync    -> esegue subito un ciclo di import dalla cartella Drive

Il job schedulato (ogni 15 min) chiama la stessa `drive_invoice_ingest.sync`.
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends

from app.database import Database
from app.services import drive_invoice_ingest
from app.utils.ruoli import richiedi_admin

router = APIRouter()


@router.get("/drive/status")
async def drive_status() -> Dict[str, Any]:
    """Stato dell'ingest Drive (configurato?, cartella, ultimo sync)."""
    db = Database.get_db()
    return await drive_invoice_ingest.get_status(db)


@router.post("/drive/sync")
async def drive_sync() -> Dict[str, Any]:
    """Avvia l'import dalla cartella Drive in background e risponde subito.

    Con molti file l'elaborazione può superare il timeout HTTP del browser:
    il lavoro gira in background e la card Admin segue l'avanzamento
    facendo polling su /drive/status (campo sync_running).
    """
    db = Database.get_db()
    if not drive_invoice_ingest.is_configured():
        return await drive_invoice_ingest.sync(db)  # ritorna il not_configured
    if not drive_invoice_ingest.start_background_sync(db):
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    return {"status": "started", "message": "Sincronizzazione avviata"}


@router.post("/drive/quadratura")
async def drive_quadratura() -> Dict[str, Any]:
    """Doppio controllo Elaborate ↔ gestionale.

    Ripassa TUTTI i file archiviati nella sottocartella Drive "Elaborate" e
    verifica che ognuno abbia la sua fattura nel gestionale. I buchi (file
    spostato in archivio ma record mai creato) vengono importati subito:
    l'operazione è idempotente, non può creare doppioni e non sposta file.
    Gira anche da sola una volta a settimana; da qui la lanci quando vuoi.
    """
    db = Database.get_db()
    return await drive_invoice_ingest.verifica_quadratura_elaborate(db)


@router.post("/drive/ricostruzione")
async def drive_ricostruzione(
    reset: bool = False,
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Avvia un lotto riprendibile senza spostare originali Drive."""
    db = Database.get_db()
    if not drive_invoice_ingest.is_configured():
        return await drive_invoice_ingest.ricostruisci_archivio_drive_lotto(
            db, reset=reset,
        )
    if not drive_invoice_ingest.start_background_rebuild(db, reset=reset):
        return {"status": "running", "message": "Ricostruzione gia' in corso"}
    return {"status": "started", "message": "Lotto ricostruzione Drive avviato"}


@router.post("/drive/ricostruzione/lotto")
async def drive_ricostruzione_lotto(
    reset: bool = False,
    batch_size: int = 10,
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Esegue e restituisce un solo lotto; la chiamata seguente riprende."""
    db = Database.get_db()
    return await drive_invoice_ingest.ricostruisci_archivio_drive_lotto(
        db, batch_size=batch_size, reset=reset,
    )
