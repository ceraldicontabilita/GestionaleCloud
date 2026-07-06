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

router = APIRouter(tags=["OpenAPI Imprese"])
logger = logging.getLogger(__name__)

# Token da environment
OPENAPI_TOKEN = os.environ.get("OPENAPI_COMPANY_TOKEN", "")


class UpdateFornitoreRequest(BaseModel):
    """Request per aggiornare un fornitore"""
    partita_iva: str
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
    
    # Cerca fornitore esistente nella collection "fornitori" (collection canonica dell'app)
    fornitore = await db["fornitori"].find_one({
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
    # Aggiunge anche "nome" e "denominazione" come alias di ragione_sociale per compatibilità
    if fornitore_update.get("ragione_sociale"):
        fornitore_update["nome"] = fornitore_update["ragione_sociale"]
        fornitore_update["denominazione"] = fornitore_update["ragione_sociale"]
    
    # Recupera PEC separatamente se non presente
    if not fornitore_update.get("pec"):
        pec_result = await client.get_pec(piva)
        if pec_result.get("success") and pec_result.get("pec"):
            fornitore_update["pec"] = pec_result.get("pec")
    
    fornitore_update["openapi_last_update"] = datetime.now(timezone.utc).isoformat()
    
    if fornitore:
        # Aggiorna fornitore esistente nella collection fornitori
        fornitore_update["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await db["fornitori"].update_one(
            {"_id": fornitore["_id"]},
            {"$set": fornitore_update}
        )
        
        return {
            "success": True,
            "action": "updated",
            "fornitore_id": str(fornitore.get("id", "")),
            "data_aggiornati": list(fornitore_update.keys()),
            "openapi_data": {k: v for k, v in fornitore_update.items() if k not in ("_id",)}
        }
    else:
        # Crea nuovo fornitore nella collection fornitori
        import uuid
        fornitore_update["id"] = str(uuid.uuid4())
        fornitore_update["created_at"] = datetime.now(timezone.utc).isoformat()
        fornitore_update["updated_at"] = fornitore_update["created_at"]
        fornitore_update["source"] = "openapi"
        
        await db["fornitori"].insert_one(fornitore_update)
        
        return {
            "success": True,
            "action": "created",
            "fornitore_id": fornitore_update["id"],
            "openapi_data": {k: v for k, v in fornitore_update.items() if k not in ("_id",)}
        }


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
