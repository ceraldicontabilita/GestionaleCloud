"""
Router InvoiceTronic - Integrazione Fatturazione Elettronica SDI

Funzionalità:
1. Ricezione automatica fatture passive da SDI
2. Webhook per notifiche real-time
3. Status e monitoraggio
4. Import automatico in database

API Key: Configurata in .env come INVOICETRONIC_API_KEY
Documentazione: https://invoicetronic.com/docs/
"""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import logging
import os
import base64

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/invoicetronic", tags=["InvoiceTronic SDI"])

# Configurazione
INVOICETRONIC_API_KEY = os.environ.get("INVOICETRONIC_API_KEY")
INVOICETRONIC_SANDBOX = os.environ.get("INVOICETRONIC_SANDBOX", "true").lower() == "true"
INVOICETRONIC_CODICE_DESTINATARIO = os.environ.get("INVOICETRONIC_CODICE_DESTINATARIO", "7hd37x0")

# Collection per fatture SDI
COLLECTION_FATTURE_SDI = "fatture_sdi"
COLLECTION_WEBHOOK_LOG = "invoicetronic_webhook_log"


def get_invoicetronic_client():
    """Inizializza il client InvoiceTronic SDK."""
    try:
        from invoicetronic_sdk import Configuration, ApiClient
        
        if not INVOICETRONIC_API_KEY:
            raise ValueError("INVOICETRONIC_API_KEY non configurata")
        
        config = Configuration()
        
        # InvoiceTronic usa Basic Auth con API key come username e password vuota
        config.username = INVOICETRONIC_API_KEY
        config.password = ""
        
        # Host API InvoiceTronic
        config.host = "https://api.invoicetronic.com/v1"
        
        return ApiClient(config)
    except ImportError:
        logger.error("invoicetronic_sdk non installato")
        return None
    except Exception as e:
        logger.error(f"Errore inizializzazione InvoiceTronic: {e}")
        return None


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Verifica stato connessione e crediti disponibili.
    """
    try:
        from invoicetronic_sdk import StatusApi
        
        client = get_invoicetronic_client()
        if not client:
            return {
                "connected": False,
                "error": "Client non configurato",
                "api_key_configured": bool(INVOICETRONIC_API_KEY),
                "sandbox_mode": INVOICETRONIC_SANDBOX,
                "codice_destinatario": INVOICETRONIC_CODICE_DESTINATARIO
            }
        
        api = StatusApi(client)
        status = api.status_get()
        
        return {
            "connected": True,
            "sandbox_mode": INVOICETRONIC_SANDBOX,
            "codice_destinatario": INVOICETRONIC_CODICE_DESTINATARIO,
            "account": {
                "operations_left": getattr(status, 'operation_left', None),
                "signatures_left": getattr(status, 'signature_left', None),
            },
            "istruzioni": {
                "passo_1": "Vai su https://ivaservizi.agenziaentrate.gov.it/",
                "passo_2": "Fatture e Corrispettivi → Registrazione indirizzo telematico",
                "passo_3": f"Inserisci Codice Destinatario: {INVOICETRONIC_CODICE_DESTINATARIO}",
                "passo_4": "Salva. Da quel momento le fatture arrivano qui automaticamente"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Errore status InvoiceTronic: {e}")
        return {
            "connected": False,
            "error": str(e),
            "sandbox_mode": INVOICETRONIC_SANDBOX,
            "codice_destinatario": INVOICETRONIC_CODICE_DESTINATARIO
        }


@router.get("/fatture-in-arrivo")
async def get_fatture_in_arrivo(
    limit: int = 50,
    scaricate: bool = False
) -> Dict[str, Any]:
    """
    Recupera fatture passive in arrivo da SDI.
    Queste sono le fatture dei fornitori destinate a Ceraldi Group.
    """
    try:
        from invoicetronic_sdk import ReceiveApi
        
        client = get_invoicetronic_client()
        if not client:
            raise HTTPException(status_code=500, detail="Client InvoiceTronic non configurato")
        
        api = ReceiveApi(client)
        
        # Recupera fatture in entrata
        fatture = api.receive_get(page_size=limit)
        
        risultato = []
        for f in fatture:
            risultato.append({
                "id": getattr(f, 'id', None),
                "file_name": getattr(f, 'file_name', None),
                "sender_vat": getattr(f, 'sender_id', None),
                "receiver_vat": getattr(f, 'receiver_id', None),
                "date_received": str(getattr(f, 'created', '')),
                "status": getattr(f, 'state', None),
                "scaricata": False  # Da implementare tracking
            })
        
        return {
            "fatture": risultato,
            "count": len(risultato),
            "sandbox_mode": INVOICETRONIC_SANDBOX
        }
    except Exception as e:
        logger.error(f"Errore recupero fatture: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scarica-fattura/{fattura_id}")
async def scarica_fattura(fattura_id: str) -> Dict[str, Any]:
    """
    Scarica una specifica fattura e la importa nel database.
    """
    db = Database.get_db()
    
    try:
        from invoicetronic_sdk import ReceiveApi
        
        client = get_invoicetronic_client()
        if not client:
            raise HTTPException(status_code=500, detail="Client InvoiceTronic non configurato")
        
        api = ReceiveApi(client)
        
        # Scarica fattura specifica
        fattura = api.receive_id_get(fattura_id)
        
        # Decodifica XML
        xml_content = ""
        if hasattr(fattura, 'payload'):
            payload = fattura.payload
            if payload:
                # Prova a decodificare da Base64
                try:
                    xml_content = base64.b64decode(payload).decode('utf-8')
                except Exception:
                    xml_content = payload
        
        # Salva in database locale
        fattura_doc = {
            "id": f"SDI-{fattura_id}",
            "invoicetronic_id": fattura_id,
            "file_name": getattr(fattura, 'file_name', None),
            "xml_content": xml_content,
            "sender_vat": getattr(fattura, 'sender_id', None),
            "receiver_vat": getattr(fattura, 'receiver_id', None),
            "status": getattr(fattura, 'state', None),
            "date_received": str(getattr(fattura, 'created', '')),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source": "invoicetronic"
        }
        
        # Inserisci o aggiorna
        await db[COLLECTION_FATTURE_SDI].update_one(
            {"invoicetronic_id": fattura_id},
            {"$set": fattura_doc},
            upsert=True
        )
        
        # TODO: Parsare XML e inserire in invoices collection principale
        
        return {
            "success": True,
            "fattura_id": fattura_id,
            "file_name": fattura_doc["file_name"],
            "imported": True
        }
    except Exception as e:
        logger.error(f"Errore scaricamento fattura {fattura_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-fatture")
async def sync_fatture_da_sdi(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Sincronizza tutte le fatture in arrivo da SDI.
    Scarica e importa automaticamente nel database.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fatture_trovate": 0,
        "fatture_importate": 0,
        "gia_presenti": 0,
        "errori": []
    }
    
    try:
        from invoicetronic_sdk import ReceiveApi
        
        client = get_invoicetronic_client()
        if not client:
            raise HTTPException(status_code=500, detail="Client InvoiceTronic non configurato")
        
        api = ReceiveApi(client)
        
        # Recupera tutte le fatture
        fatture = api.receive_get(page_size=100)
        risultati["fatture_trovate"] = len(fatture)
        
        for f in fatture:
            fattura_id = getattr(f, 'id', None)
            if not fattura_id:
                continue
            
            # Verifica se già importata
            esistente = await db[COLLECTION_FATTURE_SDI].find_one(
                {"invoicetronic_id": str(fattura_id)}
            )
            
            if esistente:
                risultati["gia_presenti"] += 1
                continue
            
            # Scarica e importa
            try:
                fattura_detail = api.receive_id_get(fattura_id)
                
                xml_content = ""
                if hasattr(fattura_detail, 'payload') and fattura_detail.payload:
                    try:
                        xml_content = base64.b64decode(fattura_detail.payload).decode('utf-8')
                    except Exception:
                        xml_content = fattura_detail.payload
                
                fattura_doc = {
                    "id": f"SDI-{fattura_id}",
                    "invoicetronic_id": str(fattura_id),
                    "file_name": getattr(fattura_detail, 'file_name', None),
                    "xml_content": xml_content,
                    "sender_vat": getattr(fattura_detail, 'sender_id', None),
                    "receiver_vat": getattr(fattura_detail, 'receiver_id', None),
                    "status": getattr(fattura_detail, 'state', None),
                    "date_received": str(getattr(fattura_detail, 'created', '')),
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "source": "invoicetronic"
                }
                
                await db[COLLECTION_FATTURE_SDI].insert_one(fattura_doc)
                risultati["fatture_importate"] += 1
                
            except Exception as e:
                risultati["errori"].append(f"Fattura {fattura_id}: {str(e)}")
        
        return risultati
        
    except Exception as e:
        logger.error(f"Errore sync fatture: {e}")
        risultati["errori"].append(str(e))
        return risultati


@router.post("/webhook")
async def webhook_invoicetronic(request: Request) -> Dict[str, Any]:
    """
    Webhook endpoint per ricevere notifiche real-time da InvoiceTronic.
    
    Eventi supportati:
    - receive.created: Nuova fattura in arrivo
    - send.delivered: Fattura consegnata
    - send.rejected: Fattura scartata da SDI
    """
    db = Database.get_db()
    
    try:
        payload = await request.json()
        
        # Log webhook
        webhook_log = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": payload.get("event"),
            "payload": payload,
            "processed": False
        }
        await db[COLLECTION_WEBHOOK_LOG].insert_one(webhook_log)
        
        event_type = payload.get("event", "")
        
        # Gestisci evento nuova fattura in arrivo
        if event_type == "receive.created":
            document_id = payload.get("data", {}).get("id")
            if document_id:
                # Scarica automaticamente la fattura
                try:
                    await scarica_fattura(str(document_id))
                    webhook_log["processed"] = True
                    await db[COLLECTION_WEBHOOK_LOG].update_one(
                        {"id": webhook_log["id"]},
                        {"$set": {"processed": True, "process_result": "imported"}}
                    )
                except Exception as e:
                    await db[COLLECTION_WEBHOOK_LOG].update_one(
                        {"id": webhook_log["id"]},
                        {"$set": {"process_error": str(e)}}
                    )
        
        # Gestisci aggiornamento stato fattura inviata
        elif event_type in ["send.delivered", "send.rejected", "send.accepted"]:
            document_id = payload.get("data", {}).get("id")
            new_status = payload.get("data", {}).get("state")
            
            if document_id:
                await db[COLLECTION_FATTURE_SDI].update_one(
                    {"invoicetronic_id": str(document_id)},
                    {"$set": {
                        "status": new_status,
                        "status_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
        
        return {"status": "ok", "event": event_type}
        
    except Exception as e:
        logger.error(f"Errore webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/aziende")
async def get_aziende() -> Dict[str, Any]:
    """
    Lista aziende configurate su InvoiceTronic.
    """
    try:
        from invoicetronic_sdk import CompanyApi
        
        client = get_invoicetronic_client()
        if not client:
            raise HTTPException(status_code=500, detail="Client InvoiceTronic non configurato")
        
        api = CompanyApi(client)
        aziende = api.company_get()
        
        risultato = []
        for a in aziende:
            risultato.append({
                "id": getattr(a, 'id', None),
                "name": getattr(a, 'name', None),
                "vat_number": getattr(a, 'vat_number', None),
                "fiscal_code": getattr(a, 'fiscal_code', None),
                "sdi_code": getattr(a, 'sdi_code', None)
            })
        
        return {
            "aziende": risultato,
            "count": len(risultato)
        }
    except Exception as e:
        logger.error(f"Errore recupero aziende: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook-log")
async def get_webhook_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Log degli webhook ricevuti."""
    db = Database.get_db()
    
    logs = await db[COLLECTION_WEBHOOK_LOG].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return logs


@router.get("/fatture-importate")
async def get_fatture_importate(
    anno: int = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Lista fatture già importate da InvoiceTronic."""
    db = Database.get_db()
    
    query = {"source": "invoicetronic"}
    if anno:
        query["imported_at"] = {"$regex": f"^{anno}"}
    
    fatture = await db[COLLECTION_FATTURE_SDI].find(
        query, {"_id": 0, "xml_content": 0}  # Escludi XML pesante
    ).sort("imported_at", -1).limit(limit).to_list(limit)
    
    return {
        "fatture": fatture,
        "count": len(fatture)
    }
