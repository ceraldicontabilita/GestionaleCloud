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
    """Riconcilia cassa↔estratto conto solo quando il candidato è univoco.

    Una compatibilità di importo/data è una proposta, non una prova sufficiente
    quando esistono più movimenti EC possibili. In caso di ambiguità nessun
    record viene modificato e il caso resta da verificare manualmente.
    """
    db = Database.get_db()
    logger.info("🔄 Avvio riconciliazione estratto conto...")

    spostati_in_banca = 0
    ambigui = 0
    senza_match = 0

    movimenti_cassa = await db.prima_nota_cassa.find({
        "tipo": "uscita",
        "riconciliato": {"$ne": True},
        "metodo_scelto_manualmente": "cassa"
    }).to_list(1000)

    for mov_cassa in movimenti_cassa:
        importo = abs(float(mov_cassa["importo"]))
        data = mov_cassa["data"]
        data_min = (datetime.fromisoformat(data) - timedelta(days=7)).strftime("%Y-%m-%d")
        data_max = (datetime.fromisoformat(data) + timedelta(days=7)).strftime("%Y-%m-%d")

        candidati = await db.estratto_conto_movimenti.find({
            "importo": {"$gte": -importo - 1, "$lte": -importo + 1},
            "data_valuta": {"$gte": data_min, "$lte": data_max},
            "riconciliato": {"$ne": True}
        }).to_list(2)

        if len(candidati) != 1:
            if candidati:
                ambigui += 1
                logger.warning(
                    "Riconciliazione cassa↔banca ambigua: %s candidati per %s €%.2f",
                    len(candidati), mov_cassa.get("id") or mov_cassa.get("_id"), importo,
                )
            else:
                senza_match += 1
            continue

        mov_banca = candidati[0]
        mov_banca_id = mov_banca.get("id") or mov_banca.get("_id")
        mov_cassa_id = mov_cassa.get("id") or mov_cassa.get("_id")
        now = datetime.now(timezone.utc).isoformat()

        # Claim atomico del movimento EC: se nel frattempo è stato riconciliato,
        # non si procede con la mutazione della Prima Nota Cassa.
        claim = await db.estratto_conto_movimenti.update_one(
            {
                "$or": [{"id": mov_banca_id}, {"_id": mov_banca.get("_id")}],
                "riconciliato": {"$ne": True},
            },
            {"$set": {
                "riconciliato": True,
                "fornitore": mov_cassa.get("fornitore"),
                "numero_documento": mov_cassa.get("numero_documento"),
                "movimento_cassa_id": str(mov_cassa_id),
                "riconciliato_il": now,
                "riconciliazione_fonte": "dati_provvisori_univoco",
            }},
        )
        if getattr(claim, "modified_count", 0) == 0:
            continue

        await db.prima_nota_cassa.update_one(
            {"$or": [{"id": mov_cassa_id}, {"_id": mov_cassa.get("_id")}], "riconciliato": {"$ne": True}},
            {"$set": {
                "riconciliato": True,
                "spostato_in_banca": True,
                "movimento_banca_id": str(mov_banca_id),
                "riconciliato_il": now,
                "riconciliazione_fonte": "dati_provvisori_univoco",
            }},
        )

        spostati_in_banca += 1
        logger.info("✅ CASSA↔BANCA riconciliato con candidato univoco: %s - €%.2f", mov_cassa.get("fornitore"), importo)

    return {
        "success": True,
        "spostati_in_banca": spostati_in_banca,
        "ambigui": ambigui,
        "senza_match": senza_match,
        "message": (
            f"Riconciliazione completata: {spostati_in_banca} univoci, "
            f"{ambigui} ambigui, {senza_match} senza match"
        )
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
    """Bloccata: una proposta non è prova e richiede conferma puntuale."""
    raise HTTPException(
        status_code=409,
        detail="Conferma massiva disabilitata: verificare ogni proposta e confermarla singolarmente",
    )


@router.post("/rifiuta/{proposta_id}")
@handle_errors
async def rifiuta(proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta (match errato)."""
    from app.services.dati_provvisori_service import rifiuta_proposta
    db = Database.get_db()
    return await rifiuta_proposta(db, proposta_id)
