"""
Router OpenAPI Company - Aggiornamento automatico schede fornitore
Utilizza l'API OpenAPI.com Company per recuperare dati anagrafici aggiornati
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import os
import logging

from app.database import Database
from app.services.openapi_company import OpenAPICompany, map_company_to_fornitore

router = APIRouter(prefix="/openapi-imprese", tags=["OpenAPI Imprese"])
logger = logging.getLogger(__name__)

# Token da environment
OPENAPI_TOKEN = os.environ.get("OPENAPI_COMPANY_TOKEN", "")


class UpdateFornitoreRequest(BaseModel):
    """Request per aggiornare un fornitore"""
    partita_iva: str
    force_update: bool = False


class BulkUpdateRequest(BaseModel):
    """Request per aggiornamento massivo"""
    partite_iva: List[str]
    force_update: bool = False


@router.get("/status")
async def check_api_status() -> Dict[str, Any]:
    """
    Verifica se il token OpenAPI è configurato e funzionante.
    """
    token = OPENAPI_TOKEN
    
    if not token:
        return {
            "configured": False,
            "message": "Token OpenAPI non configurato. Imposta OPENAPI_COMPANY_TOKEN in .env"
        }
    
    # Test con una P.IVA di esempio (OpenAPI stessa)
    client = OpenAPICompany(token)
    result = await client.get_start_info("12485671007")
    
    if result.get("success"):
        return {
            "configured": True,
            "status": "OK",
            "test_company": result.get("data", {}).get("companyName"),
            "message": "Connessione API verificata"
        }
    else:
        return {
            "configured": True,
            "status": "ERROR",
            "error": result.get("error", "Errore sconosciuto")
        }


@router.post("/aggiorna-fornitore")
async def aggiorna_fornitore(
    request: UpdateFornitoreRequest,
    token: Optional[str] = Query(None, description="Token OpenAPI (opzionale se configurato in env)")
) -> Dict[str, Any]:
    """
    Aggiorna la scheda di un fornitore con dati da OpenAPI Company.
    
    Recupera: ragione sociale, indirizzo, PEC, codice SDI, ATECO, fatturato, dipendenti
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(
            status_code=400,
            detail="Token OpenAPI non fornito. Passalo come query param o configura OPENAPI_COMPANY_TOKEN"
        )
    
    piva = request.partita_iva.strip().replace(" ", "")
    
    # Valida P.IVA
    if len(piva) != 11 or not piva.isdigit():
        raise HTTPException(status_code=400, detail="Partita IVA non valida (deve essere 11 cifre)")
    
    db = Database.get_db()
    
    # Cerca fornitore esistente
    fornitore = await db.fornitori.find_one({
        "$or": [
            {"partita_iva": piva},
            {"piva": piva},
            {"codice_fiscale": piva}
        ]
    })
    
    # Chiama OpenAPI Company
    client = OpenAPICompany(api_token)
    
    # Prima prova IT-advanced per dati completi, fallback su IT-start
    result = await client.get_advanced_info(piva)
    if not result.get("success"):
        result = await client.get_start_info(piva)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=404,
            detail=f"Errore OpenAPI: {result.get('error', 'Partita IVA non trovata')}"
        )
    
    # Mappa dati
    company_data = result.get("data", {})
    fornitore_update = map_company_to_fornitore(company_data)
    
    # Recupera PEC separatamente se non presente
    if not fornitore_update.get("pec"):
        pec_result = await client.get_pec(piva)
        if pec_result.get("success") and pec_result.get("pec"):
            fornitore_update["pec"] = pec_result.get("pec")
    
    if fornitore:
        # Aggiorna fornitore esistente
        fornitore_update["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.fornitori.update_one(
            {"_id": fornitore["_id"]},
            {"$set": fornitore_update}
        )
        
        return {
            "success": True,
            "action": "updated",
            "fornitore_id": str(fornitore.get("id", fornitore.get("_id"))),
            "data_aggiornati": list(fornitore_update.keys()),
            "openapi_data": fornitore_update
        }
    else:
        # Crea nuovo fornitore
        import uuid
        fornitore_update["id"] = str(uuid.uuid4())
        fornitore_update["created_at"] = datetime.now(timezone.utc).isoformat()
        fornitore_update["updated_at"] = fornitore_update["created_at"]
        fornitore_update["source"] = "openapi"
        
        await db.fornitori.insert_one(fornitore_update)
        
        return {
            "success": True,
            "action": "created",
            "fornitore_id": fornitore_update["id"],
            "openapi_data": fornitore_update
        }


