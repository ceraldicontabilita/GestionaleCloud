"""
Router ingest cedolini paga da Google Drive.

Endpoint (montati sotto /api/cedolini):
  GET  /api/cedolini/drive/status  -> stato configurazione + ultimo sync
  POST /api/cedolini/drive/sync    -> esegue subito un ciclo di import dalla cartella Drive

Il job schedulato (ogni ora) chiama la stessa `drive_cedolini_ingest.sync`.
"""
import base64
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.database import Database
from app.services import drive_cedolini_ingest

router = APIRouter()


@router.get("/{cedolino_id}/pdf")
async def scarica_cedolino_pdf(cedolino_id: str):
    """Serve il PDF di un cedolino dato il suo ID.

    Il record `cedolini` tiene i DATI estratti; il PDF vive nell'hub
    documentale `documents_inbox` (campo `pdf_data` base64), da cui è arrivato
    (Drive cedolini o allegato email). Cerchiamo il PDF in ordine: nel record
    stesso, poi in documents_inbox per filename."""
    db = Database.get_db()
    ced = await db["cedolini"].find_one({"id": cedolino_id}, {"_id": 0})
    if not ced:
        raise HTTPException(status_code=404, detail="Cedolino non trovato")

    filename = ced.get("filename") or f"cedolino_{cedolino_id}.pdf"
    pdf_b64 = ced.get("pdf_data")

    if not pdf_b64 and ced.get("filename"):
        doc = await db["documents_inbox"].find_one(
            {"filename": ced["filename"], "pdf_data": {"$exists": True}},
            {"_id": 0, "pdf_data": 1},
        )
        if doc:
            pdf_b64 = doc.get("pdf_data")

    if not pdf_b64:
        raise HTTPException(
            status_code=404,
            detail="PDF del cedolino non disponibile (non presente in archivio documenti)",
        )

    try:
        content = base64.b64decode(pdf_b64)
    except Exception:
        raise HTTPException(status_code=500, detail="PDF del cedolino illeggibile")

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
