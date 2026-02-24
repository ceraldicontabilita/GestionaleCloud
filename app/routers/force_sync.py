"""
SYNC FORZATO - Email Aruba e Riconciliazione F24
================================================

Questo router forza il download delle email Aruba e la riconciliazione F24.
Usa le credenziali configurate in .env

Endpoint:
- POST /api/force-sync/aruba-email - Scarica email fatture Aruba
- POST /api/force-sync/f24-reconciliation - Riconcilia F24 con estratto conto
- POST /api/force-sync/all - Esegue tutto il workflow completo

Autore: Sistema Automatico
Data: 13 Febbraio 2026
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from app.database import Database
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/aruba-email")
async def force_sync_aruba_email(
    days_back: int = Query(30, ge=1, le=365, description="Giorni da scaricare")
) -> Dict[str, Any]:
    """
    Forza il download delle email da noreply@fatturazioneelettronica.aruba.it
    
    Workflow:
    1. Connessione IMAP a Gmail
    2. Cerca email da Aruba negli ultimi N giorni
    3. Parse HTML per estrarre dati fattura
    4. Crea fatture provvisorie nel DB
    5. Cerca pagamento nell'estratto conto
    6. Associa automaticamente se trovato
    """
    db = Database.get_db()
    
    # Prendi credenziali
    gmail_email = settings.GMAIL_EMAIL or settings.EMAIL_USER
    gmail_password = settings.GMAIL_APP_PASSWORD or settings.EMAIL_PASSWORD
    
    if not gmail_email or not gmail_password:
        raise HTTPException(
            status_code=500,
            detail="Credenziali Gmail non configurate. Verifica .env: GMAIL_EMAIL e GMAIL_APP_PASSWORD"
        )
    
    logger.info(f"📥 Avvio sync email Aruba - ultimi {days_back} giorni")
    logger.info(f"📧 Email: {gmail_email}")
    
    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header
        
        # Connessione IMAP
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(gmail_email, gmail_password)
        imap.select("INBOX")
        
        # Calcola data di inizio
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        
        # Cerca email da Aruba
        search_criteria = f'(FROM "noreply@fatturazioneelettronica.aruba.it" SINCE {since_date})'
        status, messages = imap.search(None, search_criteria)
        
        if status != "OK":
            raise Exception("Errore ricerca email IMAP")
        
        email_ids = messages[0].split()
        total_emails = len(email_ids)
        
        logger.info(f"✅ Trovate {total_emails} email da Aruba")
        
        fatture_create = 0
        fatture_gia_esistenti = 0
        errori = []
        
        for email_id in email_ids:
            try:
                # Scarica email
                status, msg_data = imap.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
                
                # Estrai corpo HTML
                body_html = None
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    if msg.get_content_type() == "text/html":
                        body_html = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                if not body_html:
                    continue
                
                # Parse HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body_html, "html.parser")
                
                # Estrai dati fattura (pattern Aruba)
                fattura_data = await parse_aruba_email(soup, body_html)
                
                if not fattura_data:
                    logger.warning(f"Email {email_id}: dati fattura non trovati")
                    continue
                
                # Verifica se esiste già
                existing = await db.fatture_provvisorie.find_one({
                    "numero_documento": fattura_data["numero_documento"],
                    "fornitore": fattura_data["fornitore"]
                })
                
                if existing:
                    fatture_gia_esistenti += 1
                    continue
                
                # Cerca pagamento nell'estratto conto
                pagamento = await cerca_pagamento_estratto_conto(
                    db,
                    importo=fattura_data["importo"],
                    data_documento=fattura_data["data_documento"],
                    fornitore=fattura_data["fornitore"]
                )
                
                # Crea fattura provvisoria
                fattura_record = {
                    **fattura_data,
                    "data_ricezione": datetime.now(timezone.utc).isoformat(),
                    "stato": "ricevuta",
                    "pagamento_trovato": pagamento is not None,
                    "pagamento_id": pagamento["id"] if pagamento else None,
                    "riconciliata": pagamento is not None
                }
                
                await db.fatture_provvisorie.insert_one(fattura_record)
                fatture_create += 1
                
                logger.info(f"✅ Fattura creata: {fattura_data['fornitore']} - €{fattura_data['importo']}")
                
            except Exception as e:
                logger.error(f"Errore processing email {email_id}: {e}")
                errori.append(str(e))
        
        imap.logout()
        
        return {
            "success": True,
            "email_totali": total_emails,
            "fatture_create": fatture_create,
            "fatture_gia_esistenti": fatture_gia_esistenti,
            "errori": errori,
            "message": f"Sync completato: {fatture_create} nuove fatture, {fatture_gia_esistenti} già esistenti"
        }
        
    except Exception as e:
        logger.error(f"❌ Errore sync email Aruba: {e}")
        raise HTTPException(status_code=500, detail=f"Errore sync: {str(e)}")


async def parse_aruba_email(soup, html: str) -> Optional[Dict[str, Any]]:
    """Parse email Aruba per estrarre dati fattura."""
    import re
    
    try:
        # Cerca fornitore (vari pattern)
        fornitore = None
        fornitore_patterns = [
            r"(?:Cedente|Mittente|Fornitore)[\s:]+([A-Z][A-Za-z\s&\.]+?)(?:\s*-|\s*<|$)",
            r"<strong>([A-Z][A-Za-z\s&\.]+?)</strong>",
        ]
        
        for pattern in fornitore_patterns:
            match = re.search(pattern, html)
            if match:
                fornitore = match.group(1).strip()
                break
        
        # Cerca numero fattura
        numero_patterns = [
            r"(?:Numero|N\.|Nr\.)[\s:]+(\d+(?:/\d+)?)",
            r"Fattura[\s:]+(\d+(?:/\d+)?)",
        ]
        
        numero_documento = None
        for pattern in numero_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                numero_documento = match.group(1).strip()
                break
        
        # Cerca data
        data_patterns = [
            r"(?:Data|Del)[\s:]+(\d{2}[/-]\d{2}[/-]\d{4})",
            r"(\d{2}[/-]\d{2}[/-]\d{4})",
        ]
        
        data_documento = None
        for pattern in data_patterns:
            match = re.search(pattern, html)
            if match:
                data_str = match.group(1)
                # Normalizza formato
                data_str = data_str.replace("/", "-")
                day, month, year = data_str.split("-")
                data_documento = f"{year}-{month}-{day}"
                break
        
        # Cerca importo
        importo_patterns = [
            r"(?:Importo|Totale)[\s:]+€?\s*([\d.,]+)",
            r"€\s*([\d.,]+)",
        ]
        
        importo = None
        for pattern in importo_patterns:
            match = re.search(pattern, html)
            if match:
                importo_str = match.group(1).replace(".", "").replace(",", ".")
                importo = float(importo_str)
                break
        
        if not all([fornitore, numero_documento, importo]):
            return None
        
        return {
            "fornitore": fornitore,
            "numero_documento": numero_documento,
            "data_documento": data_documento or datetime.now().strftime("%Y-%m-%d"),
            "importo": importo,
            "tipo": "fattura_elettronica",
            "fonte": "aruba_pec"
        }
        
    except Exception as e:
        logger.error(f"Errore parse email: {e}")
        return None


async def cerca_pagamento_estratto_conto(
    db, 
    importo: float, 
    data_documento: str,
    fornitore: str
) -> Optional[Dict[str, Any]]:
    """Cerca pagamento corrispondente nell'estratto conto."""
    
    # Tolleranza importo ±1€
    importo_min = importo - 1.0
    importo_max = importo + 1.0
    
    # Tolleranza data ±60 giorni
    from datetime import datetime, timedelta
    data_doc = datetime.fromisoformat(data_documento)
    data_min = (data_doc - timedelta(days=60)).strftime("%Y-%m-%d")
    data_max = (data_doc + timedelta(days=60)).strftime("%Y-%m-%d")
    
    # Cerca movimento
    movimento = await db.estratto_conto_movimenti.find_one({
        "importo": {"$gte": -importo_max, "$lte": -importo_min},  # Negativo = uscita
        "data_valuta": {"$gte": data_min, "$lte": data_max},
        "riconciliato": {"$ne": True}
    })
    
    if movimento:
        logger.info(f"💰 Pagamento trovato: €{abs(movimento['importo'])} del {movimento['data_valuta']}")
    
    return movimento


