"""
Temperature Cottura — HACCP
Registra temperature al cuore raggiunte durante cottura.
Soglia legale: ≥ +75°C al cuore (≥ +70°C per abbattimento controllato).
"""
from fastapi import APIRouter, HTTPException, Body
from app.routers.tracciabilita.server import db
from datetime import datetime, timezone
import uuid
import os


router = APIRouter(prefix="/temperature-cottura", tags=["Temperature Cottura"])

SOGLIA_MIN_COTTURA = 75.0   # °C al cuore — valore legale standard
SOGLIA_MIN_ABBATTIMENTO = 70.0  # °C per cottura + abbattimento immediato


@router.get("/oggi")
async def get_temp_cottura_oggi():
    """Temperature cottura registrate oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    docs = await db.temperature_cottura.find(
        {"data": oggi}, {"_id": 0}
    ).sort("ora", 1).to_list(200)
    return docs


@router.get("/storico")
async def get_storico_cottura(giorni: int = 30):
    from datetime import timedelta
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    docs = await db.temperature_cottura.find(
        {"data": {"$gte": data_limite}}, {"_id": 0}
    ).sort("data", -1).to_list(1000)
    return docs


@router.post("/registra")
async def registra_temperatura_cottura(payload: dict = Body(...)):
    """
    Registra una misurazione di temperatura cottura.
    Payload: prodotto, ricetta_id, temperatura_cuore, tipo_cottura, operatore, note
    tipo_cottura: forno | pentola | friggitrice | vapore | griglia | altro
    """
    ora_utc = datetime.now(timezone.utc)
    temperatura = float(payload.get("temperatura_cuore", 0))
    abbattimento_immediato = payload.get("abbattimento_immediato", False)
    
    soglia = SOGLIA_MIN_ABBATTIMENTO if abbattimento_immediato else SOGLIA_MIN_COTTURA
    conforme = temperatura >= soglia
    
    doc = {
        "id": str(uuid.uuid4()),
        "data": ora_utc.strftime("%Y-%m-%d"),
        "ora": ora_utc.strftime("%H:%M"),
        "prodotto": payload.get("prodotto", ""),
        "ricetta_id": payload.get("ricetta_id"),
        "tipo_cottura": payload.get("tipo_cottura", "forno"),
        "temperatura_cuore": temperatura,
        "soglia_applicata": soglia,
        "conforme": conforme,
        "abbattimento_immediato": abbattimento_immediato,
        "azione_correttiva": payload.get("azione_correttiva", "") if not conforme else "",
        "operatore": payload.get("operatore", ""),
        "note": payload.get("note", ""),
        "creato": ora_utc.isoformat()
    }

    await db.temperature_cottura.insert_one({**doc})
    return {"success": True, "id": doc["id"], "conforme": conforme, "soglia": soglia}


@router.patch("/{cottura_id}")
async def aggiorna_temperatura_cottura(cottura_id: str, payload: dict = Body(...)):
    result = await db.temperature_cottura.update_one(
        {"id": cottura_id},
        {"$set": {k: v for k, v in payload.items() if k not in ("id", "_id")}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Registrazione non trovata")
    return {"success": True}


@router.delete("/{cottura_id}")
async def elimina_temperatura_cottura(cottura_id: str):
    await db.temperature_cottura.delete_one({"id": cottura_id})
    return {"success": True}


@router.get("/statistiche")
async def statistiche_cottura(giorni: int = 30):
    from datetime import timedelta
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    docs = await db.temperature_cottura.find(
        {"data": {"$gte": data_limite}}, {"_id": 0}
    ).to_list(1000)
    
    totale = len(docs)
    non_conformi = sum(1 for d in docs if not d.get("conforme", True))
    
    return {
        "totale_registrazioni": totale,
        "conformi": totale - non_conformi,
        "non_conformi": non_conformi,
        "percentuale_conformita": round((totale - non_conformi) / totale * 100, 1) if totale else 100,
    }