@router.post("/aggiorna-bulk")
async def aggiorna_fornitori_bulk(
    request: BulkUpdateRequest,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Aggiorna più fornitori in batch.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non fornito")
    
    results = {
        "totale": len(request.partite_iva),
        "aggiornati": 0,
        "creati": 0,
        "errori": 0,
        "dettagli": []
    }
    
    client = OpenAPICompany(api_token)
    db = Database.get_db()
    
    for piva in request.partite_iva:
        piva = piva.strip().replace(" ", "")
        
        try:
            result = await client.get_start_info(piva)
            
            if result.get("success"):
                company_data = result.get("data", {})
                fornitore_update = map_company_to_fornitore(company_data)
                fornitore_update["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                # Upsert
                update_result = await db.fornitori.update_one(
                    {"$or": [{"partita_iva": piva}, {"piva": piva}]},
                    {"$set": fornitore_update},
                    upsert=True
                )
                
                if update_result.upserted_id:
                    results["creati"] += 1
                    results["dettagli"].append({"piva": piva, "status": "created"})
                else:
                    results["aggiornati"] += 1
                    results["dettagli"].append({"piva": piva, "status": "updated"})
            else:
                results["errori"] += 1
                results["dettagli"].append({
                    "piva": piva, 
                    "status": "error", 
                    "error": result.get("error")
                })
                
        except Exception as e:
            results["errori"] += 1
            results["dettagli"].append({"piva": piva, "status": "error", "error": str(e)})
    
    return results


@router.get("/cerca")
async def cerca_azienda(
    query: str = Query(..., description="Nome azienda (parziale)"),
    provincia: Optional[str] = Query(None, description="Codice provincia (es: RM, MI)"),
    limit: int = Query(10, description="Numero massimo risultati"),
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Cerca un'azienda per nome usando l'API OpenAPI Company.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non fornito")
    
    client = OpenAPICompany(api_token)
    result = await client.search_company(company_name=query, provincia=provincia, limit=limit)
    
    if result.get("success"):
        return {
            "success": True,
            "query": query,
            "count": len(result.get("results", [])),
            "results": result.get("results", [])
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@router.get("/info/{partita_iva}")
async def get_info_azienda(
    partita_iva: str,
    token: Optional[str] = Query(None),
    tipo: str = Query("advanced", description="start, advanced o full")
) -> Dict[str, Any]:
    """
    Recupera informazioni su un'azienda senza aggiornare il database.
    Utile per preview prima di aggiornare.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non fornito")
    
    piva = partita_iva.strip().replace(" ", "")
    client = OpenAPICompany(api_token)
    
    if tipo == "start":
        result = await client.get_start_info(piva)
    elif tipo == "full":
        result = await client.get_full_info(piva)
    else:
        result = await client.get_advanced_info(piva)
    
    if result.get("success"):
        return {
            "success": True,
            "partita_iva": piva,
            "data": result.get("data", {}),
            "campi_mappati": map_company_to_fornitore(result.get("data", {}))
        }
    else:
        raise HTTPException(status_code=404, detail=result.get("error"))


@router.get("/pec/{partita_iva}")
async def get_pec_azienda(
    partita_iva: str,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Recupera solo la PEC di un'azienda.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non fornito")
    
    piva = partita_iva.strip().replace(" ", "")
    client = OpenAPICompany(api_token)
    result = await client.get_pec(piva)
    
    if result.get("success"):
        return {"success": True, "partita_iva": piva, "pec": result.get("pec")}
    else:
        raise HTTPException(status_code=404, detail=result.get("error"))


@router.get("/sdi/{partita_iva}")
async def get_sdi_azienda(
    partita_iva: str,
    token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Recupera il Codice Destinatario SDI di un'azienda.
    """
    api_token = token or OPENAPI_TOKEN
    
    if not api_token:
        raise HTTPException(status_code=400, detail="Token OpenAPI non fornito")
    
    piva = partita_iva.strip().replace(" ", "")
    client = OpenAPICompany(api_token)
    result = await client.get_sdi_code(piva)
    
    if result.get("success"):
        return {"success": True, "partita_iva": piva, "codice_sdi": result.get("codice_sdi")}
    else:
        raise HTTPException(status_code=404, detail=result.get("error"))


@router.get("/fornitori-da-aggiornare")
async def get_fornitori_da_aggiornare(
    limit: int = Query(100)
) -> Dict[str, Any]:
    """
    Lista fornitori che necessitano aggiornamento da OpenAPI.
    """
    db = Database.get_db()
    
    # Fornitori con P.IVA ma senza dati OpenAPI
    fornitori = await db.fornitori.find({
        "$or": [
            {"partita_iva": {"$exists": True, "$ne": None, "$ne": ""}},
            {"piva": {"$exists": True, "$ne": None, "$ne": ""}}
        ],
        "openapi_last_update": {"$exists": False}
    }, {"_id": 0, "id": 1, "ragione_sociale": 1, "partita_iva": 1, "piva": 1}).limit(limit).to_list(length=limit)
    
    return {
        "count": len(fornitori),
        "fornitori": [
            {
                "id": f.get("id"),
                "ragione_sociale": f.get("ragione_sociale", "N/A"),
                "partita_iva": f.get("partita_iva") or f.get("piva")
            }
            for f in fornitori
        ]
    }
