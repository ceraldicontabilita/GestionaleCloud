"""
Prima Nota Module - Operazioni Prima Nota Salari.
CRUD per movimenti stipendi e salari.

Il sistema canonico dei salari e' ``/api/prima-nota-salari``
(``app/routers/accounting/prima_nota_salari.py``): nessuna pagina chiama
queste rotte. Restano corrette sugli stessi campi delle righe vere —
``importo_busta`` / ``importo_bonifico`` e ``dipendente`` /
``dipendente_nome`` — e con lo stesso filtro di stato.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database
from app.services.scritture_contabili import ScritturaNonValida, scrivi_riga_salari
from .common import COLLECTION_PRIMA_NOTA_SALARI, logger

# Le copie marcate dalla bonifica doppioni e le righe eliminate restano per
# audit, ma non compaiono in nessuna vista (come nel router canonico).
FILTRO_SALARI_ATTIVI: Dict[str, Any] = {
    "status": {"$nin": ["deleted", "archived", "archiviata"]},
    "entity_status": {"$ne": "deleted"},
}


def _totali_pipeline(match: Dict[str, Any], per_dipendente: bool = False) -> list:
    return [
        {"$match": match},
        {"$group": {
            "_id": {"$ifNull": ["$dipendente_nome", "$dipendente"]} if per_dipendente else None,
            "totale_buste": {"$sum": {"$ifNull": ["$importo_busta", 0]}},
            "totale_bonifici": {"$sum": {"$ifNull": ["$importo_bonifico", 0]}},
            "count": {"$sum": 1},
        }},
    ]


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
    
    query: Dict[str, Any] = dict(FILTRO_SALARI_ATTIVI)
    condizioni = []
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    if dipendente:
        # Il nome sta in ``dipendente_nome`` o in ``dipendente``:
        # ``nome_dipendente`` non esiste sulle righe salari.
        condizioni.append({"$or": [
            {"dipendente_nome": {"$regex": dipendente, "$options": "i"}},
            {"dipendente": {"$regex": dipendente, "$options": "i"}},
        ]})
    if anno:
        # Supporta sia records con campo 'anno' (int) sia record con solo 'data' (string)
        condizioni.append({"$or": [
            {"anno": anno},
            {"anno": {"$exists": False}, "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
            {"anno": None, "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}}
        ]})
    if condizioni:
        query["$and"] = condizioni

    movimenti = await db[COLLECTION_PRIMA_NOTA_SALARI].find(
        query, {"_id": 0}
    ).sort("data", -1).skip(skip).limit(limit).to_list(limit)

    totals = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate(
        _totali_pipeline(query)
    ).to_list(1)
    total = totals[0] if totals else {}

    return {
        "movimenti": movimenti,
        "totale_buste": round(float(total.get("totale_buste") or 0), 2),
        "totale_bonifici": round(float(total.get("totale_bonifici") or 0), 2),
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
        # Il campo che leggono le viste salari.
        "dipendente_nome": data.get("dipendente_nome") or data.get("nome_dipendente"),
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
    
    try:
        await scrivi_riga_salari(db, movimento)
    except ScritturaNonValida as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(f"Prima Nota Salari: creato movimento {movimento['id']}")
    
    return {"message": "Movimento salari creato", "id": movimento["id"]}


async def delete_prima_nota_salari(movimento_id: str) -> Dict[str, str]:
    """Elimina movimento prima nota salari.

    Soft delete per id: la riga resta per audit con motivo e data, fuori da
    ogni vista. Una scrittura sbagliata non si cancella.
    """
    db = Database.get_db()

    riga = await db[COLLECTION_PRIMA_NOTA_SALARI].find_one(
        {"id": movimento_id, **FILTRO_SALARI_ATTIVI}, {"_id": 0, "id": 1},
    )
    if not riga:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    ora = datetime.now(timezone.utc).isoformat()
    await db[COLLECTION_PRIMA_NOTA_SALARI].update_one({"id": movimento_id}, {"$set": {
        "status": "deleted",
        "deleted_at": ora,
        "deleted_reason": "eliminato_da_utente",
        "updated_at": ora,
    }})

    return {"message": "Movimento eliminato"}


async def get_salari_stats(
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Statistiche aggregate salari."""
    db = Database.get_db()
    
    match_filter: Dict[str, Any] = dict(FILTRO_SALARI_ATTIVI)
    if data_da:
        match_filter["data"] = {"$gte": data_da}
    if data_a:
        match_filter.setdefault("data", {})["$lte"] = data_a

    stats = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate(
        _totali_pipeline(match_filter)
    ).to_list(1)
    by_dipendente = await db[COLLECTION_PRIMA_NOTA_SALARI].aggregate(
        _totali_pipeline(match_filter, per_dipendente=True)
    ).to_list(1000)
    by_dipendente.sort(key=lambda d: -(d.get("totale_buste") or 0))

    result = stats[0] if stats else {}

    return {
        "totale_buste": round(float(result.get("totale_buste") or 0), 2),
        "totale_bonifici": round(float(result.get("totale_bonifici") or 0), 2),
        "count": result.get("count", 0),
        "by_dipendente": [
            {"nome": d["_id"], "totale_buste": round(float(d.get("totale_buste") or 0), 2),
             "totale_bonifici": round(float(d.get("totale_bonifici") or 0), 2),
             "count": d["count"]}
            for d in by_dipendente if d.get("_id")
        ],
    }
