"""
Prima Nota Module - Statistiche e Export.
Statistiche aggregate, export Excel, anni disponibili.
"""
from fastapi import HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, Literal
from datetime import datetime
import io

from app.database import Database
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA
)


async def get_anni_disponibili() -> Dict[str, Any]:
    """Restituisce gli anni per cui esistono movimenti in prima nota."""
    db = Database.get_db()
    
    anni = set()
    current_year = datetime.now().year
    anni.add(current_year)
    
    pipeline = [
        {"$project": {"anno": {"$substr": ["$data", 0, 4]}}},
        {"$group": {"_id": "$anno"}}
    ]
    
    cassa_anni = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline).to_list(100)
    for doc in cassa_anni:
        try:
            anni.add(int(doc["_id"]))
        except (ValueError, TypeError):
            pass
    
    banca_anni = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline).to_list(100)
    for doc in banca_anni:
        try:
            anni.add(int(doc["_id"]))
        except (ValueError, TypeError):
            pass
    
    return {"anni": sorted(list(anni), reverse=True)}


async def get_prima_nota_stats(
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Statistiche aggregate prima nota cassa e banca."""
    db = Database.get_db()
    
    match_filter = {}
    if data_da:
        match_filter["data"] = {"$gte": data_da}
    if data_a:
        match_filter.setdefault("data", {})["$lte"] = data_a
    
    cassa_pipeline = [
        {"$match": match_filter} if match_filter else {"$match": {}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1}
        }}
    ]
    cassa_stats = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(cassa_pipeline).to_list(1)
    
    banca_pipeline = [
        {"$match": match_filter} if match_filter else {"$match": {}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}},
            "count": {"$sum": 1}
        }}
    ]
    banca_stats = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(banca_pipeline).to_list(1)
    
    cassa = cassa_stats[0] if cassa_stats else {"entrate": 0, "uscite": 0, "count": 0}
    banca = banca_stats[0] if banca_stats else {"entrate": 0, "uscite": 0, "count": 0}
    
    return {
        "cassa": {
            "saldo": cassa.get("entrate", 0) - cassa.get("uscite", 0),
            "entrate": cassa.get("entrate", 0),
            "uscite": cassa.get("uscite", 0),
            "movimenti": cassa.get("count", 0)
        },
        "banca": {
            "saldo": banca.get("entrate", 0) - banca.get("uscite", 0),
            "entrate": banca.get("entrate", 0),
            "uscite": banca.get("uscite", 0),
            "movimenti": banca.get("count", 0)
        },
        "totale": {
            "saldo": (cassa.get("entrate", 0) - cassa.get("uscite", 0)) + (banca.get("entrate", 0) - banca.get("uscite", 0)),
            "entrate": cassa.get("entrate", 0) + banca.get("entrate", 0),
            "uscite": cassa.get("uscite", 0) + banca.get("uscite", 0)
        }
    }


async def get_saldo_finale(
    anno: int = Query(..., description="Anno per cui calcolare il saldo finale"),
    tipo: str = Query("cassa", description="Tipo: cassa o banca")
) -> Dict[str, Any]:
    """Calcola il saldo finale dell'anno specificato."""
    db = Database.get_db()
    
    collection = COLLECTION_PRIMA_NOTA_CASSA if tipo == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    
    anno_start = f"{anno}-01-01"
    anno_end = f"{anno}-12-31"
    
    movimenti = await db[collection].find({
        "data": {"$gte": anno_start, "$lte": anno_end},
        "status": {"$ne": "deleted"}
    }).to_list(length=None)
    
    saldo = 0
    for m in movimenti:
        importo = abs(m.get("importo", 0))
        if m.get("tipo") == "entrata":
            saldo += importo
        else:
            saldo -= importo
    
    return {
        "anno": anno,
        "tipo": tipo,
        "saldo": round(saldo, 2),
        "movimenti_count": len(movimenti)
    }


async def export_prima_nota_excel(
    tipo: Literal["cassa", "banca", "entrambi"] = Query("entrambi"),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None)
) -> StreamingResponse:
    """Export Prima Nota in Excel."""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="pandas non installato")
    
    db = Database.get_db()
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if tipo in ["cassa", "entrambi"]:
            cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
            if cassa:
                df_cassa = pd.DataFrame(cassa)
                cols = ["data", "tipo", "importo", "descrizione", "categoria", "riferimento"]
                df_cassa = df_cassa[[c for c in cols if c in df_cassa.columns]]
                df_cassa.to_excel(writer, sheet_name="Prima Nota Cassa", index=False)
        
        if tipo in ["banca", "entrambi"]:
            banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
            if banca:
                df_banca = pd.DataFrame(banca)
                cols = ["data", "tipo", "importo", "descrizione", "categoria", "riferimento", "assegno_collegato"]
                df_banca = df_banca[[c for c in cols if c in df_banca.columns]]
                df_banca.to_excel(writer, sheet_name="Prima Nota Banca", index=False)
    
    output.seek(0)
    filename = f"prima_nota_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
