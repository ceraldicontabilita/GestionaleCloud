"""
Suppliers validation endpoints.
Validazione P0, dizionario metodi pagamento.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone

from app.database import Database, Collections
from .common import PAYMENT_METHODS, PAYMENT_TERMS, METODI_BANCARI, logger

router = APIRouter()


@router.get("/payment-methods")
async def get_payment_methods() -> List[Dict[str, Any]]:
    """Ritorna la lista dei metodi di pagamento disponibili."""
    return [
        {"code": code, **data}
        for code, data in PAYMENT_METHODS.items()
    ]


@router.get("/payment-terms")
async def get_payment_terms() -> List[Dict[str, Any]]:
    """Ritorna i termini di pagamento standard."""
    return PAYMENT_TERMS


@router.get("/validazione-p0")
async def get_fornitori_con_problemi_p0() -> Dict[str, Any]:
    """
    PRD Validatori P0 - Ritorna i fornitori con problemi bloccanti:
    1. Senza metodo di pagamento
    2. Metodo bancario senza IBAN
    """
    db = Database.get_db()
    
    # P0: Senza metodo pagamento
    senza_metodo = await db[Collections.SUPPLIERS].find({
        "$or": [
            {"metodo_pagamento": None},
            {"metodo_pagamento": ""},
            {"metodo_pagamento": "da_configurare"},
            {"metodo_pagamento": {"$exists": False}}
        ]
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1}).to_list(500)
    
    # P0: Metodo bancario senza IBAN
    senza_iban = await db[Collections.SUPPLIERS].find({
        "metodo_pagamento": {"$in": METODI_BANCARI},
        "$or": [
            {"iban": None},
            {"iban": ""},
            {"iban": {"$exists": False}}
        ]
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1, "metodo_pagamento": 1}).to_list(500)
    
    return {
        "totale_problemi": len(senza_metodo) + len(senza_iban),
        "senza_metodo_pagamento": {
            "count": len(senza_metodo),
            "fornitori": senza_metodo[:50]
        },
        "metodo_bancario_senza_iban": {
            "count": len(senza_iban),
            "fornitori": senza_iban[:50]
        }
    }


@router.get("/dizionario-metodi-pagamento")
async def get_dizionario_metodi_pagamento() -> Dict[str, Any]:
    """
    Restituisce il dizionario completo dei metodi di pagamento associati ai fornitori.
    Viene utilizzato dalla Learning Machine per auto-assegnare i metodi in base alla P.IVA.
    """
    db = Database.get_db()
    
    # Pipeline per raggruppare fornitori per metodo pagamento
    pipeline = [
        {
            "$match": {
                "metodo_pagamento": {"$exists": True, "$ne": None, "$ne": ""}
            }
        },
        {
            "$group": {
                "_id": "$metodo_pagamento",
                "count": {"$sum": 1},
                "fornitori": {
                    "$push": {
                        "partita_iva": "$partita_iva",
                        "denominazione": {"$ifNull": ["$denominazione", "$ragione_sociale"]},
                        "iban": "$iban"
                    }
                }
            }
        },
        {"$sort": {"count": -1}}
    ]
    
    result = await db[Collections.SUPPLIERS].aggregate(pipeline).to_list(100)
    
    # Costruisci dizionario P.IVA -> Metodo
    dizionario_piva = {}
    for item in result:
        metodo = item["_id"]
        for fornitore in item.get("fornitori", []):
            piva = fornitore.get("partita_iva")
            if piva:
                dizionario_piva[piva] = {
                    "metodo": metodo,
                    "denominazione": fornitore.get("denominazione", ""),
                    "iban": fornitore.get("iban", "")
                }
    
    # Statistiche
    totale_fornitori = await db[Collections.SUPPLIERS].count_documents({})
    con_metodo = await db[Collections.SUPPLIERS].count_documents({
        "metodo_pagamento": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    return {
        "totale_fornitori": totale_fornitori,
        "con_metodo_configurato": con_metodo,
        "senza_metodo": totale_fornitori - con_metodo,
        "distribuzione": {item["_id"]: item["count"] for item in result},
        "dizionario_piva": dizionario_piva
    }


@router.post("/aggiorna-dizionario-metodo")
async def aggiorna_dizionario_metodo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggiorna il dizionario metodi pagamento per un fornitore.
    Usato dalla Learning Machine per apprendere nuove associazioni.
    
    Payload: {"partita_iva": "...", "metodo_pagamento": "...", "iban": "...", "source": "learning_machine|manual"}
    """
    db = Database.get_db()
    
    piva = payload.get("partita_iva")
    metodo = payload.get("metodo_pagamento")
    iban = payload.get("iban")
    source = payload.get("source", "manual")
    
    if not piva:
        raise HTTPException(status_code=400, detail="partita_iva richiesta")
    
    if metodo and metodo not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail=f"metodo_pagamento non valido: {metodo}")
    
    try:
        # Trova il fornitore
        fornitore = await db[Collections.SUPPLIERS].find_one({"partita_iva": piva})
        
        if not fornitore:
            return {
                "success": False,
                "message": f"Fornitore con P.IVA {piva} non trovato"
            }
        
        # Aggiorna
        update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
        
        if metodo:
            update_data["metodo_pagamento"] = metodo
        if iban:
            update_data["iban"] = iban
        
        result = await db[Collections.SUPPLIERS].update_one(
            {"partita_iva": piva},
            {"$set": update_data}
        )
        
        # Log dell'apprendimento se dalla Learning Machine
        if source == "learning_machine":
            await db["learning_feedback"].insert_one({
                "tipo": "metodo_pagamento",
                "partita_iva": piva,
                "metodo_vecchio": fornitore.get("metodo_pagamento"),
                "metodo_nuovo": metodo,
                "iban_vecchio": fornitore.get("iban"),
                "iban_nuovo": iban,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        return {
            "success": True,
            "modified": result.modified_count > 0,
            "fornitore": fornitore.get("denominazione") or fornitore.get("ragione_sociale", ""),
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Errore aggiornamento dizionario metodi: {e}")
        raise HTTPException(status_code=500, detail=str(e))
