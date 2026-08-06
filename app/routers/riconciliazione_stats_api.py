"""
Router Riconciliazione Stats — Gestionale Ceraldi Group
========================================================
Endpoint statistiche per la dashboard relazionale.
"""
from fastapi import APIRouter
from typing import Dict, Any
import logging
from datetime import datetime, timezone

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/riconciliazione", tags=["Riconciliazione"])

COLL_MATCH = "riconciliazioni_match"


@router.get("/stats")
async def stats_riconciliazione() -> Dict[str, Any]:
    """Statistiche vive, non una fotografia della sola tabella dei match."""
    db = Database.get_db()

    from app.services.riconciliazione_kpi import calcola_contatori_movimenti

    movimenti = await db["estratto_conto_movimenti"].find(
        {}, {"_id": 0, "id": 1, "importo": 1, "riconciliato": 1}
    ).to_list(50000)
    banca = calcola_contatori_movimenti(movimenti)

    proposte_aperte = await db["operazioni_da_confermare"].count_documents({
        "stato": "da_confermare"
    })
    partite_aperte = await db["partite_aperte"].count_documents({
        "stato": {"$in": ["aperta", "parziale"]}
    })
    partite_chiuse = await db["partite_aperte"].count_documents({"stato": "chiusa"})

    pipeline = [
        {"$group": {
            "_id": "$stato",
            "count": {"$sum": 1},
            "totale": {"$sum": "$importo_riconciliato"}
        }},
        {"$sort": {"count": -1}}
    ]

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
    }
