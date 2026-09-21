"""
Router per gestione Storico Produzioni.
Salva e recupera eventi di produzione (ricetta, quantità, data, costo).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.lotti.db import database as db
from app.lotti.auth import require_admin, request_actor
from app.lotti.servizi.annullamento_produzione_service import annulla_produzione

router = APIRouter(prefix="/produzioni", tags=["Produzioni"])


class AnnullamentoProduzione(BaseModel):
    motivo: str = Field(min_length=3)


@router.get("/per-oggi")
async def get_produzioni_oggi():
    """Produzioni registrate oggi, solo quelle da laboratorio (pasticceria/rosticceria)."""
    from app.lotti.routers.date_utils import oggi_iso

    oggi = oggi_iso()
    # Cerca per data ISO oppure data con timestamp (substr 10)
    pipeline = [
        {"$addFields": {"data_str": {"$substr": ["$data", 0, 10]}}},
        {"$match": {"data_str": oggi, "reparto": {"$in": ["pasticceria", "rosticceria"]}, "stato": {"$ne": "annullata"}}},
        {"$project": {"_id": 0}},
    ]
    docs = await db.produzioni.aggregate(pipeline).to_list(200)
    return docs


@router.get("/")
async def get_produzioni(
    ricetta_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    """Lista storico produzioni, ordinato per data decrescente"""
    query = {}
    if ricetta_id:
        query["ricetta_id"] = ricetta_id
    if search:
        query["ricetta_nome"] = {"$regex": search, "$options": "i"}

    produzioni = (
        await db.produzioni.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    )
    # Garantisce campi attesi dal frontend
    for p in produzioni:
        if "moltiplicatore" not in p or p["moltiplicatore"] is None:
            p["moltiplicatore"] = 1.0
    return produzioni


@router.get("/stats")
async def get_stats_produzioni():
    """Statistiche aggregate delle produzioni"""
    pipeline = [
        {"$match": {"stato": {"$ne": "annullata"}}},
        {
            "$group": {
                "_id": "$ricetta_nome",
                "totale_pezzi": {"$sum": "$pezzi"},
                "totale_costo": {"$sum": "$costo_totale"},
                "num_produzioni": {"$sum": 1},
                "ultima_data": {"$max": "$data"},
            }
        },
        {"$sort": {"totale_pezzi": -1}},
        {"$limit": 20},
    ]
    result = await db.produzioni.aggregate(pipeline).to_list(20)
    # Rimuovi _id da aggregazione
    for r in result:
        r["ricetta"] = r.pop("_id", "")
    return result


@router.get("/trend")
async def get_trend_produzioni(giorni: int = 30):
    """Trend giornaliero produzioni. Le date storiche hanno formati misti
    (ISO e gg/mm/aaaa): vengono normalizzate in ISO, raggruppate e ordinate."""
    from datetime import timedelta
    from app.lotti.routers.utils import parse_data_flessibile

    inizio = (datetime.now(timezone.utc) - timedelta(days=giorni)).date()
    docs = await db.produzioni.find(
        {"stato": {"$ne": "annullata"}}, {"_id": 0, "data": 1, "pezzi": 1, "costo_totale": 1}
    ).to_list(10000)
    agg = {}
    for d in docs:
        dt = None
        try:
            dt = parse_data_flessibile(str(d.get("data", ""))[:19])
        except Exception:
            dt = None
        if dt is None:
            continue
        dd = dt.date() if hasattr(dt, "date") else dt
        if dd < inizio:
            continue
        k = dd.isoformat()
        a = agg.setdefault(k, {"pezzi": 0, "costo": 0.0, "produzioni": 0})
        a["pezzi"] += int(d.get("pezzi") or 0)
        a["costo"] += float(d.get("costo_totale") or 0)
        a["produzioni"] += 1
    return [
        {"data": k, "pezzi": v["pezzi"], "costo": round(v["costo"], 2), "produzioni": v["produzioni"]}
        for k, v in sorted(agg.items())
    ]


@router.get("/per-giorno")
async def get_produzioni_per_giorno(
    ricetta_id: Optional[str] = Query(None), giorni: int = Query(30, le=365)
):
    """Produzioni raggruppate per giorno (per grafici trend)."""
    from datetime import timedelta

    data_inizio = (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()
    match = {"data": {"$gte": data_inizio}, "stato": {"$ne": "annullata"}}
    if ricetta_id:
        match["ricetta_id"] = ricetta_id

    pipeline = [
        {"$match": match},
        {"$addFields": {"data_str": {"$substr": ["$data", 0, 10]}}},
        {
            "$group": {
                "_id": {"data": "$data_str", "ricetta": "$ricetta_nome"},
                "pezzi": {"$sum": "$pezzi"},
                "costo": {"$sum": "$costo_totale"},
                "num": {"$sum": 1},
            }
        },
        {"$sort": {"_id.data": -1}},
    ]
    rows = await db.produzioni.aggregate(pipeline).to_list(500)
    return [
        {
            "data": r["_id"]["data"],
            "ricetta": r["_id"]["ricetta"],
            "pezzi": r["pezzi"],
            "costo": round(r["costo"], 2),
            "num": r["num"],
        }
        for r in rows
    ]


@router.get("/riepilogo")
async def get_riepilogo_produzioni(giorni: int = Query(30, le=365)):
    """KPI riepilogo: totale pezzi, costo, ricette distinte, media giornaliera."""
    from datetime import timedelta

    data_inizio = (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()
    pipeline = [
        {"$match": {"data": {"$gte": data_inizio}, "stato": {"$ne": "annullata"}}},
        {
            "$group": {
                "_id": None,
                "totale_pezzi": {"$sum": "$pezzi"},
                "totale_costo": {"$sum": "$costo_totale"},
                "num_produzioni": {"$sum": 1},
                "ricette_distinte": {"$addToSet": "$ricetta_nome"},
            }
        },
    ]
    rows = await db.produzioni.aggregate(pipeline).to_list(1)
    if not rows:
        return {"totale_pezzi": 0, "totale_costo": 0, "num_produzioni": 0, "ricette_distinte": 0}
    r = rows[0]
    return {
        "totale_pezzi": r["totale_pezzi"],
        "totale_costo": round(r["totale_costo"], 2),
        "num_produzioni": r["num_produzioni"],
        "ricette_distinte": len(r["ricette_distinte"]),
    }


@router.post("/{produzione_id}/annulla")
async def annulla_produzione_route(
    produzione_id: str, body: AnnullamentoProduzione, request: Request,
    _admin=Depends(require_admin),
):
    actor = request_actor(request)
    if not actor or not actor["id"]:
        raise HTTPException(401, "Sessione dipendente richiesta")
    return await annulla_produzione(produzione_id, body.motivo.strip(), actor)
