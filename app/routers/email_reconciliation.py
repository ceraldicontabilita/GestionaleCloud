"""
Router API per Riconciliazione Email ↔ Gestionale

Endpoint per:
- Costruzione indice documenti
- Scansione e riconciliazione posta
- Statistiche e monitoraggio
- Download PDF archiviati
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Response

from app.database import Database
from app.services.email_reconciliation import (
    costruisci_indice_documenti,
    scansiona_tutta_posta_e_riconcilia,
    cerca_match_in_indice,
    get_statistiche_indice,
    COLLECTION_INDICE,
    COLLECTION_PDF_ARCHIVE,
    COLLECTION_MATCH_LOG
)

router = APIRouter(prefix="/api/riconciliazione", tags=["Riconciliazione Email"])
logger = logging.getLogger(__name__)


@router.post("/costruisci-indice")
async def costruisci_indice_endpoint() -> Dict[str, Any]:
    """
    Costruisce/aggiorna l'indice master di tutti i documenti del gestionale.
    
    L'indice include:
    - Fatture ricevute
    - Verbali noleggio
    - Contratti noleggio
    - Costi noleggio (bolli, riparazioni, etc.)
    - F24
    
    Ogni documento viene indicizzato con chiavi di ricerca per il matching.
    """
    try:
        risultato = await costruisci_indice_documenti()
        return {
            "success": True,
            "message": "Indice costruito con successo",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore costruzione indice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scansiona-posta")
async def scansiona_posta_endpoint(
    limit_per_cartella: int = Query(default=50, description="Max email per cartella")
) -> Dict[str, Any]:
    """
    Scansiona TUTTA la posta elettronica e riconcilia con il gestionale.
    
    Per ogni email:
    1. Estrae soggetto, corpo e allegati
    2. Cerca pattern (numeri fattura, verbali, targhe, importi)
    3. Confronta con l'indice documenti
    4. Se trova match, associa i PDF al documento
    
    ATTENZIONE: Operazione lunga, può richiedere diversi minuti.
    """
    try:
        # Prima ricostruisci l'indice per avere dati aggiornati
        await costruisci_indice_documenti()
        
        # Poi scansiona la posta
        risultato = await scansiona_tutta_posta_e_riconcilia(limit_per_cartella)
        
        return {
            "success": True,
            "message": "Scansione e riconciliazione completata",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore scansione posta: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistiche")
async def get_statistiche_endpoint() -> Dict[str, Any]:
    """
    Restituisce statistiche sull'indice documenti e le riconciliazioni.
    """
    try:
        return await get_statistiche_indice()
    except Exception as e:
        logger.error(f"Errore statistiche: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cerca")
async def cerca_match_endpoint(
    testo: str = Query(..., description="Testo da cercare nell'indice")
) -> Dict[str, Any]:
    """
    Cerca match tra un testo e l'indice documenti.
    
    Utile per testare il matching prima di scansionare tutta la posta.
    """
    try:
        matches = await cerca_match_in_indice(testo)
        return {
            "testo_cercato": testo[:200],
            "matches_trovati": len(matches),
            "matches": matches
        }
    except Exception as e:
        logger.error(f"Errore ricerca: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documenti-senza-pdf")
async def get_documenti_senza_pdf(
    tipo: Optional[str] = Query(None, description="Filtra per tipo documento"),
    limit: int = Query(default=100)
) -> Dict[str, Any]:
    """
    Restituisce i documenti dell'indice che non hanno PDF associati.
    
    Utile per identificare documenti da cercare nella posta.
    """
    db = Database.get_db()
    
    query = {"$or": [
        {"pdf_associati": {"$exists": False}},
        {"pdf_associati": []},
        {"pdf_associati": None}
    ]}
    
    if tipo:
        query["tipo"] = tipo
    
    cursor = db[COLLECTION_INDICE].find(query, {"_id": 0}).limit(limit)
    documenti = await cursor.to_list(limit)
    
    totale = await db[COLLECTION_INDICE].count_documents(query)
    
    return {
        "documenti": documenti,
        "count": len(documenti),
        "totale_senza_pdf": totale
    }


@router.get("/pdf/{hash_pdf}")
async def get_pdf_archiviato(hash_pdf: str) -> Response:
    """
    Restituisce un PDF archiviato dato il suo hash.
    """
    db = Database.get_db()
    
    pdf = await db[COLLECTION_PDF_ARCHIVE].find_one({"hash": hash_pdf})
    
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF non trovato")
    
    content_base64 = pdf.get("content_base64")
    if not content_base64:
        raise HTTPException(status_code=404, detail="Contenuto PDF non disponibile")
    
    import base64
    content = base64.b64decode(content_base64)
    
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{pdf.get('filename', 'documento.pdf')}\""
        }
    )


@router.get("/log-riconciliazioni")
async def get_log_riconciliazioni(
    limit: int = Query(default=50),
    solo_con_match: bool = Query(default=False)
) -> Dict[str, Any]:
    """
    Restituisce il log delle riconciliazioni effettuate.
    """
    db = Database.get_db()
    
    query = {}
    if solo_con_match:
        query["matches_trovati"] = {"$gt": 0}
    
    cursor = db[COLLECTION_MATCH_LOG].find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(limit)
    
    return {
        "logs": logs,
        "count": len(logs)
    }


@router.delete("/reset-indice")
async def reset_indice_endpoint() -> Dict[str, Any]:
    """
    Resetta l'indice documenti (per debug/manutenzione).
    
    ATTENZIONE: Elimina tutto l'indice, sarà necessario ricostruirlo.
    """
    db = Database.get_db()
    
    result = await db[COLLECTION_INDICE].delete_many({})
    
    return {
        "success": True,
        "documenti_eliminati": result.deleted_count
    }
