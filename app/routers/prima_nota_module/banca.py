"""
Prima Nota Module - Operazioni Prima Nota Banca.
CRUD e operazioni per movimenti bancari.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database
from .common import (
    COLLECTION_PRIMA_NOTA_BANCA, TIPO_MOVIMENTO, calcola_saldo_anni_precedenti
)


async def list_prima_nota_banca(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=2500),
    anno: Optional[int] = Query(None, description="Anno (es. 2024, 2025)"),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Lista movimenti prima nota banca con saldo separato per anno."""
    db = Database.get_db()
    
    query = {"status": {"$nin": ["deleted", "archived"]}}
    
    if anno:
        query["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
    
    if data_da:
        query.setdefault("data", {})["$gte"] = data_da
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    if tipo:
        query["tipo"] = tipo
    if categoria:
        query["categoria"] = categoria
    
    movimenti = await db[COLLECTION_PRIMA_NOTA_BANCA].find(query, {"_id": 0}).sort("data", -1).skip(skip).limit(limit).to_list(limit)
    
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    totals = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline).to_list(1)
    
    entrate_anno = totals[0].get("entrate", 0) if totals else 0
    uscite_anno = totals[0].get("uscite", 0) if totals else 0
    saldo_anno = entrate_anno - uscite_anno
    
    saldo_precedente = await calcola_saldo_anni_precedenti(db, COLLECTION_PRIMA_NOTA_BANCA, anno) if anno else 0.0
    saldo_finale = saldo_precedente + saldo_anno
    
    return {
        "movimenti": movimenti,
        "saldo": round(saldo_finale, 2),
        "saldo_anno": round(saldo_anno, 2),
        "saldo_precedente": round(saldo_precedente, 2),
        "totale_entrate": round(entrate_anno, 2),
        "totale_uscite": round(uscite_anno, 2),
        "count": len(movimenti),
        "anno": anno
    }


async def create_prima_nota_banca(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea movimento prima nota banca."""
    db = Database.get_db()
    
    required = ["data", "tipo", "importo", "descrizione"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    if data["tipo"] not in TIPO_MOVIMENTO:
        raise HTTPException(status_code=400, detail="Tipo deve essere 'entrata' o 'uscita'")
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": data["tipo"],
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Altro"),
        "riferimento": data.get("riferimento"),
        "fornitore_piva": data.get("fornitore_piva"),
        "fattura_id": data.get("fattura_id"),
        "iban": data.get("iban"),
        "conto_bancario": data.get("conto_bancario"),
        "note": data.get("note"),
        "source": data.get("source"),
        "pos_details": data.get("pos_details"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
    return {"message": "Movimento banca creato", "id": movimento["id"]}


async def update_prima_nota_banca(
    movimento_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """Modifica movimento prima nota banca."""
    db = Database.get_db()
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    for field in ["data", "tipo", "importo", "descrizione", "categoria", "riferimento", "note", "fornitore", "ragione_sociale"]:
        if field in data:
            update_data[field] = float(data[field]) if field == "importo" else data[field]
    
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
        {"id": movimento_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    return {"message": "Movimento aggiornato", "id": movimento_id}


async def delete_movimento_banca(
    movimento_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """Elimina un singolo movimento banca con validazione."""
    from app.services.business_rules import BusinessRules, EntityStatus
    
    db = Database.get_db()
    
    mov = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({"id": movimento_id})
    if not mov:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    validation = BusinessRules.can_delete_movement(mov)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Eliminazione non consentita", "errors": validation.errors}
        )
    
    if validation.warnings and not force:
        return {
            "status": "warning",
            "warnings": validation.warnings,
            "require_force": True
        }
    
    await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
        {"id": movimento_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Movimento eliminato (archiviato)"}


async def delete_all_prima_nota_banca() -> Dict[str, Any]:
    """Elimina TUTTI i movimenti dalla prima nota banca."""
    db = Database.get_db()
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many({})
    return {"message": f"Eliminati {result.deleted_count} movimenti dalla banca"}


async def delete_banca_by_source(source: str) -> Dict[str, Any]:
    """Elimina movimenti banca per source."""
    db = Database.get_db()
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many({"source": source})
    return {"message": f"Eliminati {result.deleted_count} movimenti con source={source}"}


async def get_fattura_allegata_banca(movimento_id: str) -> Dict[str, Any]:
    """Recupera la fattura allegata a un movimento banca."""
    db = Database.get_db()
    
    mov = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({"id": movimento_id}, {"_id": 0})
    if not mov:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    fattura_id = mov.get("fattura_id")
    if not fattura_id:
        return {"movimento_id": movimento_id, "fattura": None, "message": "Nessuna fattura collegata"}
    
    fattura = await db["invoices"].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
        {"_id": 0}
    )
    
    return {
        "movimento_id": movimento_id,
        "fattura": fattura,
        "message": "Fattura trovata" if fattura else "Fattura non trovata nel DB"
    }
