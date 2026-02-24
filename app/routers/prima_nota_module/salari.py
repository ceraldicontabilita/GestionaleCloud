"""
Prima Nota Module - Operazioni Prima Nota Salari.
CRUD per movimenti stipendi e salari.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database
from .common import COLLECTION_PRIMA_NOTA_SALARI, logger


async def get_prima_nota_salari(
    data_da: Optional[str] = Query(None, description="Data inizio (YYYY-MM-DD)"),
    data_a: Optional[str] = Query(None, description="Data fine (YYYY-MM-DD)"),
    dipendente: Optional[str] = Query(None, description="Filtro per nome dipendente"),
    anno: Optional[int] = Query(None, description="Anno"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=2500)
) -> Dict[str, Any]:
    """Lista movimenti prima nota salari con filtri."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    if dipendente:
        query["nome_dipendente"] = {"$regex": dipendente, "$options": "i"}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    movimenti = await db[COLLECTION_PRIMA_NOTA_SALARI].find(
        query, {"_id": 0}
    ).sort("data", -1).skip(skip).limit(limit).to_list(limit)
    
    totals = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate([
        {"$match": query},
        {"$group": {
            "_id": None,
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    total = totals[0] if totals else {"totale": 0, "count": 0}
    
    return {
        "movimenti": movimenti,
        "totale": total.get("totale", 0),
        "count": total.get("count", 0)
    }


async def create_prima_nota_salari(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea nuovo movimento prima nota salari."""
    db = Database.get_db()
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": "uscita",
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Stipendi"),
        "nome_dipendente": data.get("nome_dipendente"),
        "codice_fiscale": data.get("codice_fiscale"),
        "employee_id": data.get("employee_id"),
        "dipendente_id": data.get("dipendente_id"),
        "periodo": data.get("periodo"),
        "mese": data.get("mese"),
        "anno": data.get("anno"),
        "riferimento": data.get("riferimento"),
        "note": data.get("note"),
        "source": data.get("source", "manual_entry"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION_PRIMA_NOTA_SALARI].insert_one(movimento.copy())
    logger.info(f"Prima Nota Salari: creato movimento {movimento['id']}")
    
    return {"message": "Movimento salari creato", "id": movimento["id"]}


async def delete_prima_nota_salari(movimento_id: str) -> Dict[str, str]:
    """Elimina movimento prima nota salari."""
    db = Database.get_db()
    
    result = await db[COLLECTION_PRIMA_NOTA_SALARI].delete_one({"id": movimento_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    return {"message": "Movimento eliminato"}


async def get_salari_stats(
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Statistiche aggregate salari."""
    db = Database.get_db()
    
    match_filter = {}
    if data_da:
        match_filter["data"] = {"$gte": data_da}
    if data_a:
        match_filter.setdefault("data", {})["$lte"] = data_a
    
    pipeline = [
        {"$match": match_filter} if match_filter else {"$match": {}},
        {"$group": {
            "_id": None,
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }}
    ]
    stats = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate(pipeline).to_list(1)
    
    by_dipendente_pipeline = [
        {"$match": match_filter} if match_filter else {"$match": {}},
        {"$group": {
            "_id": "$nome_dipendente",
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}}
    ]
    by_dipendente = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate(by_dipendente_pipeline).to_list(100)
    
    result = stats[0] if stats else {"totale": 0, "count": 0}
    
    return {
        "totale": result.get("totale", 0),
        "count": result.get("count", 0),
        "by_dipendente": [{"nome": d["_id"], "totale": d["totale"], "count": d["count"]} for d in by_dipendente if d["_id"]]
    }
