"""
Servizio Schede Tecniche Prodotti
=================================
Gestisce le schede tecniche dei prodotti forniti dai fornitori.
Estrae dati dai PDF e li associa ai prodotti in magazzino.
"""

import os
import re
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import base64
from app.database import Database

logger = logging.getLogger(__name__)


async def extract_product_info_from_text(text: str) -> Dict[str, Any]:
    """
    Estrae informazioni sul prodotto dal testo della scheda tecnica.
    Cerca pattern come "Prodotto:", "Articolo N°:", "Nome:", etc.
    """
    result = {
        "nome_prodotto": None,
        "codice_articolo": None,
        "codice_fornitore": None,
        "descrizione": None,
        "ingredienti": [],
        "allergeni": [],
        "valori_nutrizionali": {},
        "raw_text": text[:5000] if text else ""  # Salva primi 5000 caratteri per debug
    }
    
    text_lower = text.lower() if text else ""
    
    # Pattern per nome prodotto
    nome_patterns = [
        r"prodotto\s*:?\s*([A-Z][A-Z\s\-\']+[A-Z])",
        r"nome\s*(?:prodotto)?\s*:?\s*([A-Z][A-Z\s\-\']+[A-Z])",
        r"denominazione\s*:?\s*([A-Z][A-Z\s\-\']+[A-Z])",
    ]
    
    for pattern in nome_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            result["nome_prodotto"] = match.group(1).strip()
            break
    
    # Pattern per codice articolo
    codice_patterns = [
        r"articolo\s*[Nn°\.:\s]+(\d{6,12})",
        r"cod(?:ice)?\.?\s*(?:art)?\.?\s*:?\s*(\d{6,12})",
        r"sku\s*:?\s*(\w{5,15})",
        r"ref(?:erenza)?\.?\s*:?\s*(\w{5,15})",
    ]
    
    for pattern in codice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["codice_articolo"] = match.group(1).strip()
            break
    
    # Estrai ingredienti (se presenti)
    ingredienti_match = re.search(
        r"ingredienti?\s*:?\s*(.+?)(?=allergeni|valori|conserv|prodotto|$)",
        text, re.IGNORECASE | re.DOTALL
    )
    if ingredienti_match:
        ingredienti_text = ingredienti_match.group(1).strip()
        # Pulisci e splitta
        ingredienti_list = [i.strip() for i in re.split(r'[,;]', ingredienti_text) if i.strip()]
        result["ingredienti"] = ingredienti_list[:20]  # Max 20 ingredienti
    
    # Estrai allergeni (se presenti)
    allergeni_keywords = [
        "glutine", "grano", "latte", "lattosio", "uova", "soia", 
        "arachidi", "frutta a guscio", "sedano", "senape", "sesamo",
        "lupini", "molluschi", "crostacei", "pesce", "anidride solforosa"
    ]
    found_allergeni = []
    for allergen in allergeni_keywords:
        if allergen in text_lower:
            found_allergeni.append(allergen.title())
    result["allergeni"] = found_allergeni
    
    return result