@router.post("/f24-reconciliation")
async def force_f24_reconciliation() -> Dict[str, Any]:
    """
    Forza riconciliazione F24 tra movimenti bancari e quietanze.
    """
    db = Database.get_db()
    
    logger.info("🔄 Avvio riconciliazione F24...")
    
    # Trova movimenti F24 non riconciliati
    f24_patterns = ["F24", "AGENZIA ENTRATE", "DELEGA"]
    
    movimenti_f24 = await db.estratto_conto_movimenti.find({
        "$or": [{"descrizione_originale": {"$regex": p, "$options": "i"}} for p in f24_patterns],
        "riconciliato": {"$ne": True},
        "importo": {"$lt": 0}  # Solo uscite
    }).to_list(500)
    
    logger.info(f"📊 Trovati {len(movimenti_f24)} movimenti F24 non riconciliati")
    
    riconciliati = 0
    
    for movimento in movimenti_f24:
        importo_abs = abs(movimento["importo"])
        data_movimento = movimento["data_valuta"]
        
        # Cerca quietanza con importo simile
        quietanza = await db.quietanze_f24.find_one({
            "importo_totale": {
                "$gte": importo_abs - 1.0,
                "$lte": importo_abs + 1.0
            },
            "riconciliato": {"$ne": True}
        })
        
        if quietanza:
            # Associa
            await db.estratto_conto_movimenti.update_one(
                {"_id": movimento["_id"]},
                {"$set": {
                    "riconciliato": True,
                    "quietanza_f24_id": str(quietanza["_id"]),
                    "riconciliato_il": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await db.quietanze_f24.update_one(
                {"_id": quietanza["_id"]},
                {"$set": {
                    "riconciliato": True,
                    "movimento_id": str(movimento["_id"])
                }}
            )
            
            riconciliati += 1
            logger.info(f"✅ F24 riconciliato: €{importo_abs}")
    
    return {
        "success": True,
        "movimenti_totali": len(movimenti_f24),
        "riconciliati": riconciliati,
        "message": f"Riconciliazione completata: {riconciliati}/{len(movimenti_f24)}"
    }


@router.post("/all")
async def force_sync_all(days_back: int = Query(30)) -> Dict[str, Any]:
    """
    Esegue tutto il workflow:
    1. Sync email Aruba
    2. Riconciliazione F24
    """
    logger.info("🚀 Avvio sync completo...")
    
    # Step 1: Email Aruba
    email_result = await force_sync_aruba_email(days_back=days_back)
    
    # Step 2: F24
    f24_result = await force_f24_reconciliation()
    
    return {
        "success": True,
        "email_sync": email_result,
        "f24_reconciliation": f24_result,
        "message": "Sync completo eseguito con successo"
    }
