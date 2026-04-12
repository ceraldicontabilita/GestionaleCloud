"""
WhatsApp Business API — Webhook receiver + Message sender.
Gestisce verifica webhook Meta e ricezione messaggi.
"""
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Token di verifica webhook — deve corrispondere a quello inserito nella console Meta
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "ceraldi_erp_webhook_2026")


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Verifica webhook Meta — risponde alla challenge di verifica.
    Meta invia GET con hub.mode=subscribe, hub.verify_token e hub.challenge.
    """
    logger.info(f"[WhatsApp Webhook] Verifica: mode={hub_mode}, token={hub_token}")
    
    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("[WhatsApp Webhook] ✅ Verifica riuscita")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    
    logger.warning(f"[WhatsApp Webhook] ❌ Token non valido: {hub_token}")
    raise HTTPException(status_code=403, detail="Token di verifica non valido")


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Riceve notifiche webhook da Meta (messaggi in arrivo, status updates).
    """
    body = await request.json()
    logger.info(f"[WhatsApp Webhook] Messaggio ricevuto: {body.get('object', 'unknown')}")
    
    try:
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    # Messaggi in arrivo
                    messages = value.get("messages", [])
                    for msg in messages:
                        from_number = msg.get("from", "")
                        msg_type = msg.get("type", "")
                        text = msg.get("text", {}).get("body", "") if msg_type == "text" else f"[{msg_type}]"
                        logger.info(f"[WhatsApp] 📩 Da {from_number}: {text[:100]}")
                    
                    # Status updates (sent, delivered, read)
                    statuses = value.get("statuses", [])
                    for status in statuses:
                        logger.info(f"[WhatsApp] 📊 Status: {status.get('status')} per {status.get('recipient_id')}")
    except Exception as e:
        logger.error(f"[WhatsApp Webhook] Errore processing: {e}")
    
    # Meta richiede sempre 200 OK
    return {"status": "ok"}
