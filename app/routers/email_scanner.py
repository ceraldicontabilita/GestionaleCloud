"""
Router Scanner Email Completo - Scansiona tutta la posta.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging

from app.services.email_scanner_completo import (
    get_cartelle_da_scansionare,
    scansiona_tutte_cartelle,
    associa_documenti_a_verbali,
    get_statistiche_documenti
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email-scanner", tags=["Email Scanner"])


@router.get("/cartelle")
async def lista_cartelle() -> Dict[str, Any]:
    """
    Lista tutte le cartelle email classificate per tipo.
    """
    cartelle = await get_cartelle_da_scansionare()
    
    totale = sum(len(v) for v in cartelle.values())
    
    return {
        "totale_cartelle": totale,
        "per_tipo": {k: len(v) for k, v in cartelle.items()},
        "dettaglio": {k: v[:20] for k, v in cartelle.items()}  # Prime 20 per tipo
    }


@router.post("/scansiona")
async def avvia_scansione(
    tipi: List[str] = None,
    max_cartelle: int = 50,
    max_email: int = 5
) -> Dict[str, Any]:
    """
    Avvia scansione completa delle cartelle email.
    
    Args:
        tipi: Tipi di cartelle da scansionare (default: verbali, esattoriali, f24)
        max_cartelle: Numero massimo di cartelle per tipo
        max_email: Numero massimo di email per cartella
    """
    try:
        risultato = await scansiona_tutte_cartelle(
            tipi=tipi,
            max_cartelle=max_cartelle,
            max_email_per_cartella=max_email
        )
        
        return {
            "success": True,
            "message": f"Scansione completata: {risultato['salvati']} nuovi documenti",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore scansione: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/associa")
async def associa_documenti() -> Dict[str, Any]:
    """
    Associa i documenti email scaricati ai verbali/fatture nel database.
    """
    try:
        risultato = await associa_documenti_a_verbali()
        
        return {
            "success": True,
            "message": f"Associati {risultato['associazioni_create']} documenti",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore associazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistiche")
async def statistiche() -> Dict[str, Any]:
    """
    Statistiche complete dei documenti email scaricati.
    """
    return await get_statistiche_documenti()


@router.post("/scansiona-e-associa")
async def scansiona_e_associa(
    tipi: List[str] = None,
    max_cartelle: int = 100,
    max_email: int = 10
) -> Dict[str, Any]:
    """
    Esegue scansione completa E associazione in un'unica operazione.
    
    Questo è l'endpoint principale da usare.
    """
    try:
        # 1. Scansiona
        scan_result = await scansiona_tutte_cartelle(
            tipi=tipi or ["verbale_noleggio", "esattoriale", "esattoriale_regionale", "f24_tributi"],
            max_cartelle=max_cartelle,
            max_email_per_cartella=max_email
        )
        
        # 2. Associa
        assoc_result = await associa_documenti_a_verbali()
        
        return {
            "success": True,
            "scansione": {
                "cartelle_analizzate": scan_result["cartelle_totali"],
                "documenti_trovati": scan_result["documenti_totali"],
                "nuovi_salvati": scan_result["salvati"],
                "duplicati_saltati": scan_result["duplicati"]
            },
            "associazione": assoc_result,
            "dettaglio": scan_result.get("dettaglio_per_tipo", {})
        }
        
    except Exception as e:
        logger.error(f"Errore scansione e associazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))
