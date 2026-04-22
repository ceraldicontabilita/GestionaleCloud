"""
Router Auto Repair — Operazioni di riparazione automatica dati.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Query, HTTPException
from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auto Riparazione"])


@router.post("/collega-targa-driver")
async def collega_targa_driver(
    targa: str = Query(..., description="Targa veicolo"),
    driver_id: str = Query(..., description="ID dipendente/driver"),
) -> Dict[str, Any]:
    """Collega una targa a un driver nei verbali di noleggio."""
    db = Database.get_db()

    # Verifica che il dipendente esista
    dipendente = await db["dipendenti"].find_one({"id": driver_id}, {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1})
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    nome = dipendente.get("nome_completo") or f"{dipendente.get('cognome', '')} {dipendente.get('nome', '')}".strip()

    # Aggiorna tutti i verbali con questa targa che non hanno driver
    result = await db["verbali_noleggio"].update_many(
        {"targa": targa.upper(), "$or": [{"driver_id": None}, {"driver_id": ""}, {"driver_id": {"$exists": False}}]},
        {"$set": {
            "driver_id": driver_id,
            "driver_nome": nome,
            "auto_repaired": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "message": f"Targa {targa.upper()} collegata a {nome}",
        "verbali_aggiornati": result.modified_count,
    }
