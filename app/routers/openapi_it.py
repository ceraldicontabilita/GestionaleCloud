"""
OpenAPI.it Integration Module
Integrazione con le API di OpenAPI.it per:
- SDI (Fatturazione Elettronica)
- AISP (Open Banking - Riconciliazione Bancaria)
- XBRL (Bilanci Camera di Commercio)
- Visure Camerali

Documentazione: https://console.openapi.com/it/apis/sdi/documentation
"""
import os
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Body
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


class InvoiceCreate(BaseModel):
    """Modello per creazione fattura elettronica"""
    numero: str
    data: str  # YYYY-MM-DD
    fornitore_piva: str
    fornitore_denominazione: str
    cliente_piva: Optional[str] = None
    cliente_cf: Optional[str] = None
    cliente_denominazione: str
    imponibile: float
    iva: float
    totale: float
    descrizione: Optional[str] = None
    modalita_pagamento: str = "MP05"  # Bonifico bancario


class BankAccountConnect(BaseModel):
    """Modello per connessione conto bancario AISP"""
    bank_code: str
    iban: str
    consent_id: Optional[str] = None


# ============================================================
# SDI - FATTURAZIONE ELETTRONICA
# ============================================================

@router.get("/sdi/status")
async def get_sdi_status() -> Dict[str, Any]:
    """
    Verifica lo stato della connessione SDI e le configurazioni.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Verifica connettività
            response = await client.get(
                f"{get_base_url()}/v1/tools/validate_xml/schema/FatturaPA",
                headers=get_headers()
            )
            
            return {
                "status": "connected" if response.status_code == 200 else "error",
                "environment": OPENAPI_ENV,
                "api_key_configured": bool(OPENAPI_KEY),
                "base_url": get_base_url(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Errore verifica SDI: {e}")
        return {
            "status": "error",
            "error": str(e),
            "environment": OPENAPI_ENV,
            "api_key_configured": bool(OPENAPI_KEY)
        }


@router.post("/sdi/invia-fattura")
async def invia_fattura_sdi(fattura_id: str = Query(...)) -> Dict[str, Any]:
    """
    Invia una fattura al Sistema di Interscambio (SDI).
    
    1. Recupera la fattura dal database
    2. Genera XML FatturaPA
    3. Invia tramite API OpenAPI.it
    4. Salva ricevuta
    """
    db = Database.get_db()
    
    # Recupera fattura
    fattura = await db.invoices.find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Verifica se già inviata
    if fattura.get("sdi_status") == "inviata":
        return {
            "status": "already_sent",
            "sdi_id": fattura.get("sdi_id"),
            "message": "Fattura già inviata allo SDI"
        }
    
    try:
        # Genera XML FatturaPA
        xml_content = genera_xml_fatturapa(fattura)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Invia allo SDI
            response = await client.post(
                f"{get_base_url()}/v1/invoice/send",
                headers=get_headers(),
                json={
                    "xml": xml_content,
                    "format": "FatturaPA",
                    "apply_signature": True,
                    "apply_legal_storage": True
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Aggiorna fattura nel database
                await db.invoices.update_one(
                    {"id": fattura_id},
                    {"$set": {
                        "sdi_status": "inviata",
                        "sdi_id": result.get("id"),
                        "sdi_timestamp": datetime.now(timezone.utc).isoformat(),
                        "sdi_response": result,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                return {
                    "status": "success",
                    "sdi_id": result.get("id"),
                    "message": "Fattura inviata con successo allo SDI"
                }
            else:
                error_detail = response.json() if response.content else {"error": response.status_code}
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Errore SDI: {error_detail}"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore HTTP invio SDI: {e}")
        raise HTTPException(status_code=500, detail=f"Errore connessione SDI: {str(e)}")


@router.get("/sdi/ricevi-fatture")
async def ricevi_fatture_sdi(
    from_date: Optional[str] = None,
    limit: int = Query(50, le=200)
) -> Dict[str, Any]:
    """
    Recupera fatture passive ricevute dallo SDI.
    """
    db = Database.get_db()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            params = {"limit": limit}
            if from_date:
                params["from_date"] = from_date
            
            response = await client.get(
                f"{get_base_url()}/v1/invoice/received",
                headers=get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                fatture_ricevute = response.json().get("invoices", [])
                
                # Importa fatture nel database
                importate = 0
                for fatt_sdi in fatture_ricevute:
                    # Verifica se già presente
                    existing = await db.invoices.find_one({
                        "sdi_id": fatt_sdi.get("id")
                    })
                    
                    if not existing:
                        # Importa nuova fattura
                        nuova_fattura = converti_fattura_sdi(fatt_sdi)
                        await db.invoices.insert_one(nuova_fattura)
                        importate += 1
                
                return {
                    "status": "success",
                    "fatture_ricevute": len(fatture_ricevute),
                    "fatture_importate": importate,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore recupero fatture SDI"
                )
                
    except httpx.HTTPError as e:
        logger.error(f"Errore HTTP ricezione SDI: {e}")
        raise HTTPException(status_code=500, detail=f"Errore connessione SDI: {str(e)}")


@router.get("/sdi/notifiche")
async def get_notifiche_sdi(limit: int = Query(50)) -> Dict[str, Any]:
    """
    Recupera le notifiche SDI (esiti, scarti, mancata consegna).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{get_base_url()}/v1/invoice/notifications",
                headers=get_headers(),
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "notifiche": response.json().get("notifications", [])
                }
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "notifiche": []
                }
                
    except Exception as e:
        logger.error(f"Errore recupero notifiche SDI: {e}")
        return {"status": "error", "error": str(e), "notifiche": []}


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
                    # Bilancio disponibile
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


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def genera_xml_fatturapa(fattura: Dict) -> str:
    """
    Genera XML FatturaPA dal documento fattura.
    Formato conforme alle specifiche Agenzia delle Entrate.
    """
    # Questa è una versione semplificata - in produzione usare lxml
    fornitore = fattura.get("supplier_name", "")
    if isinstance(fornitore, dict):
        fornitore = fornitore.get("name", "")
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>{fattura.get('supplier_vat', '')}</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>{fattura.get('invoice_number', '')}</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>{fattura.get('codice_destinatario', 'USAL8PV')}</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>{fattura.get('supplier_vat', '')}</IdCodice>
        </IdFiscaleIVA>
        <Anagrafica>
          <Denominazione>{fornitore}</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{fattura.get('invoice_date', '')}</Data>
        <Numero>{fattura.get('invoice_number', '')}</Numero>
        <ImportoTotaleDocumento>{fattura.get('total_amount', 0):.2f}</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>{fattura.get('description', 'Servizi')[:100]}</Descrizione>
        <PrezzoUnitario>{fattura.get('taxable_amount', fattura.get('total_amount', 0) / 1.10):.2f}</PrezzoUnitario>
        <PrezzoTotale>{fattura.get('taxable_amount', fattura.get('total_amount', 0) / 1.10):.2f}</PrezzoTotale>
        <AliquotaIVA>{fattura.get('aliquota_iva', '10.00')}</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>{fattura.get('aliquota_iva', '10.00')}</AliquotaIVA>
        <ImponibileImporto>{fattura.get('taxable_amount', fattura.get('total_amount', 0) / 1.10):.2f}</ImponibileImporto>
        <Imposta>{fattura.get('vat_amount', fattura.get('total_amount', 0) * 0.10 / 1.10):.2f}</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento>
      <CondizioniPagamento>TP02</CondizioniPagamento>
      <DettaglioPagamento>
        <ModalitaPagamento>{fattura.get('payment_method_code', 'MP05')}</ModalitaPagamento>
        <ImportoPagamento>{fattura.get('total_amount', 0):.2f}</ImportoPagamento>
      </DettaglioPagamento>
    </DatiPagamento>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""
    
    return xml


def converti_fattura_sdi(fatt_sdi: Dict) -> Dict:
    """
    Converte una fattura SDI nel formato interno del database.
    """
    import uuid
    
    return {
        "id": str(uuid.uuid4()),
        "sdi_id": fatt_sdi.get("id"),
        "invoice_number": fatt_sdi.get("numero"),
        "invoice_date": fatt_sdi.get("data"),
        "supplier_name": fatt_sdi.get("cedente", {}).get("denominazione"),
        "supplier_vat": fatt_sdi.get("cedente", {}).get("partita_iva"),
        "total_amount": float(fatt_sdi.get("importo_totale", 0)),
        "taxable_amount": float(fatt_sdi.get("imponibile", 0)),
        "vat_amount": float(fatt_sdi.get("iva", 0)),
        "status": "ricevuta",
        "source": "sdi",
        "metodo_pagamento": "Bonifico",
        "payment_method": "bank_transfer",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
