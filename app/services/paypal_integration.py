"""
PayPal Integration — Ceraldi ERP
=================================
Scarica transazioni PayPal per riconciliare pagamenti verbali/multe.
Usa PayPal REST API v1/reporting/transactions.
"""
import httpx
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv("backend/.env", override=True)

logger = logging.getLogger(__name__)

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET_KEY = os.environ.get("PAYPAL_SECRET_KEY", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "live")

PAYPAL_API_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"


async def _get_paypal_token() -> Optional[str]:
    """Ottiene OAuth2 access token da PayPal."""
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET_KEY:
        logger.error("[PAYPAL] Credenziali non configurate")
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET_KEY),
                headers={"Accept": "application/json"},
                timeout=15
            )
            if response.status_code == 200:
                token = response.json().get("access_token")
                logger.info("[PAYPAL] Token ottenuto")
                return token
            else:
                logger.error(f"[PAYPAL] Token fallito: {response.status_code} {response.text[:200]}")
                return None
    except Exception as e:
        logger.error(f"[PAYPAL] Errore token: {e}")
        return None


async def cerca_transazioni_paypal(
    days_back: int = 365,
    keywords: List[str] = None
) -> Dict[str, Any]:
    """
    Cerca transazioni PayPal degli ultimi N giorni.
    Filtra per keyword (verbale, multa, comune, ecc.)
    """
    token = await _get_paypal_token()
    if not token:
        return {"success": False, "error": "Token non ottenuto", "transazioni": []}
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=min(days_back, 31))).strftime("%Y-%m-%dT00:00:00Z")
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT23:59:59Z")
    
    all_transactions = []
    page = 1
    
    try:
        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    f"{PAYPAL_API_BASE}/v1/reporting/transactions",
                    params={
                        "start_date": start_date,
                        "end_date": end_date,
                        "fields": "transaction_info,payer_info,cart_info",
                        "page_size": 100,
                        "page": page
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"[PAYPAL] Errore transazioni: {response.status_code} {response.text[:300]}")
                    break
                
                data = response.json()
                transactions = data.get("transaction_details", [])
                
                for tx in transactions:
                    tx_info = tx.get("transaction_info", {})
                    payer = tx.get("payer_info", {})
                    cart = tx.get("cart_info", {})
                    
                    amount = float(tx_info.get("transaction_amount", {}).get("value", 0))
                    tx_date = tx_info.get("transaction_initiation_date", "")
                    tx_id = tx_info.get("transaction_id", "")
                    tx_status = tx_info.get("transaction_status", "")
                    subject = tx_info.get("transaction_subject", "") or tx_info.get("transaction_note", "")
                    payer_name = payer.get("payer_name", {}).get("alternate_full_name", "")
                    payer_email = payer.get("email_address", "")
                    
                    all_transactions.append({
                        "id": tx_id,
                        "date": tx_date,
                        "amount": abs(amount),
                        "currency": tx_info.get("transaction_amount", {}).get("currency_code", "EUR"),
                        "status": tx_status,
                        "subject": subject,
                        "payer_name": payer_name,
                        "payer_email": payer_email,
                        "type": tx_info.get("transaction_event_code", ""),
                    })
                
                total_pages = data.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1
        
        # Filtra per keywords se specificate
        if keywords:
            filtered = []
            for tx in all_transactions:
                text = f"{tx['subject']} {tx['payer_name']}".lower()
                if any(kw.lower() in text for kw in keywords):
                    filtered.append(tx)
            all_transactions = filtered
        
        logger.info(f"[PAYPAL] Trovate {len(all_transactions)} transazioni")
        return {"success": True, "transazioni": all_transactions, "totale": len(all_transactions)}
        
    except Exception as e:
        logger.error(f"[PAYPAL] Errore: {e}")
        return {"success": False, "error": str(e), "transazioni": []}


async def riconcilia_verbali_con_paypal(db) -> Dict[str, Any]:
    """
    Scarica transazioni PayPal e le confronta con verbali da pagare.
    Match per importo e/o riferimento nel subject.
    """
    stats = {"transazioni_paypal": 0, "match_trovati": 0, "verbali_pagati": 0, "errori": 0}
    
    # Scarica transazioni PayPal
    result = await cerca_transazioni_paypal(
        days_back=31,
        keywords=["verbale", "multa", "sanzione", "comune", "pagopa", "infrazione"]
    )
    
    if not result.get("success"):
        # Prova senza filtro
        result = await cerca_transazioni_paypal(days_back=31)
    
    transactions = result.get("transazioni", [])
    stats["transazioni_paypal"] = len(transactions)
    
    if not transactions:
        logger.info("[PAYPAL] Nessuna transazione trovata")
        return stats
    
    # Carica verbali non pagati
    verbali = await db["verbali_noleggio"].find(
        {"stato": {"$nin": ["pagato", "riconciliato"]}, "importo": {"$gt": 0}},
        {"_id": 0}
    ).to_list(500)
    
    logger.info(f"[PAYPAL] {len(transactions)} transazioni vs {len(verbali)} verbali")
    
    for verbale in verbali:
        importo = float(verbale.get("importo", 0))
        numero = verbale.get("numero_verbale", "")
        
        for tx in transactions:
            matched = False
            
            # Match per importo esatto
            if abs(tx["amount"] - importo) <= 0.05:
                matched = True
            
            # Match per numero verbale nel subject
            if numero and numero.lower() in tx.get("subject", "").lower():
                matched = True
            
            if matched:
                await db["verbali_noleggio"].update_one(
                    {"id": verbale["id"]},
                    {"$set": {
                        "stato": "pagato",
                        "quietanza_ricevuta": True,
                        "data_pagamento": tx["date"][:10] if tx.get("date") else None,
                        "metodo_pagamento": "paypal",
                        "paypal_transaction_id": tx["id"],
                        "paypal_payer": tx.get("payer_name") or tx.get("payer_email"),
                        "importo_pagato": tx["amount"],
                    }}
                )
                stats["match_trovati"] += 1
                stats["verbali_pagati"] += 1
                logger.info(f"[PAYPAL] Match: Verbale {numero} → PayPal {tx['id']} €{tx['amount']}")
                break
    
    # Salva TUTTE le transazioni PayPal nel DB per consultazione
    for tx in transactions:
        existing = await db["paypal_transactions"].find_one({"transaction_id": tx["id"]})
        if not existing:
            await db["paypal_transactions"].insert_one({
                "id": str(uuid.uuid4()),
                "transaction_id": tx["id"],
                "date": tx["date"],
                "amount": tx["amount"],
                "currency": tx["currency"],
                "status": tx["status"],
                "subject": tx["subject"],
                "payer_name": tx["payer_name"],
                "payer_email": tx["payer_email"],
                "type": tx["type"],
                "imported_at": datetime.now(timezone.utc).isoformat()
            })
    
    logger.info(f"[PAYPAL] Riconciliazione completata: {stats}")
    return stats
