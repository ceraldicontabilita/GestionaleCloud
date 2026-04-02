"""
Controllo Olio Frittura — HACCP
Registra giornalmente: colore, odore, test polarità, temperatura, esito, azione correttiva.
Soglia legale: olio < 175°C e polarità < 25%.
"""
from fastapi import APIRouter, HTTPException, Body
from app.routers.tracciabilita.server import db
from datetime import datetime, timezone
import uuid
import os


router = APIRouter(prefix="/controllo-olio", tags=["Controllo Olio Frittura"])

SOGLIA_POLARITA = 25.0   # %  — sopra = olio da sostituire
SOGLIA_TEMP_MAX = 175.0  # °C — sopra = fuori norma (limite legale)


def _esito(polarita, temperatura):
    """Calcola esito automatico in base ai parametri."""
    if polarita is not None and polarita >= SOGLIA_POLARITA:
        return "NON_CONFORME"
    if temperatura is not None and temperatura >= SOGLIA_TEMP_MAX:
        return "NON_CONFORME"
    return "CONFORME"


@router.get("/oggi")
async def get_controllo_olio_oggi():
    """Restituisce i controlli olio registrati oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    docs = await db.controllo_olio.find(
        {"data": oggi}, {"_id": 0}
    ).sort("ora", 1).to_list(100)
    return docs


@router.get("/storico")
async def get_storico_olio(giorni: int = 30):
    """Ultime N giorni di controlli olio."""
    from datetime import timedelta
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    docs = await db.controllo_olio.find(
        {"data": {"$gte": data_limite}}, {"_id": 0}
    ).sort("data", -1).to_list(500)
    return docs


@router.post("/registra")
async def registra_controllo_olio(payload: dict = Body(...)):
    """
    Registra un controllo olio.
    Payload: friggitrice, colore (1-5), odore_ok, polarita (%), temperatura, operatore, note
    """
    ora_utc = datetime.now(timezone.utc)
    
    polarita   = payload.get("polarita")
    temperatura = payload.get("temperatura")
    colore     = payload.get("colore", 1)        # 1=chiaro/ottimo … 5=scuro/da cambiare
    odore_ok   = payload.get("odore_ok", True)

    # Calcola esito automatico
    esito = payload.get("esito") or _esito(polarita, temperatura)
    if colore >= 4 or not odore_ok:
        esito = "NON_CONFORME"

    doc = {
        "id": str(uuid.uuid4()),
        "data": ora_utc.strftime("%Y-%m-%d"),
        "ora": ora_utc.strftime("%H:%M"),
        "friggitrice": payload.get("friggitrice", "Friggitrice 1"),
        "colore": colore,
        "odore_ok": odore_ok,
        "polarita": polarita,
        "temperatura": temperatura,
        "esito": esito,
        "azione_correttiva": payload.get("azione_correttiva", ""),
        "olio_sostituito": payload.get("olio_sostituito", False),
        "operatore": payload.get("operatore", ""),
        "note": payload.get("note", ""),
        "creato": ora_utc.isoformat()
    }

    await db.controllo_olio.insert_one({**doc})
    return {"success": True, "id": doc["id"], "esito": esito}


@router.patch("/{controllo_id}")
async def aggiorna_controllo_olio(controllo_id: str, payload: dict = Body(...)):
    """Aggiorna un controllo esistente (es. aggiunge azione correttiva)."""
    result = await db.controllo_olio.update_one(
        {"id": controllo_id},
        {"$set": {k: v for k, v in payload.items() if k not in ("id", "_id")}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Controllo non trovato")
    return {"success": True}


@router.delete("/{controllo_id}")
async def elimina_controllo_olio(controllo_id: str):
    await db.controllo_olio.delete_one({"id": controllo_id})
    return {"success": True}


@router.get("/statistiche")
async def statistiche_olio(giorni: int = 30):
    """Percentuale conformità e tendenza ultimi N giorni."""
    from datetime import timedelta
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    docs = await db.controllo_olio.find(
        {"data": {"$gte": data_limite}}, {"_id": 0}
    ).to_list(1000)
    
    totale = len(docs)
    non_conformi = sum(1 for d in docs if d.get("esito") == "NON_CONFORME")
    sostituzioni = sum(1 for d in docs if d.get("olio_sostituito"))
    
    return {
        "totale_controlli": totale,
        "conformi": totale - non_conformi,
        "non_conformi": non_conformi,
        "percentuale_conformita": round((totale - non_conformi) / totale * 100, 1) if totale else 100,
        "sostituzioni_olio": sostituzioni
    }
