"""
Gestione Riservata - Dati non fatturati (incassi/spese extra).
Accesso protetto con codice da variabile d'ambiente.
"""
from fastapi import APIRouter, HTTPException, Body, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging
import os

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# Codice accesso da variabile d'ambiente (MAI hardcoded)
GESTIONE_RISERVATA_CODE = os.environ.get("GESTIONE_RISERVATA_CODE", "")
if not GESTIONE_RISERVATA_CODE:
    logger.warning("⚠️ GESTIONE_RISERVATA_CODE non configurato in .env")
COLLECTION_NAME = "gestione_riservata"


@router.post("/login")
async def gestione_riservata_login(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Login gestione riservata con codice accesso."""
    code = str(data.get("code", "")).strip()
    
    if not code:
        raise HTTPException(status_code=400, detail="Inserire il codice di accesso")
    
    if code != GESTIONE_RISERVATA_CODE:
        logger.warning(f"Tentativo accesso Gestione Riservata fallito con codice: {code}")
        raise HTTPException(status_code=401, detail="Codice di accesso non valido")
    
    return {
        "success": True,
        "message": "Accesso autorizzato",
        "portal": "gestione_riservata"
    }


@router.get("/movimenti")
async def get_movimenti(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None)  # "incasso" o "spesa"
) -> List[Dict[str, Any]]:
    """Lista movimenti non fatturati."""
    db = Database.get_db()
    
    query = {"entity_status": {"$ne": "deleted"}}
    
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    if tipo:
        query["tipo"] = tipo
    
    movimenti = await db[COLLECTION_NAME].find(
        query, 
        {"_id": 0}
    ).sort("data", -1).to_list(10000)
    
    return movimenti


@router.post("/movimenti")
async def create_movimento(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea nuovo movimento non fatturato."""
    db = Database.get_db()
    
    data_mov = data.get("data", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    # Estrai anno e mese dalla data
    try:
        dt = datetime.strptime(data_mov, "%Y-%m-%d")
        anno = dt.year
        mese = dt.month
    except Exception:
        anno = datetime.now().year
        mese = datetime.now().month
    
    movimento = {
        "id": str(uuid4()),
        "data": data_mov,
        "anno": anno,
        "mese": mese,
        "tipo": data.get("tipo", "incasso"),  # "incasso" o "spesa"
        "descrizione": data.get("descrizione", ""),
        "importo": float(data.get("importo", 0) or 0),
        "categoria": data.get("categoria", "altro"),
        "note": data.get("note", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entity_status": "active"
    }
    
    await db[COLLECTION_NAME].insert_one(movimento.copy())
    movimento.pop("_id", None)
    
    return movimento


@router.put("/movimenti/{movimento_id}")
async def update_movimento(
    movimento_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Aggiorna movimento esistente."""
    db = Database.get_db()
    
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    for field in ["data", "tipo", "descrizione", "importo", "categoria", "note"]:
        if field in data:
            update_data[field] = data[field]
    
    # Ricalcola anno/mese se la data è cambiata
    if "data" in data:
        try:
            dt = datetime.strptime(data["data"], "%Y-%m-%d")
            update_data["anno"] = dt.year
            update_data["mese"] = dt.month
        except Exception:
            pass
    
    result = await db[COLLECTION_NAME].update_one(
        {"id": movimento_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    movimento = await db[COLLECTION_NAME].find_one({"id": movimento_id}, {"_id": 0})
    return movimento


@router.delete("/movimenti/{movimento_id}")
async def delete_movimento(movimento_id: str) -> Dict[str, Any]:
    """Elimina movimento (soft-delete)."""
    db = Database.get_db()
    
    result = await db[COLLECTION_NAME].update_one(
        {"id": movimento_id},
        {"$set": {
            "entity_status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    return {"success": True, "message": "Movimento eliminato"}


@router.get("/riepilogo")
async def get_riepilogo(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """Riepilogo totali incassi/spese non fatturati."""
    db = Database.get_db()
    
    match_query = {"entity_status": {"$ne": "deleted"}}
    if anno:
        match_query["anno"] = anno
    if mese:
        match_query["mese"] = mese
    
    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": "$tipo",
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }}
    ]
    
    results = await db[COLLECTION_NAME].aggregate(pipeline).to_list(100)
    
    totali = {
        "incassi": {"totale": 0, "count": 0},
        "spese": {"totale": 0, "count": 0}
    }
    
    for r in results:
        if r["_id"] == "incasso":
            totali["incassi"] = {"totale": r["totale"], "count": r["count"]}
        elif r["_id"] == "spesa":
            totali["spese"] = {"totale": r["totale"], "count": r["count"]}
    
    totali["saldo_netto"] = totali["incassi"]["totale"] - totali["spese"]["totale"]
    
    return totali


@router.get("/volume-affari-reale")
async def get_volume_affari_reale(
    anno: int = Query(...),
    mese: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Calcola il volume d'affari reale:
    Fatturato ufficiale + Corrispettivi + Incassi non fatturati - Spese non fatturate
    """
    db = Database.get_db()
    
    # 1. Fatturato ufficiale = corrispettivi (le fatture emesse sono già incluse nei corrispettivi)
    # Le fatture ricevute (invoices) sono COSTI, non ricavi
    corr_match = {"data": {"$regex": f"^{anno}"}}
    if mese:
        corr_match["data"] = {"$regex": f"^{anno}-{str(mese).zfill(2)}"}
    
    corr_pipeline = [
        {"$match": corr_match},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]
    corr_result = await db["corrispettivi"].aggregate(corr_pipeline).to_list(1)
    fatturato_ufficiale = corr_result[0]["totale"] if corr_result else 0
    corrispettivi = fatturato_ufficiale  # stessi dati (fatture emesse = corrispettivi)
    
    # 2. Incassi/Spese non fatturati
    riservata_query = {"entity_status": {"$ne": "deleted"}, "anno": anno}
    if mese:
        riservata_query["mese"] = mese
    
    riservata_pipeline = [
        {"$match": riservata_query},
        {"$group": {
            "_id": "$tipo",
            "totale": {"$sum": "$importo"}
        }}
    ]
    riservata_result = await db[COLLECTION_NAME].aggregate(riservata_pipeline).to_list(100)
    
    incassi_extra = 0
    spese_extra = 0
    for r in riservata_result:
        if r["_id"] == "incasso":
            incassi_extra = r["totale"]
        elif r["_id"] == "spesa":
            spese_extra = r["totale"]
    
    # Calcolo finale - Volume Affari = corrispettivi + extras
    totale_ufficiale = fatturato_ufficiale
    volume_reale = totale_ufficiale + incassi_extra - spese_extra
    
    return {
        "anno": anno,
        "mese": mese,
        "fatturato_ufficiale": fatturato_ufficiale,
        "corrispettivi": corrispettivi,
        "totale_ufficiale": totale_ufficiale,
        "incassi_non_fatturati": incassi_extra,
        "spese_non_fatturate": spese_extra,
        "saldo_extra": incassi_extra - spese_extra,
        "volume_affari_reale": volume_reale
    }
