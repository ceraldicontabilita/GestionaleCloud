"""
Router Riconciliazione Stats — Gestionale Ceraldi Group
========================================================
Endpoint statistiche per la dashboard relazionale.
"""
from fastapi import APIRouter, Query
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timezone

from app.database import Database
from app.utils.mongo_year import combina_filtri, filtro_anno_mongo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/riconciliazione", tags=["Riconciliazione"])

COLL_MATCH = "riconciliazioni_match"


@router.get("/stats")
async def stats_riconciliazione(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
) -> Dict[str, Any]:
    """Statistiche vive, non una fotografia della sola tabella dei match."""
    db = Database.get_db()

    from app.services.riconciliazione_kpi import calcola_contatori_movimenti

    filtro_movimenti = filtro_anno_mongo(
        anno,
        ("data", "data_contabile", "data_operazione"),
    )
    movimenti = await db["estratto_conto_movimenti"].find(
        filtro_movimenti,
        {"_id": 0, "id": 1, "importo": 1, "riconciliato": 1},
    ).to_list(50000)
    banca = calcola_contatori_movimenti(movimenti)

    filtro_proposte = filtro_anno_mongo(
        anno,
        ("data", "data_operazione"),
    )
    filtro_partite = filtro_anno_mongo(
        anno,
        ("data_documento", "data_scadenza", "data"),
    )

    proposte_aperte = await db["operazioni_da_confermare"].count_documents(
        combina_filtri({"stato": "da_confermare"}, filtro_proposte)
    )
    partite_aperte = await db["partite_aperte"].count_documents(
        combina_filtri(
            {"stato": {"$in": ["aperta", "parziale"]}},
            filtro_partite,
        )
    )
    partite_chiuse = await db["partite_aperte"].count_documents(
        combina_filtri({"stato": "chiusa"}, filtro_partite)
    )

    pipeline = []
    if anno is not None:
        movimento_ids = [m.get("id") for m in movimenti if m.get("id")]
        pipeline.append({"$match": {"movimento_id": {"$in": movimento_ids}}})
    pipeline.extend([
        {"$group": {
            "_id": "$stato",
            "count": {"$sum": 1},
            "totale": {"$sum": "$importo_riconciliato"}
        }},
        {"$sort": {"count": -1}}
    ])

    match_per_stato = {}
    async for doc in db[COLL_MATCH].aggregate(pipeline):
        if doc["_id"]:
            match_per_stato[doc["_id"]] = {
                "count": doc["count"],
                "totale": round(doc.get("totale") or 0, 2)
            }

    return {
        "stati": {
            "da_riconciliare": {
                "count": banca["da_riconciliare"],
                "totale": banca["importo_da_riconciliare"],
            },
            "riconciliati": {
                "count": banca["riconciliati"],
                "totale": banca["importo_riconciliato"],
            },
            "da_confermare": {"count": proposte_aperte, "totale": 0},
        },
        "sezioni": {
            "estratto_conto": banca,
            "partite": {
                "aperte_o_parziali": partite_aperte,
                "chiuse": partite_chiuse,
                "totale": partite_aperte + partite_chiuse,
            },
            "match": match_per_stato,
        },
        "quadratura": {
            "ok": banca["quadratura_ok"],
            "formula": "totale = riconciliati + da_riconciliare",
            "valori": f"{banca['totale']} = {banca['riconciliati']} + {banca['da_riconciliare']}",
        },
        "aggiornato_il": datetime.now(timezone.utc).isoformat(),
        "anno": anno,
    }
