"""Admin router - Administrative functions."""
from fastapi import APIRouter, Depends, Path, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/stats",
    summary="Get database statistics"
)
async def get_stats(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get statistics for main collections."""
    db = Database.get_db()
    
    stats = {
        "invoices": await db["invoices"].count_documents({}),
        "suppliers": await db["fornitori"].count_documents({}),
        "products": await db["warehouse_inventory"].count_documents({}),
        "employees": await db["employees"].count_documents({}),
        "prima_nota_cassa": await db["prima_nota_cassa"].count_documents({}),
        "prima_nota_banca": await db["prima_nota_banca"].count_documents({}),
        "f24": await db["f24_unificato"].count_documents({})
    }
    
    return stats


@router.get(
    "/year-opening-balances/{year}",
    summary="Get year opening balances"
)
async def get_year_opening_balances(
    year: int = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get opening balances for a year."""
    db = Database.get_db()
    balances = await db["opening_balances"].find_one({"year": year}, {"_id": 0})
    return balances or {"year": year, "balances": {}}


@router.put(
    "/year-opening-balances/{year}",
    summary="Update year opening balances"
)
async def update_year_opening_balances(
    data: Dict[str, Any],
    year: int = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update opening balances for a year."""
    db = Database.get_db()
    data["year"] = year
    data["updated_at"] = datetime.now(timezone.utc)
    await db["opening_balances"].update_one({"year": year}, {"$set": data}, upsert=True)
    return {"message": "Balances updated"}


@router.get(
    "/collections",
    summary="Get collections list"
)
async def get_collections(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of collections and counts."""
    db = Database.get_db()
    cols = await db.list_collection_names()
    results = []
    for c in cols:
        count = await db[c].count_documents({})
        results.append({"name": c, "count": count})
    return results


@router.post(
    "/reset-collections",
    summary="Reset selected collections"
)
async def reset_collections(
    selected: List[str] = Query(None),
    delete_files: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Reset selected collections (Delete all data).
    If selected is None or empty, NOTHING happens unless specific 'all' logic is added.
    Frontend sends selected=...
    """
    db = Database.get_db()
    deleted_stats = {}
    
    # Protect critical collections
    protected = ["users", "system_settings", "settings"]
    
    targets = selected or []
    
    for col in targets:
        if col in protected:
            continue
        if col not in await db.list_collection_names():
            continue
            
        result = await db[col].delete_many({})
        deleted_stats[col] = {"deleted": result.deleted_count}
        
    return {"message": "Collections reset", "deleted_collections": deleted_stats}


@router.get(
    "/fatture-stats",
    summary="Get fatture statistics"
)
async def get_fatture_stats() -> Dict[str, Any]:
    """
    Restituisce statistiche sui metodi di pagamento delle fatture.
    """
    db = Database.get_db()
    
    # Totale fatture
    totale = await db["invoices"].count_documents({})
    
    # Conteggio per metodo di pagamento
    pipeline = [
        {"$group": {"_id": "$metodo_pagamento", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    metodi = await db["invoices"].aggregate(pipeline).to_list(20)
    
    # Fatture senza metodo
    senza_metodo = await db["invoices"].count_documents({
        "$or": [
            {"metodo_pagamento": {"$exists": False}},
            {"metodo_pagamento": None},
            {"metodo_pagamento": ""}
        ]
    })
    
    return {
        "totale": totale,
        "metodi_pagamento": metodi,
        "senza_metodo": senza_metodo
    }


@router.post(
    "/fatture-set-metodo-pagamento",
    summary="Set payment method for invoices"
)
async def set_fatture_metodo_pagamento(
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Imposta il metodo di pagamento per le fatture che non ne hanno uno.
    Richiede conferma doppia dal frontend.
    """
    db = Database.get_db()
    
    metodo = data.get("metodo_pagamento", "Bonifico")
    
    # Aggiorna solo fatture senza metodo
    result = await db["invoices"].update_many(
        {
            "$or": [
                {"metodo_pagamento": {"$exists": False}},
                {"metodo_pagamento": None},
                {"metodo_pagamento": ""}
            ]
        },
        {"$set": {
            "metodo_pagamento": metodo,
            "metodo_pagamento_updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"Updated {result.modified_count} invoices with metodo_pagamento={metodo}")
    
    return {
        "success": True,
        "message": f"Metodo pagamento impostato a '{metodo}'",
        "updated": result.modified_count
    }