async def process_scheda_tecnica_from_pdf(
    db, 
    pdf_data: bytes, 
    filename: str, 
    email_from: str = "", 
    email_subject: str = ""
) -> Dict[str, Any]:
    """
    Processa un PDF di scheda tecnica, estrae i dati del prodotto e lo salva.
    Tenta di associarlo a un prodotto esistente e al fornitore.
    """
    try:
        # Estrai testo dal PDF
        text = await extract_text_from_pdf(pdf_data)
        
        if not text or len(text) < 50:
            return {
                "success": False,
                "error": "Impossibile estrarre testo dal PDF"
            }
        
        # Estrai info prodotto
        product_info = await extract_product_info_from_text(text)
        
        # Cerca fornitore dal mittente email
        fornitore_info = await find_fornitore_from_email(db, email_from)
        
        # Cerca prodotto esistente nel magazzino
        prodotto_match = None
        if product_info.get("nome_prodotto"):
            prodotto_match = await find_matching_product(
                db, 
                product_info["nome_prodotto"],
                product_info.get("codice_articolo")
            )
        
        # Crea record scheda tecnica
        scheda_id = str(uuid.uuid4())
        scheda_doc = {
            "id": scheda_id,
            "filename": filename,
            "pdf_hash": calculate_hash(pdf_data),
            "pdf_data": base64.b64encode(pdf_data).decode('utf-8'),
            "pdf_size": len(pdf_data),
            
            # Info prodotto estratte
            "nome_prodotto": product_info.get("nome_prodotto"),
            "codice_articolo": product_info.get("codice_articolo"),
            "ingredienti": product_info.get("ingredienti", []),
            "allergeni": product_info.get("allergeni", []),
            "valori_nutrizionali": product_info.get("valori_nutrizionali", {}),
            "raw_text": product_info.get("raw_text", ""),
            
            # Associazioni
            "fornitore_id": fornitore_info.get("id") if fornitore_info else None,
            "fornitore_nome": fornitore_info.get("nome") if fornitore_info else None,
            "prodotto_id": prodotto_match.get("id") if prodotto_match else None,
            "prodotto_associato": bool(prodotto_match),
            
            # Email info
            "email_from": email_from,
            "email_subject": email_subject,
            
            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed": True,
            "validated": False  # Richiede validazione manuale
        }
        
        # Salva nel database
        await db["schede_tecniche_prodotti"].insert_one(scheda_doc.copy())
        
        # Se trovato prodotto, aggiorna con riferimento alla scheda tecnica
        if prodotto_match:
            await db["magazzino_articoli"].update_one(
                {"id": prodotto_match["id"]},
                {
                    "$set": {
                        "scheda_tecnica_id": scheda_id,
                        "scheda_tecnica_data": datetime.now(timezone.utc).isoformat()
                    },
                    "$push": {
                        "schede_tecniche_storico": {
                            "scheda_id": scheda_id,
                            "filename": filename,
                            "data": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            )
        
        # Se trovato fornitore, aggiungi alla lista schede del fornitore
        if fornitore_info:
            await db["fornitori"].update_one(
                {"id": fornitore_info["id"]},
                {
                    "$push": {
                        "schede_tecniche": {
                            "scheda_id": scheda_id,
                            "nome_prodotto": product_info.get("nome_prodotto"),
                            "filename": filename,
                            "data": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            )
        
        return {
            "success": True,
            "scheda_id": scheda_id,
            "nome_prodotto": product_info.get("nome_prodotto"),
            "codice_articolo": product_info.get("codice_articolo"),
            "fornitore_associato": fornitore_info.get("nome") if fornitore_info else None,
            "prodotto_associato": prodotto_match.get("nome") if prodotto_match else None,
            "ingredienti_trovati": len(product_info.get("ingredienti", [])),
            "allergeni_trovati": product_info.get("allergeni", [])
        }
        
    except Exception as e:
        logger.error(f"Errore process_scheda_tecnica_from_pdf: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def extract_text_from_pdf(pdf_data: bytes) -> str:
    """Estrae testo da un PDF usando pdfplumber o PyPDF2."""
    try:
        import pdfplumber
        import io
        
        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            text_parts = []
            for page in pdf.pages[:10]:  # Max 10 pagine
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
    except ImportError:
        pass
    
    try:
        from PyPDF2 import PdfReader
        import io
        
        reader = PdfReader(io.BytesIO(pdf_data))
        text_parts = []
        for page in reader.pages[:10]:
            text_parts.append(page.extract_text())
        return "\n".join(text_parts)
    except Exception as e:
        logger.warning(f"Errore estrazione PDF: {e}")
        return ""


async def find_fornitore_from_email(db, email_from: str) -> Optional[Dict[str, Any]]:
    """Cerca il fornitore dal mittente email."""
    if not email_from:
        return None
    
    # Pulisci email
    email_clean = email_from.lower()
    email_match = re.search(r'<([^>]+)>', email_from)
    if email_match:
        email_clean = email_match.group(1).lower()
    
    # Cerca per email esatta
    fornitore = await db["fornitori"].find_one(
        {"email": {"$regex": email_clean, "$options": "i"}},
        {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
    )
    
    if fornitore:
        return {
            "id": fornitore.get("id"),
            "nome": fornitore.get("ragione_sociale") or fornitore.get("nome")
        }
    
    # Cerca per dominio
    domain_match = re.search(r'@([^.]+)', email_clean)
    if domain_match:
        domain = domain_match.group(1)
        fornitore = await db["fornitori"].find_one(
            {"$or": [
                {"nome": {"$regex": domain, "$options": "i"}},
                {"ragione_sociale": {"$regex": domain, "$options": "i"}}
            ]},
            {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
        )
        if fornitore:
            return {
                "id": fornitore.get("id"),
                "nome": fornitore.get("ragione_sociale") or fornitore.get("nome")
            }
    
    return None


async def find_matching_product(db, nome_prodotto: str, codice_articolo: str = None) -> Optional[Dict[str, Any]]:
    """Cerca un prodotto esistente nel magazzino."""
    if not nome_prodotto:
        return None
    
    # Prima cerca per codice articolo se disponibile
    if codice_articolo:
        prodotto = await db["magazzino_articoli"].find_one(
            {"$or": [
                {"codice": codice_articolo},
                {"codice_fornitore": codice_articolo},
                {"sku": codice_articolo}
            ]},
            {"_id": 0, "id": 1, "nome": 1, "codice": 1}
        )
        if prodotto:
            return prodotto
    
    # Cerca per nome prodotto (fuzzy)
    nome_parts = nome_prodotto.split()
    if len(nome_parts) >= 2:
        # Cerca con almeno 2 parole del nome
        query_parts = []
        for part in nome_parts[:3]:
            if len(part) > 2:
                query_parts.append({"nome": {"$regex": part, "$options": "i"}})
        
        if query_parts:
            prodotto = await db["magazzino_articoli"].find_one(
                {"$and": query_parts},
                {"_id": 0, "id": 1, "nome": 1, "codice": 1}
            )
            if prodotto:
                return prodotto
    
    return None


def calculate_hash(data: bytes) -> str:
    """Calcola hash MD5 del contenuto."""
    import hashlib
    return hashlib.md5(data).hexdigest()


async def get_schede_tecniche_fornitore(db, fornitore_id: str) -> List[Dict[str, Any]]:
    """Ottiene tutte le schede tecniche di un fornitore."""
    schede = await db["schede_tecniche_prodotti"].find(
        {"fornitore_id": fornitore_id},
        {"_id": 0, "pdf_data": 0, "raw_text": 0}
    ).sort("created_at", -1).to_list(100)
    
    return schede


async def get_schede_tecniche_prodotto(db, prodotto_id: str) -> List[Dict[str, Any]]:
    """Ottiene tutte le schede tecniche di un prodotto."""
    schede = await db["schede_tecniche_prodotti"].find(
        {"prodotto_id": prodotto_id},
        {"_id": 0, "pdf_data": 0, "raw_text": 0}
    ).sort("created_at", -1).to_list(20)
    
    return schede


# ============================================
# SCANSIONE EMAIL PER SCHEDE TECNICHE
# ============================================

import imaplib
import email
from email.header import decode_header as email_decode_header

def decode_mime_header(header_value: str) -> str:
    """Decodifica header MIME."""
    if not header_value:
        return ""
    decoded_parts = email_decode_header(header_value)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            except:
                result.append(part.decode('utf-8', errors='replace'))
        else:
            result.append(str(part))
    return ' '.join(result)


def is_technical_sheet_email(filename: str, subject: str) -> bool:
    """Determina se un allegato è probabilmente una scheda tecnica."""
    keywords = [
        'scheda tecnica', 'technical sheet', 'data sheet',
        'product specification', 'specifica prodotto',
        'scheda prodotto', 'informazioni tecniche',
        'technical data', 'specifiche', 'datasheet',
        'ingredienti', 'allergeni', 'valori nutrizionali'
    ]
    
    filename_lower = filename.lower()
    subject_lower = subject.lower()
    
    for kw in keywords:
        if kw in filename_lower or kw in subject_lower:
            return True
    
    # Se è un PDF e NON è fattura/cedolino, considera come potenziale scheda
    if filename_lower.endswith('.pdf'):
        non_scheda = ['fattura', 'invoice', 'f24', 'cedolino', 'busta paga', 
                      'estratto', 'quietanza', 'bonifico', 'cartella']
        for ns in non_scheda:
            if ns in filename_lower or ns in subject_lower:
                return False
        # Se non è escluso, potrebbe essere scheda tecnica
        return True
    
    return False


async def scan_email_for_schede_tecniche(
    imap_host: str,
    imap_user: str,
    imap_password: str,
    folders: List[str] = None,
    limit: int = 50,
    days_back: int = 60
) -> Dict[str, Any]:
    """
    Scansiona le email per trovare e scaricare schede tecniche.
    
    Args:
        imap_host: Host IMAP
        imap_user: Username
        imap_password: Password
        folders: Lista cartelle da scansionare
        limit: Numero massimo email per cartella
        days_back: Giorni indietro da cercare
        
    Returns:
        Risultati della scansione
    """
    if folders is None:
        folders = ['INBOX', 'Fornitori', 'Schede', 'Schede Tecniche']
    
    results = {
        "email_scansionate": 0,
        "allegati_trovati": 0,
        "schede_salvate": 0,
        "schede_associate": 0,
        "errori": [],
        "dettagli": []
    }
    
    db = Database.get_db()
    
    try:
        # Connessione IMAP
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(imap_user, imap_password)
        
        for folder in folders:
            try:
                status, _ = mail.select(folder)
                if status != 'OK':
                    continue
                
                # Cerca email recenti
                from datetime import timedelta
                since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
                status, messages = mail.search(None, f'(SINCE {since_date})')
                
                if status != 'OK':
                    continue
                
                email_ids = messages[0].split()[-limit:]
                
                for email_id in email_ids:
                    try:
                        status, msg_data = mail.fetch(email_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        results["email_scansionate"] += 1
                        
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        subject = decode_mime_header(msg['Subject'] or '')
                        from_header = msg['From'] or ''
                        sender_email = email.utils.parseaddr(from_header)[1]
                        sender_name = decode_mime_header(email.utils.parseaddr(from_header)[0])
                        
                        # Cerca allegati PDF
                        for part in msg.walk():
                            if part.get_content_maintype() == 'multipart':
                                continue
                            
                            filename = part.get_filename()
                            if not filename:
                                continue
                            
                            filename = decode_mime_header(filename)
                            
                            if not filename.lower().endswith('.pdf'):
                                continue
                            
                            results["allegati_trovati"] += 1
                            
                            if not is_technical_sheet_email(filename, subject):
                                continue
                            
                            # Scarica allegato
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue
                            
                            # Verifica se già scaricato (hash)
                            file_hash = calculate_hash(payload)
                            existing = await db["schede_tecniche_prodotti"].find_one({"file_hash": file_hash})
                            if existing:
                                continue  # Già scaricato
                            
                            # Processa la scheda tecnica
                            result = await process_scheda_tecnica_from_pdf(
                                db=db,
                                pdf_data=payload,
                                filename=filename,
                                email_from=sender_email,
                                email_subject=subject
                            )
                            
                            if result.get("success"):
                                results["schede_salvate"] += 1
                                if result.get("fornitore_id"):
                                    results["schede_associate"] += 1
                                
                                results["dettagli"].append({
                                    "filename": filename,
                                    "fornitore": result.get("fornitore_nome", "Non associato"),
                                    "prodotto": result.get("prodotto_nome", "Non identificato"),
                                    "email_from": sender_email
                                })
                            
                    except Exception as e:
                        results["errori"].append(f"Email {email_id}: {str(e)}")
                        
            except Exception as e:
                results["errori"].append(f"Folder {folder}: {str(e)}")
        
        mail.logout()
        
    except Exception as e:
        results["errori"].append(f"Connessione IMAP: {str(e)}")
    
    return results
