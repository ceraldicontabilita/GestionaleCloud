"""
Router OpenAPI Automotive - Visure veicoli da targa
Utilizza l'API OpenAPI.com Automotive per recuperare dati veicoli
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import os
import logging

from app.database import Database
from app.services.openapi_automotive import OpenAPIAutomotive, map_automotive_to_veicolo

router = APIRouter(prefix="/openapi-automotive", tags=["OpenAPI Automotive"])
logger = logging.getLogger(__name__)

# Token da environment (stesso di Company)
OPENAPI_TOKEN = os.environ.get("OPENAPI_COMPANY_TOKEN", "")


class UpdateVeicoloRequest(BaseModel):
    """Request per aggiornare un veicolo"""
    targa: str
    force_update: bool = False


class BulkUpdateVeicoliRequest(BaseModel):
    """Request per aggiornamento massivo veicoli"""
    targhe: List[str]
    force_update: bool = False


@router.get("/status")
async def check_api_status() -> Dict[str, Any]:
    """Verifica se il token OpenAPI Automotive è configurato e funzionante."""
    token = OPENAPI_TOKEN
    
    if not token:
        return {
            "configured": False,
            "message": "Token OpenAPI non configurato"
        }
    
    # Test con targa di esempio
    client = OpenAPIAutomotive(token)
    result = await client.get_car_info("AB123CD")
    
    # La targa di test potrebbe non esistere, ma l'API dovrebbe rispondere
    return {
        "configured": True,
        "status": "OK" if result.get("success") or "non trovata" in str(result.get("error", "")).lower() else "ERROR",
        "message": "API Automotive attiva"
    }


@router.get("/info/{targa}")
async def get_info_veicolo(
    targa: str,
    token: Optional[str] = Query(None),
    tipo: str = Query("car", description="car, bike o insurance")
) -> Dict[str, Any]:
    """
    Recupera informazioni su un veicolo dalla targa.
    Non aggiorna il database, solo preview.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non configurato")
    
    targa_clean = targa.upper().replace(" ", "").replace("-", "")
    client = OpenAPIAutomotive(api_token)
    
    if tipo == "bike":
        result = await client.get_bike_info(targa_clean)
    elif tipo == "insurance":
        result = await client.get_insurance_info(targa_clean)
    else:
        result = await client.get_car_info(targa_clean)
    
    if result.get("success"):
        return {
            "success": True,
            "targa": targa_clean,
            "tipo": tipo,
            "data": result.get("data", {}),
            "campi_mappati": map_automotive_to_veicolo(result.get("data", {}))
        }
    else:
        raise HTTPException(status_code=404, detail=result.get("error", "Targa non trovata"))


@router.post("/aggiorna-veicolo")
async def aggiorna_veicolo(
    request: UpdateVeicoloRequest,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Aggiorna un veicolo nella flotta noleggio con i dati da OpenAPI Automotive.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non configurato")
    
    targa = request.targa.upper().replace(" ", "").replace("-", "")
    
    db = Database.get_db()
    
    # Cerca veicolo esistente
    veicolo = await db.noleggio_veicoli.find_one({
        "$or": [
            {"targa": targa},
            {"targa": {"$regex": targa, "$options": "i"}}
        ]
    })
    
    # Chiama OpenAPI Automotive
    client = OpenAPIAutomotive(api_token)
    result = await client.get_car_info(targa)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Targa non trovata"))
    
    # Mappa dati
    auto_data = result.get("data", {})
    veicolo_update = map_automotive_to_veicolo(auto_data)
    
    if veicolo:
        # Aggiorna veicolo esistente
        veicolo_update["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.noleggio_veicoli.update_one(
            {"_id": veicolo["_id"]},
            {"$set": veicolo_update}
        )
        
        return {
            "success": True,
            "action": "updated",
            "veicolo_id": str(veicolo.get("id", veicolo.get("_id"))),
            "data_aggiornati": list(veicolo_update.keys()),
            "automotive_data": veicolo_update
        }
    else:
        # Crea nuovo veicolo
        import uuid
        veicolo_update["id"] = str(uuid.uuid4())
        veicolo_update["created_at"] = datetime.now(timezone.utc).isoformat()
        veicolo_update["updated_at"] = veicolo_update["created_at"]
        veicolo_update["stato"] = "attivo"
        veicolo_update["source"] = "openapi_automotive"
        
        await db.noleggio_veicoli.insert_one(veicolo_update)
        
        return {
            "success": True,
            "action": "created",
            "veicolo_id": veicolo_update["id"],
            "automotive_data": veicolo_update
        }


@router.post("/aggiorna-bulk")
async def aggiorna_veicoli_bulk(
    request: BulkUpdateVeicoliRequest,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Aggiorna più veicoli in batch."""
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non configurato")
    
    results = {
        "totale": len(request.targhe),
        "aggiornati": 0,
        "creati": 0,
        "errori": 0,
        "dettagli": []
    }
    
    client = OpenAPIAutomotive(api_token)
    db = Database.get_db()
    
    for targa in request.targhe:
        targa_clean = targa.upper().replace(" ", "").replace("-", "")
        
        try:
            result = await client.get_car_info(targa_clean)
            
            if result.get("success"):
                auto_data = result.get("data", {})
                veicolo_update = map_automotive_to_veicolo(auto_data)
                veicolo_update["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                # Upsert
                update_result = await db.noleggio_veicoli.update_one(
                    {"targa": {"$regex": f"^{targa_clean}$", "$options": "i"}},
                    {"$set": veicolo_update},
                    upsert=True
                )
                
                if update_result.upserted_id:
                    results["creati"] += 1
                    results["dettagli"].append({
                        "targa": targa_clean, 
                        "status": "created",
                        "marca": veicolo_update.get("marca"),
                        "modello": veicolo_update.get("modello")
                    })
                else:
                    results["aggiornati"] += 1
                    results["dettagli"].append({
                        "targa": targa_clean, 
                        "status": "updated",
                        "marca": veicolo_update.get("marca"),
                        "modello": veicolo_update.get("modello")
                    })
            else:
                results["errori"] += 1
                results["dettagli"].append({
                    "targa": targa_clean,
                    "status": "error",
                    "error": result.get("error")
                })
                
        except Exception as e:
            results["errori"] += 1
            results["dettagli"].append({
                "targa": targa_clean,
                "status": "error",
                "error": str(e)
            })
    
    return results


@router.get("/veicoli-da-aggiornare")
async def get_veicoli_da_aggiornare(
    limit: int = Query(100)
) -> Dict[str, Any]:
    """Lista veicoli nella flotta che non hanno dati OpenAPI."""
    db = Database.get_db()
    
    veicoli = await db.noleggio_veicoli.find({
        "targa": {"$exists": True, "$ne": None, "$ne": ""},
        "openapi_last_update": {"$exists": False}
    }, {"_id": 0, "id": 1, "targa": 1, "marca": 1, "modello": 1}).limit(limit).to_list(length=limit)
    
    return {
        "count": len(veicoli),
        "veicoli": veicoli
    }


@router.get("/assicurazione/{targa}")
async def get_assicurazione_veicolo(
    targa: str,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Recupera informazioni sull'assicurazione di un veicolo."""
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non configurato")
    
    targa_clean = targa.upper().replace(" ", "").replace("-", "")
    client = OpenAPIAutomotive(api_token)
    result = await client.get_insurance_info(targa_clean)
    
    if result.get("success"):
        return {
            "success": True,
            "targa": targa_clean,
            "assicurazione": result.get("data", {})
        }
    else:
        raise HTTPException(status_code=404, detail=result.get("error"))
