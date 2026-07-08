"""
OpenAPI.it Integration Module
Integrazione con le API di OpenAPI.it per:
- AISP (Open Banking - Riconciliazione Bancaria)
- XBRL (Bilanci Camera di Commercio)
- Visure Camerali

Documentazione: https://console.openapi.com/it
"""
import os
import base64
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.database import Database
from app.models.stati import STATI_PAGATI

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurazione
OPENAPI_BASE_URL = "https://sdi.openapi.it"  # Sandbox SDI
OPENAPI_BASE_URL_PROD = "https://sdi.openapi.com"  # Produzione SDI
VISURE_BASE_URL = "https://test.visurecamerali.openapi.it"  # Sandbox Visure
VISURE_BASE_URL_PROD = "https://visurecamerali.openapi.it"  # Produzione Visure
OPENAPI_KEY = os.environ.get("OPENAPI_IT_KEY", "")
OPENAPI_ENV = os.environ.get("OPENAPI_IT_ENV", "sandbox")

# Headers standard
def get_headers():
    return {
        "Authorization": f"Bearer {OPENAPI_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def get_base_url():
    return OPENAPI_BASE_URL if OPENAPI_ENV == "sandbox" else OPENAPI_BASE_URL_PROD

def get_visure_url():
    return VISURE_BASE_URL if OPENAPI_ENV == "sandbox" else VISURE_BASE_URL_PROD


# ============================================================
# MODELLI PYDANTIC
# ============================================================

class BilancioXBRLRequest(BaseModel):
    """Richiesta bilancio XBRL"""
    partita_iva: str
    anno_chiusura: Optional[int] = None  # Se None, prende l'ultimo disponibile


class BankAccountConnect(BaseModel):
    """Modello per connessione conto bancario AISP"""
    bank_code: str
    iban: str
    consent_id: Optional[str] = None


# ============================================================
# AISP - OPEN BANKING (Riconciliazione Bancaria)
# ============================================================

@router.get("/aisp/status")
async def get_aisp_status() -> Dict[str, Any]:
    """
    Verifica lo stato del servizio AISP (Open Banking).
    """
    return {
        "status": "available",
        "description": "Servizio AISP per riconciliazione bancaria automatica",
        "features": [
            "Lettura movimenti bancari in tempo reale",
            "Aggregazione multi-banca",
            "Riconciliazione automatica con fatture",
            "Categorizzazione movimenti"
        ],
        "requirements": [
            "Consenso utente PSD2",
            "Autorizzazione AISP attiva su OpenAPI.it",
            "Configurazione IBAN conti da monitorare"
        ],
        "note": "Per attivare l'AISP è necessario completare la procedura di autorizzazione PSD2 su console.openapi.com"
    }


@router.post("/aisp/connetti-conto")
async def connetti_conto_bancario(data: BankAccountConnect) -> Dict[str, Any]:
    """
    Connette un conto bancario tramite AISP per la riconciliazione automatica.
    Richiede consenso utente PSD2.
    """
    db = Database.get_db()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Richiedi consenso
            response = await client.post(
                f"{get_base_url()}/v1/aisp/consents",
                headers=get_headers(),
                json={
                    "iban": data.iban,
                    "bank_code": data.bank_code,
                    "access_type": "accounts",
                    "recurring_indicator": True,
                    "valid_until": "2027-12-31"
                }
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                
                # Salva configurazione conto
                await db.conti_bancari_aisp.update_one(
                    {"iban": data.iban},
                    {"$set": {
                        "iban": data.iban,
                        "bank_code": data.bank_code,
                        "consent_id": result.get("consent_id"),
                        "consent_status": result.get("status"),
                        "consent_url": result.get("authorization_url"),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }},
                    upsert=True
                )
                
                return {
                    "status": "consent_required",
                    "consent_id": result.get("consent_id"),
                    "authorization_url": result.get("authorization_url"),
                    "message": "Clicca sul link per autorizzare l'accesso al conto"
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Errore richiesta consenso AISP"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore AISP: {e}")
        raise HTTPException(status_code=500, detail=f"Errore connessione AISP: {str(e)}")


@router.get("/aisp/movimenti")
async def get_movimenti_bancari(
    iban: str = Query(...),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Recupera i movimenti bancari tramite AISP.
    """
    db = Database.get_db()
    
    # Verifica consenso attivo
    conto = await db.conti_bancari_aisp.find_one({"iban": iban})
    if not conto or conto.get("consent_status") != "valid":
        raise HTTPException(
            status_code=400,
            detail="Consenso AISP non valido. Riconnettere il conto."
        )
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            params = {"iban": iban}
            if from_date:
                params["from_date"] = from_date
            if to_date:
                params["to_date"] = to_date
            
            response = await client.get(
                f"{get_base_url()}/v1/aisp/accounts/{iban}/transactions",
                headers={
                    **get_headers(),
                    "Consent-ID": conto.get("consent_id")
                },
                params=params
            )
            
            if response.status_code == 200:
                movimenti = response.json().get("transactions", [])
                
                return {
                    "status": "success",
                    "iban": iban,
                    "movimenti": movimenti,
                    "count": len(movimenti)
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore recupero movimenti AISP"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore AISP movimenti: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aisp/riconcilia-automatica")
async def riconcilia_automatica_aisp(iban: str = Query(...)) -> Dict[str, Any]:
    """
    Esegue la riconciliazione automatica tra movimenti AISP e fatture/assegni.
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "movimenti_processati": 0,
        "riconciliazioni_trovate": 0,
        "dettagli": []
    }
    
    try:
        # Recupera movimenti AISP
        movimenti_resp = await get_movimenti_bancari(iban=iban)
        movimenti = movimenti_resp.get("movimenti", [])
        
        risultato["movimenti_processati"] = len(movimenti)
        
        for mov in movimenti:
            importo = abs(float(mov.get("amount", 0)))
            descrizione = mov.get("description", "")
            data = mov.get("booking_date")
            
            # Cerca match in fatture
            fattura = await db.invoices.find_one({
                "total_amount": {"$gte": importo - 1, "$lte": importo + 1},
                "status": {"$nin": STATI_PAGATI}
            })
            
            if fattura:
                # Aggiorna fattura come pagata
                await db.invoices.update_one(
                    {"id": fattura.get("id")},
                    {"$set": {
                        "status": "pagata",
                        "data_pagamento": data,
                        "movimento_aisp_id": mov.get("transaction_id"),
                        "riconciliazione_automatica": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                risultato["riconciliazioni_trovate"] += 1
                risultato["dettagli"].append({
                    "movimento": descrizione[:50],
                    "importo": importo,
                    "fattura": fattura.get("invoice_number"),
                    "fornitore": fattura.get("supplier_name", "")[:30]
                })
        
        return risultato
        
    except Exception as e:
        logger.error(f"Errore riconciliazione AISP: {e}")
        risultato["error"] = str(e)
        return risultato


# ============================================================
# XBRL - BILANCI CAMERA DI COMMERCIO
# ============================================================

@router.get("/xbrl/status")
async def get_xbrl_status() -> Dict[str, Any]:
    """
    Verifica lo stato del servizio XBRL/Bilanci.
    """
    return {
        "status": "available",
        "api_key_configured": bool(OPENAPI_KEY),
        "environment": OPENAPI_ENV,
        "base_url": get_visure_url(),
        "description": "Servizio per recupero bilanci XBRL dalla Camera di Commercio",
        "features": [
            "Bilancio Ottico (PDF ufficiale)",
            "Bilancio XBRL (formato elettronico)",
            "Verbale Assemblea Soci",
            "Bilancio Riclassificato con indici"
        ],
        "tassonomia": "2018-11-04 (obbligatoria dal 2020)",
        "costo_stimato": "€2.95 - €4.50 per bilancio"
    }


@router.post("/xbrl/richiedi-bilancio")
async def richiedi_bilancio_xbrl(data: BilancioXBRLRequest) -> Dict[str, Any]:
    """
    Richiede il bilancio XBRL di un'azienda dalla Camera di Commercio.
    
    Il bilancio viene recuperato in 10-15 minuti.
    Usa GET /xbrl/bilancio/{request_id} per verificare lo stato.
    """
    db = Database.get_db()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "cf_piva_id": data.partita_iva
            }
            
            if data.anno_chiusura:
                payload["anno_chiusura"] = data.anno_chiusura
            
            response = await client.post(
                f"{get_visure_url()}/bilancio-ottico",
                headers=get_headers(),
                json=payload
            )
            
            if response.status_code in [200, 201, 202]:
                result = response.json()
                request_id = result.get("id")
                
                # Salva richiesta nel database
                await db.richieste_bilanci.insert_one({
                    "id": request_id,
                    "partita_iva": data.partita_iva,
                    "anno_chiusura": data.anno_chiusura,
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                
                return {
                    "status": "pending",
                    "request_id": request_id,
                    "message": "Richiesta inviata. Il bilancio sarà disponibile in 10-15 minuti.",
                    "check_url": f"/api/openapi/xbrl/bilancio/{request_id}"
                }
            else:
                error_detail = response.json() if response.content else {"error": response.status_code}
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Errore richiesta bilancio: {error_detail}"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore HTTP richiesta XBRL: {e}")
        raise HTTPException(status_code=500, detail=f"Errore connessione: {str(e)}")


@router.get("/xbrl/bilancio/{request_id}")
async def get_bilancio_xbrl(request_id: str) -> Dict[str, Any]:
    """
    Recupera lo stato e il contenuto del bilancio XBRL richiesto.
    """
    db = Database.get_db()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{get_visure_url()}/bilancio-ottico/{request_id}",
                headers=get_headers()
            )
            
            if response.status_code == 200:
                result = response.json()
                status = result.get("status")
                
                # Aggiorna database
                await db.richieste_bilanci.update_one(
                    {"id": request_id},
                    {"$set": {
                        "status": status,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                if status == "completed":
                    # Bilancio disponibile: il documento salvato in richieste_bilanci
                    # deve esporre "download_url" (letto dalla tabella "Richieste
                    # Recenti" del frontend per mostrare il pulsante Download) —
                    # prima non veniva mai scritto, quindi il pulsante non compariva.
                    ha_file = bool(
                        result.get("pdf_base64") or result.get("xbrl_base64") or result.get("verbale_base64")
                    )
                    download_url = f"/api/openapi/xbrl/download/{request_id}" if ha_file else None
                    await db.richieste_bilanci.update_one(
                        {"id": request_id},
                        {"$set": {
                            "download_url": download_url,
                            "denominazione": result.get("denominazione"),
                            "data_deposito": result.get("data_deposito"),
                        }}
                    )

                    return {
                        "status": "completed",
                        "request_id": request_id,
                        "data": {
                            "denominazione": result.get("denominazione"),
                            "partita_iva": result.get("partita_iva"),
                            "anno_bilancio": result.get("anno_chiusura"),
                            "data_deposito": result.get("data_deposito"),
                            "files": {
                                "xbrl": result.get("xbrl_base64") is not None,
                                "pdf": result.get("pdf_base64") is not None,
                                "verbale": result.get("verbale_base64") is not None
                            }
                        },
                        "download_url": download_url,
                        "download_links": {
                            "xbrl": f"/api/openapi/xbrl/download/{request_id}/xbrl" if result.get("xbrl_base64") else None,
                            "pdf": f"/api/openapi/xbrl/download/{request_id}/pdf" if result.get("pdf_base64") else None,
                            "verbale": f"/api/openapi/xbrl/download/{request_id}/verbale" if result.get("verbale_base64") else None
                        }
                    }
                elif status == "pending":
                    return {
                        "status": "pending",
                        "request_id": request_id,
                        "message": "Bilancio in elaborazione. Riprova tra qualche minuto."
                    }
                else:
                    return {
                        "status": status,
                        "request_id": request_id,
                        "error": result.get("error_message")
                    }
            
            elif response.status_code == 404:
                return {
                    "status": "not_found",
                    "request_id": request_id,
                    "message": "Richiesta non trovata"
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore recupero bilancio"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore HTTP recupero XBRL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_XBRL_FILE_FIELDS = {
    "pdf": ("pdf_base64", "application/pdf", "pdf"),
    "xbrl": ("xbrl_base64", "application/xml", "xbrl"),
    "verbale": ("verbale_base64", "application/pdf", "pdf"),
}


async def _scarica_file_bilancio(request_id: str, tipo: str) -> Response:
    """Il contenuto del bilancio (PDF/XBRL/verbale) non viene mai persistito
    nel database di GestionaleCloud: viene richiesto di nuovo a OpenAPI.it
    al momento del download e restituito direttamente al browser."""
    campo, content_type, estensione = _XBRL_FILE_FIELDS[tipo]
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{get_visure_url()}/bilancio-ottico/{request_id}",
                headers=get_headers()
            )
    except httpx.HTTPError as e:
        logger.error(f"Errore HTTP download XBRL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Errore recupero bilancio")

    result = response.json()
    if result.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Il bilancio non è ancora disponibile")

    contenuto_b64 = result.get(campo)
    if not contenuto_b64:
        raise HTTPException(status_code=404, detail=f"File '{tipo}' non disponibile per questo bilancio")

    try:
        contenuto = base64.b64decode(contenuto_b64)
    except Exception:
        raise HTTPException(status_code=500, detail="File ricevuto da OpenAPI.it non decodificabile")

    filename = f"bilancio_{request_id}_{tipo}.{estensione}"
    return Response(
        content=contenuto,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/xbrl/download/{request_id}")
async def download_bilancio_xbrl(request_id: str) -> Response:
    """Download del bilancio (preferisce il PDF ufficiale, in mancanza usa l'XBRL)."""
    db = Database.get_db()
    richiesta = await db.richieste_bilanci.find_one({"id": request_id}, {"_id": 0})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    for tipo in ("pdf", "xbrl", "verbale"):
        try:
            return await _scarica_file_bilancio(request_id, tipo)
        except HTTPException as e:
            if e.status_code != 404:
                raise
    raise HTTPException(status_code=404, detail="Nessun file disponibile per questo bilancio")


@router.get("/xbrl/download/{request_id}/{tipo}")
async def download_bilancio_xbrl_tipizzato(request_id: str, tipo: str) -> Response:
    """Download del singolo file (xbrl|pdf|verbale) del bilancio richiesto."""
    if tipo not in _XBRL_FILE_FIELDS:
        raise HTTPException(status_code=400, detail="Tipo file non valido: usa xbrl, pdf o verbale")
    return await _scarica_file_bilancio(request_id, tipo)


@router.post("/xbrl/richiedi-riclassificato")
async def richiedi_bilancio_riclassificato(partita_iva: str = Query(...)) -> Dict[str, Any]:
    """
    Richiede il bilancio riclassificato con indici di bilancio.
    Include: liquidità, solvibilità, redditività, struttura finanziaria.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{get_visure_url()}/bilancio-riclassificato",
                headers=get_headers(),
                json={"cf_piva_id": partita_iva}
            )
            
            if response.status_code in [200, 201, 202]:
                result = response.json()
                return {
                    "status": "pending",
                    "request_id": result.get("id"),
                    "message": "Richiesta bilancio riclassificato inviata"
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore richiesta bilancio riclassificato"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore riclassificato: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/xbrl/storico-richieste")
async def get_storico_richieste_xbrl(limit: int = Query(20)) -> Dict[str, Any]:
    """
    Recupera lo storico delle richieste bilanci XBRL.
    """
    db = Database.get_db()
    
    richieste = await db.richieste_bilanci.find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {
        "richieste": richieste,
        "count": len(richieste)
    }


# ============================================================
# VISURE CAMERALI
# ============================================================

@router.post("/visure/richiedi")
async def richiedi_visura_camerale(partita_iva: str = Query(...)) -> Dict[str, Any]:
    """
    Richiede una visura camerale completa.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{get_visure_url()}/visura-ordinaria",
                headers=get_headers(),
                json={"cf_piva_id": partita_iva}
            )
            
            if response.status_code in [200, 201, 202]:
                result = response.json()
                return {
                    "status": "pending",
                    "request_id": result.get("id"),
                    "message": "Richiesta visura camerale inviata"
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore richiesta visura"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore visura: {e}")
        raise HTTPException(status_code=500, detail=str(e))
