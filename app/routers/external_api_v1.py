"""API pubblica v1 per integrazioni esterne.

Separata dal vecchio public_api in Fase 0C. Gli URL restano /api/v1/*.
"""
from datetime import datetime, timezone
import hashlib
import logging
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


async def richiedi_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="DEPRECATO: usare l'header X-API-Key"),
) -> Dict[str, Any]:
    """Autenticazione API pubblica v1. Preferisce l'header `X-API-Key`; accetta
    ancora la query `?api_key=` per retrocompatibilità ma è SCONSIGLIATA (finisce
    nei log/URL). Il valore della chiave non viene mai loggato. Vedi P0.12."""
    chiave = x_api_key or api_key
    if not chiave:
        raise HTTPException(status_code=401, detail="API Key mancante (usare header X-API-Key)")
    if not x_api_key and api_key:
        logger.warning("API v1: chiave passata via query string (deprecato) — usare header X-API-Key")
    return await verify_api_key_header(chiave)


async def verify_api_key_header(x_api_key: str) -> Dict[str, Any]:
    """Verifica API Key e restituisce info client."""
    db = Database.get_db()
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    
    api_client = await db["api_clients"].find_one(
        {"key_hash": key_hash, "active": True},
        {"_id": 0}
    )
    
    if not api_client:
        raise HTTPException(status_code=401, detail="API Key non valida")
    
    await db["api_clients"].update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}, "$inc": {"request_count": 1}}
    )
    
    return api_client


@router.post("/v1/keys/generate")
async def api_genera_key(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Genera nuova API Key per integrazioni esterne."""
    db = Database.get_db()
    
    api_key = f"ak_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    client_doc = {
        "id": f"client_{secrets.token_hex(8)}",
        "nome": data.get("nome", "Client API"),
        "key_hash": key_hash,
        "key_prefix": api_key[:12],
        "permessi": data.get("permessi", ["read"]),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_count": 0
    }
    
    await db["api_clients"].insert_one(dict(client_doc).copy())
    
    return {
        "success": True,
        "api_key": api_key,
        "client_id": client_doc["id"],
        "nota": "Salva questa API Key, non sarà più visualizzabile!"
    }


@router.get("/v1/keys")
async def api_lista_keys() -> Dict[str, Any]:
    """Lista API Keys (senza mostrare le key complete)."""
    db = Database.get_db()
    clients = await db["api_clients"].find({}, {"_id": 0, "key_hash": 0}).to_list(100)
    return {"clients": clients}


@router.get("/v1/fatture")
async def api_v1_fatture(
    tipo: str = Query("ricevute"),
    anno: Optional[int] = None,
    limit: int = Query(100, le=500),
    _client: Dict[str, Any] = Depends(richiedi_api_key),
) -> Dict[str, Any]:
    """API pubblica - Lista fatture. Autenticazione via header X-API-Key."""
    
    db = Database.get_db()
    collection = "fatture_ricevute" if tipo == "ricevute" else "fatture_emesse"
    
    query = {}
    if anno:
        query["$or"] = [
            {"data_fattura": {"$regex": f"^{anno}"}},
            {"data_ricezione": {"$regex": f"^{anno}"}}
        ]
    
    fatture = await db[collection].find(query, {"_id": 0}).limit(limit).to_list(limit)
    return {"data": fatture, "total": len(fatture)}


@router.get("/v1/movimenti")
async def api_v1_movimenti(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    limit: int = Query(100, le=500),
    _client: Dict[str, Any] = Depends(richiedi_api_key),
) -> Dict[str, Any]:
    """API pubblica - Lista movimenti prima nota. Auth via header X-API-Key."""
    
    db = Database.get_db()
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    movimenti = await db["prima_nota_cassa"].find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    return {"data": movimenti, "total": len(movimenti)}


@router.get("/v1/stats")
async def api_v1_stats(
    anno: int = Query(...),
    _client: Dict[str, Any] = Depends(richiedi_api_key),
) -> Dict[str, Any]:
    """API pubblica - Statistiche aggregate. Auth via header X-API-Key."""
    
    db = Database.get_db()
    
    return {
        "anno": anno,
        "fatture_ricevute": await db["invoices"].count_documents({"data_ricezione": {"$regex": f"^{anno}"}}),
        "fatture_emesse": await db["fatture_emesse"].count_documents({"data_fattura": {"$regex": f"^{anno}"}}),
        "movimenti": await db["prima_nota_cassa"].count_documents({"data": {"$regex": f"^{anno}"}}),
        "dipendenti_attivi": await db["dipendenti"].count_documents({"stato": {"$in": ["active", "attivo"]}})
    }
