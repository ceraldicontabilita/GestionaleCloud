"""
Router per la gestione dell'Inventario annuale.
Permette di creare inventari con importo target e lista prodotti.
"""

from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from ..database import Database

router = APIRouter(prefix="/inventario", tags=["inventario"])

COLLECTION = "inventari"


@router.get("")
async def get_inventari(anno: Optional[int] = None) -> Dict[str, Any]:
    """
    Lista tutti gli inventari, opzionalmente filtrati per anno.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    
    inventari = await db[COLLECTION].find(query, {"_id": 0}).sort("data_creazione", -1).to_list(100)
    
    return {"inventari": inventari}


@router.get("/{inventario_id}")
async def get_inventario(inventario_id: str) -> Dict[str, Any]:
    """
    Dettaglio singolo inventario.
    """
    db = Database.get_db()
    
    inventario = await db[COLLECTION].find_one({"id": inventario_id}, {"_id": 0})
    
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario non trovato")
    
    return inventario


@router.post("")
async def create_inventario(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Crea un nuovo inventario.
    
    Body:
    - anno: Anno di riferimento inventario
    - importo_target: Importo target da raggiungere (netto IVA)
    - importo_totale: Importo totale calcolato
    - prodotti: Lista prodotti con quantità e prezzi
    """
    db = Database.get_db()
    
    inventario = {
        "id": str(uuid.uuid4()),
        "anno": data.get("anno", datetime.now().year),
        "importo_target": data.get("importo_target", 0),
        "importo_totale": data.get("importo_totale", 0),
        "prodotti": data.get("prodotti", []),
        "note": data.get("note", ""),
        "stato": "completato",
        "data_creazione": data.get("data_creazione") or datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION].insert_one(inventario.copy())
    
    return {
        "success": True,
        "id": inventario["id"],
        "message": f"Inventario {inventario['anno']} creato con {len(inventario['prodotti'])} prodotti"
    }


@router.put("/{inventario_id}")
async def update_inventario(inventario_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Aggiorna un inventario esistente.
    """
    db = Database.get_db()
    
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    for field in ["importo_target", "importo_totale", "prodotti", "note", "stato"]:
        if field in data:
            update_data[field] = data[field]
    
    result = await db[COLLECTION].update_one(
        {"id": inventario_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Inventario non trovato")
    
    return {"success": True, "message": "Inventario aggiornato"}


@router.delete("/{inventario_id}")
async def delete_inventario(inventario_id: str) -> Dict[str, Any]:
    """
    Elimina un inventario.
    """
    db = Database.get_db()
    
    result = await db[COLLECTION].delete_one({"id": inventario_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Inventario non trovato")
    
    return {"success": True, "message": "Inventario eliminato"}


@router.get("/stats/riepilogo")
async def get_stats_inventario() -> Dict[str, Any]:
    """
    Statistiche riepilogative inventari.
    """
    db = Database.get_db()
    
    totale = await db[COLLECTION].count_documents({})
    
    # Totale per anno
    pipeline = [
        {"$group": {
            "_id": "$anno",
            "count": {"$sum": 1},
            "valore_totale": {"$sum": "$importo_totale"}
        }},
        {"$sort": {"_id": -1}}
    ]
    
    per_anno = []
    async for doc in db[COLLECTION].aggregate(pipeline):
        per_anno.append({
            "anno": doc["_id"],
            "inventari": doc["count"],
            "valore_totale": doc["valore_totale"]
        })
    
    return {
        "totale_inventari": totale,
        "per_anno": per_anno
    }
