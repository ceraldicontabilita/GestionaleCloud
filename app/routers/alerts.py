"""
Router per gestione Alert di sistema.
Include alert per fornitori senza metodo pagamento, scadenze, etc.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def alerts_summary() -> Dict[str, Any]:
    """
    Summary degli alert APERTI del sistema relazionale, aggregati per severità e modulo.
    Usato dal badge nella topnav per mostrare il conteggio visibile all'utente.

    Compatibile con entrambi gli schemi alert:
    - Schema legacy: {letto: bool, risolto: bool}
    - Schema relazionale: {stato: "aperto"|"risolto", severita: "critical"|"warning"|"info"}
    """
    db = Database.get_db()

    # Query: alert aperti nello schema relazionale (stato="aperto")
    # OR alert legacy non risolti (risolto=false)
    query_open = {
        "$or": [
            {"stato": "aperto"},
            {"$and": [
                {"stato": {"$exists": False}},
                {"risolto": {"$ne": True}}
            ]}
        ]
    }

    # Conteggio per severità
    per_severita: Dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    pipeline_sev = [
        {"$match": query_open},
        {"$group": {"_id": "$severita", "count": {"$sum": 1}}}
    ]
    async for doc in db["alerts"].aggregate(pipeline_sev):
        sev = doc["_id"] or "info"
        if sev in per_severita:
            per_severita[sev] = doc["count"]

    # Conteggio per modulo
    per_modulo: Dict[str, int] = {}
    pipeline_mod = [
        {"$match": query_open},
        {"$group": {"_id": "$modulo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    async for doc in db["alerts"].aggregate(pipeline_mod):
        if doc["_id"]:
            per_modulo[doc["_id"]] = doc["count"]

    # Top 5 alert critici recenti (per dropdown)
    critical_recenti = await db["alerts"].find(
        {**query_open, "severita": "critical"},
        {"_id": 0, "id": 1, "codice": 1, "titolo": 1, "dettaglio": 1,
         "modulo": 1, "severita": 1, "created_at": 1, "entita_id": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    totale = sum(per_severita.values())

    return {
        "totale_aperti": totale,
        "per_severita": per_severita,
        "per_modulo": per_modulo,
        "critical_recenti": critical_recenti,
    }

@router.get("/lista")
async def lista_alerts(
    tipo: Optional[str] = Query(None, description="Filtra per tipo alert"),
    letto: Optional[bool] = Query(None, description="Filtra per letto/non letto"),
    risolto: Optional[bool] = Query(None, description="Filtra per risolto/non risolto"),
    limit: int = Query(50, ge=1, le=200)
) -> Dict[str, Any]:
    """
    Lista tutti gli alert di sistema.
    """
    db = Database.get_db()
    
    query = {}
    if tipo:
        query["tipo"] = tipo
    if letto is not None:
        query["letto"] = letto
    if risolto is not None:
        query["risolto"] = risolto
    
    alerts = await db["alerts"].find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Statistiche
    totale = await db["alerts"].count_documents({})
    non_letti = await db["alerts"].count_documents({"letto": False})
    non_risolti = await db["alerts"].count_documents({"risolto": False})
    
    # Conta per tipo
    pipeline = [
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    per_tipo = {}
    async for doc in db["alerts"].aggregate(pipeline):
        if doc["_id"]:
            per_tipo[doc["_id"]] = doc["count"]
    
    return {
        "alerts": alerts,
        "stats": {
            "totale": totale,
            "non_letti": non_letti,
            "non_risolti": non_risolti,
            "per_tipo": per_tipo
        }
    }


@router.get("/fornitori-senza-metodo")
async def alerts_fornitori_senza_metodo() -> Dict[str, Any]:
    """
    Lista alert specifici per fornitori senza metodo pagamento configurato.
    """
    db = Database.get_db()
    
    alerts = await db["alerts"].find(
        {"tipo": "fornitore_senza_metodo_pagamento", "risolto": False},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.post("/{alert_id}/segna-letto")
async def segna_alert_letto(alert_id: str) -> Dict[str, Any]:
    """Segna un alert come letto."""
    db = Database.get_db()
    
    result = await db["alerts"].update_one(
        {"id": alert_id},
        {"$set": {"letto": True, "letto_il": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert segnato come letto"}


@router.post("/{alert_id}/risolvi")
async def risolvi_alert(alert_id: str) -> Dict[str, Any]:
    """Segna un alert come risolto."""
    db = Database.get_db()
    
    result = await db["alerts"].update_one(
        {"id": alert_id},
        {"$set": {
            "risolto": True, 
            "risolto_il": datetime.now(timezone.utc).isoformat(),
            "letto": True
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert risolto"}


@router.delete("/{alert_id}")
async def elimina_alert(alert_id: str) -> Dict[str, Any]:
    """Elimina un alert."""
    db = Database.get_db()
    
    result = await db["alerts"].delete_one({"id": alert_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert eliminato"}


@router.post("/risolvi-fornitore/{fornitore_piva}")
async def risolvi_alerts_fornitore(fornitore_piva: str) -> Dict[str, Any]:
    """
    Risolve automaticamente tutti gli alert per un fornitore 
    quando viene configurato il metodo di pagamento.
    """
    db = Database.get_db()
    
    result = await db["alerts"].update_many(
        {
            "tipo": "fornitore_senza_metodo_pagamento",
            "fornitore_piva": fornitore_piva,
            "risolto": False
        },
        {"$set": {
            "risolto": True,
            "risolto_il": datetime.now(timezone.utc).isoformat(),
            "note_risoluzione": "Metodo pagamento configurato"
        }}
    )
    
    return {
        "success": True,
        "alerts_risolti": result.modified_count
    }
