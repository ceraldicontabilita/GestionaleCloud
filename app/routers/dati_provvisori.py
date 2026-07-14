"""
DATI PROVVISORI - Nuova Logica Workflow
========================================

WORKFLOW CORRETTO:
1. Utente sceglie manualmente → CASSA o BANCA
2. Upload XML → Ricontrollo dati (IGNORO metodo pagamento)
3. Upload Estratto Conto → Riconciliazione automatica:
   - Trovato in banca → BANCA (se era in cassa, SPOSTO)
   - Non trovato → CASSA

Autore: Sistema Refactored
Data: 13 Febbraio 2026
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# DATI PROVVISORI - LISTA E GESTIONE
# =============================================================================
# GET /dati-provvisori, POST /sposta-cassa, POST /sposta-banca,
# DELETE /{dato_id}, POST /upload-xml: smontati (audit 14/07/2026, piano
# residuo op.3) — zero chiamanti verificati (frontend/scheduler/interno/
# test). Il flusso "Provvisori" reale oggi è il tab in PrimaNota.jsx, che usa
# /api/prima-nota/provvisori/* (router diverso, non toccato). Codice
# conservato in git, non montato in produzione.


# =============================================================================
# RICONCILIAZIONE ESTRATTO CONTO
# =============================================================================

@router.post("/dati-provvisori/riconcilia-estratto-conto")
@handle_errors
async def riconcilia_con_estratto_conto() -> Dict[str, Any]:
    """
    Riconciliazione automatica quando carichi estratto conto:
    
    1. Per ogni movimento in estratto conto (nuovo):
       - Cerca fattura in prima_nota_cassa con stesso importo/data
       - Se trovata → SPOSTA da cassa a banca
    
    2. Per ogni fattura in prima_nota_cassa:
       - Se NON trovata in estratto conto → resta in CASSA
       - Se trovata → SPOSTA in BANCA
    """
    db = Database.get_db()
    
    logger.info("🔄 Avvio riconciliazione estratto conto...")
    
    spostati_in_banca = 0
    
    # Trova movimenti in cassa che potrebbero essere in banca
    movimenti_cassa = await db.prima_nota_cassa.find({
        "tipo": "uscita",
        "riconciliato": {"$ne": True},
        "metodo_scelto_manualmente": "cassa"
    }).to_list(1000)
    
    for mov_cassa in movimenti_cassa:
        importo = abs(mov_cassa["importo"])
        data = mov_cassa["data"]
        
        # Cerca in estratto conto con tolleranza
        data_min = (datetime.fromisoformat(data) - timedelta(days=7)).strftime("%Y-%m-%d")
        data_max = (datetime.fromisoformat(data) + timedelta(days=7)).strftime("%Y-%m-%d")
        
        mov_banca = await db.estratto_conto_movimenti.find_one({
            "importo": {"$gte": -importo - 1, "$lte": -importo + 1},
            "data_valuta": {"$gte": data_min, "$lte": data_max},
            "riconciliato": {"$ne": True}
        })
        
        if mov_banca:
            # TROVATO! Sposta da cassa a banca
            
            # Marca movimento cassa come riconciliato
            await db.prima_nota_cassa.update_one(
                {"_id": mov_cassa["_id"]},
                {
                    "$set": {
                        "riconciliato": True,
                        "spostato_in_banca": True,
                        "movimento_banca_id": str(mov_banca["_id"]),
                        "riconciliato_il": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Aggiorna movimento banca
            await db.estratto_conto_movimenti.update_one(
                {"_id": mov_banca["_id"]},
                {
                    "$set": {
                        "riconciliato": True,
                        "fornitore": mov_cassa.get("fornitore"),
                        "numero_documento": mov_cassa.get("numero_documento"),
                        "movimento_cassa_id": str(mov_cassa["_id"]),
                        "riconciliato_il": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            spostati_in_banca += 1
            logger.info(f"✅ SPOSTATO cassa→banca: {mov_cassa.get('fornitore')} - €{importo}")
    
    return {
        "success": True,
        "spostati_in_banca": spostati_in_banca,
        "message": f"Riconciliazione completata: {spostati_in_banca} movimenti spostati da cassa a banca"
    }



# =============================================================================
# PROPOSTE AUTOMATICHE (Fatture ↔ Banca)
# =============================================================================

@router.post("/genera-proposte")
@handle_errors
async def genera_proposte(anno: int = 2026) -> Dict[str, Any]:
    """
    Analizza fatture bonifico non pagate e propone abbinamenti con estratto conto.
    Le proposte vanno in 'dati_provvisori' con stato 'da_confermare'.
    L'utente conferma prima dell'inserimento definitivo.
    """
    from app.services.dati_provvisori_service import genera_proposte_pagamento
    db = Database.get_db()
    return await genera_proposte_pagamento(db, anno)


@router.get("/proposte")
@handle_errors
async def lista_proposte(stato: str = "da_confermare") -> Dict[str, Any]:
    """Lista proposte di pagamento da confermare/rifiutare."""
    db = Database.get_db()
    
    query = {"tipo": "pagamento_fattura"}
    if stato:
        query["stato"] = stato
    
    proposte = await db["dati_provvisori"].find(
        query, {"_id": 0}
    ).sort("confidence", -1).to_list(200)
    
    totale_importo = sum(float(p.get("fattura_importo", 0)) for p in proposte)
    
    return {
        "proposte": proposte,
        "totale": len(proposte),
        "importo_totale": round(totale_importo, 2),
    }


@router.post("/conferma/{proposta_id}")
@handle_errors
async def conferma(proposta_id: str) -> Dict[str, Any]:
    """Conferma una proposta: registra pagamento in Prima Nota Banca."""
    from app.services.dati_provvisori_service import conferma_proposta
    db = Database.get_db()
    return await conferma_proposta(db, proposta_id)


@router.post("/conferma-tutte")
@handle_errors
async def conferma_tutte_endpoint() -> Dict[str, Any]:
    """Conferma TUTTE le proposte in sospeso."""
    from app.services.dati_provvisori_service import conferma_tutte
    db = Database.get_db()
    return await conferma_tutte(db)


@router.post("/rifiuta/{proposta_id}")
@handle_errors
async def rifiuta(proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta (match errato)."""
    from app.services.dati_provvisori_service import rifiuta_proposta
    db = Database.get_db()
    return await rifiuta_proposta(db, proposta_id)
