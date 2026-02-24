"""
Servizio per scaricare email e salvare TUTTO su MongoDB Atlas.
NIENTE filesystem - solo MongoDB.

Funzionalità:
1. Scarica allegati PDF dalle email
2. Salva contenuto base64 in MongoDB
3. Parsa cedolini/buste paga
4. Inserisce automaticamente in prima_nota_salari
"""

import imaplib
import email
from email.header import decode_header
import re
import uuid
import hashlib
import base64
from datetime import datetime, timezone
from typing import Dict, Any
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Configurazione IMAP da .env - lette a runtime
IMAP_SERVER = "imap.gmail.com"


def get_email_credentials():
    """Ottieni credenziali email da settings."""
    from app.config import settings
    email_user = settings.EMAIL_USER or settings.GMAIL_EMAIL or settings.EMAIL_ADDRESS or ""
    email_password = settings.EMAIL_PASSWORD or settings.EMAIL_APP_PASSWORD or settings.GMAIL_APP_PASSWORD or ""
    return email_user, email_password


def decode_mime_header(header_value: str) -> str:
    """Decodifica header MIME."""
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(header_value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return ''.join(result)
    except:
        return str(header_value)


def calculate_hash(content: bytes) -> str:
    """Calcola MD5 hash per deduplicazione."""
    return hashlib.md5(content).hexdigest()


def categorize_document(filename: str, subject: str = "") -> str:
    """Categorizza documento dal nome file."""
    text = f"{filename} {subject}".lower()
    
    if any(p in text for p in ["busta paga", "cedolino", "libro unico", "lul", "stipendio"]):
        return "busta_paga"
    elif any(p in text for p in ["f24", "f-24", "tribut", "agenzia entrate"]):
        return "f24"
    elif any(p in text for p in ["fattur", "invoice", "ft_", "ft-"]):
        return "fattura"
    elif any(p in text for p in ["estratto", "conto corrente", "moviment"]):
        return "estratto_conto"
    else:
        return "altro"


def parse_cedolino_from_text(text: str) -> Dict[str, Any]:
    """
    Estrae dati dal testo di un cedolino/busta paga.
    Pattern comuni nei cedolini italiani.
    """
    data = {}
    
    # Nome dipendente
    nome_match = re.search(r'(?:Dipendente|Cognome e Nome|Lavoratore)[:\s]+([A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+)', text)
    if nome_match:
        data['dipendente_nome'] = nome_match.group(1).strip()
    
    # Codice Fiscale
    cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        data['codice_fiscale'] = cf_match.group(1)
    
    # Periodo (mese/anno)
    periodo_match = re.search(r'(?:Periodo|Mese)[:\s]+(\w+)\s*[/-]?\s*(\d{4})', text, re.IGNORECASE)
    if periodo_match:
        mesi = {
            'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
            'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
            'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
        }
        mese_str = periodo_match.group(1).lower()
        data['mese'] = mesi.get(mese_str, None)
        data['anno'] = int(periodo_match.group(2))
    
    # Importi
    netto_match = re.search(r'(?:Netto|Netto a pagare|Netto in busta)[:\s]+[€\s]*([\d.,]+)', text, re.IGNORECASE)
    if netto_match:
        data['netto'] = float(netto_match.group(1).replace('.', '').replace(',', '.'))
    
    lordo_match = re.search(r'(?:Lordo|Retribuzione lorda)[:\s]+[€\s]*([\d.,]+)', text, re.IGNORECASE)
    if lordo_match:
        data['lordo'] = float(lordo_match.group(1).replace('.', '').replace(',', '.'))
    
    # INPS dipendente
    inps_match = re.search(r'(?:INPS|Contributi)[:\s]+[€\s]*([\d.,]+)', text, re.IGNORECASE)
    if inps_match:
        data['inps_dipendente'] = float(inps_match.group(1).replace('.', '').replace(',', '.'))
    
    # IRPEF
    irpef_match = re.search(r'(?:IRPEF|Ritenute)[:\s]+[€\s]*([\d.,]+)', text, re.IGNORECASE)
    if irpef_match:
        data['irpef'] = float(irpef_match.group(1).replace('.', '').replace(',', '.'))
    
    return data


async def download_and_save_emails(
    db: AsyncIOMotorDatabase,
    days_back: int = 30,
    folder: str = "INBOX"
) -> Dict[str, Any]:
    """
    Scarica email con allegati PDF e salva TUTTO su MongoDB.
    Niente filesystem.
    """
    stats = {
        "emails_processed": 0,
        "pdfs_saved": 0,
        "duplicates_skipped": 0,
        "cedolini_parsed": 0,
        "prima_nota_created": 0,
        "errors": []
    }
    
    # Ottieni credenziali email
    email_user, email_password = get_email_credentials()
    
    if not email_user or not email_password:
        return {"error": "Credenziali email non configurate", "stats": stats}
    
    try:
        # Connetti a IMAP
        conn = imaplib.IMAP4_SSL(IMAP_SERVER)
        conn.login(email_user, email_password)
        conn.select(folder)
        logger.info(f"Connesso a {IMAP_SERVER} come {email_user}")
        
        # Cerca email degli ultimi N giorni
        from datetime import timedelta
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        status, messages = conn.search(None, f'(SINCE "{since_date}")')
        
        if status != "OK":
            return {"error": "Ricerca email fallita", "stats": stats}
        
        email_ids = messages[0].split()
        logger.info(f"Trovate {len(email_ids)} email da processare")
        
        for email_uid in email_ids:
            try:
                status, msg_data = conn.fetch(email_uid, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                subject = decode_mime_header(msg.get("Subject", ""))
                from_addr = decode_mime_header(msg.get("From", ""))
                date_str = msg.get("Date", "")
                
                # Estrai allegati PDF
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        filename = part.get_filename()
                        
                        if filename:
                            filename = decode_mime_header(filename)
                        
                        # Solo PDF
                        is_pdf = (
                            content_type == "application/pdf" or
                            (filename and filename.lower().endswith(".pdf"))
                        )
                        
                        if is_pdf and filename:
                            try:
                                content = part.get_payload(decode=True)
                                if not content or len(content) < 500:
                                    continue
                                
                                # Calcola hash per deduplicazione
                                file_hash = calculate_hash(content)
                                
                                # Controlla se già esiste
                                existing = await db["email_documents"].find_one({"file_hash": file_hash})
                                if existing:
                                    stats["duplicates_skipped"] += 1
                                    continue
                                
                                # Categorizza
                                category = categorize_document(filename, subject)
                                
                                # Salva su MongoDB (contenuto base64)
                                pdf_base64 = base64.b64encode(content).decode('utf-8')
                                
                                doc = {
                                    "id": str(uuid.uuid4()),
                                    "filename": filename,
                                    "pdf_data": pdf_base64,  # Contenuto in MongoDB!
                                    "pdf_hash": file_hash,
                                    "pdf_size": len(content),
                                    "category": category,
                                    "email_subject": subject,
                                    "email_from": from_addr,
                                    "email_date": date_str,
                                    "email_uid": email_uid.decode() if isinstance(email_uid, bytes) else str(email_uid),
                                    "status": "nuovo",
                                    "processed": False,
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }
                                
                                await db["email_documents"].insert_one(doc)
                                stats["pdfs_saved"] += 1
                                logger.info(f"PDF salvato su MongoDB: {filename} ({category})")
                                
                                # Se è una busta paga, prova a parsare
                                if category == "busta_paga":
                                    await process_cedolino(db, doc, content)
                                    stats["cedolini_parsed"] += 1
                                
                            except Exception as e:
                                logger.error(f"Errore salvataggio PDF: {e}")
                                stats["errors"].append(str(e))
                
                stats["emails_processed"] += 1
                
            except Exception as e:
                logger.error(f"Errore processing email: {e}")
                stats["errors"].append(str(e))
        
        conn.logout()
        
    except Exception as e:
        logger.error(f"Errore connessione IMAP: {e}")
        return {"error": str(e), "stats": stats}
    
    return {"success": True, "stats": stats}


async def process_cedolino(db: AsyncIOMotorDatabase, doc: Dict, pdf_content: bytes):
    """
    Processa un cedolino: estrae dati e crea record in prima_nota_salari.
    """
    try:
        # Usa PyMuPDF per estrarre testo
        import fitz  # PyMuPDF
        
        pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
        text = ""
        for page in pdf_doc:
            text += page.get_text()
        pdf_doc.close()
        
        # Parsa i dati
        parsed = parse_cedolino_from_text(text)
        
        if not parsed.get('dipendente_nome') or not parsed.get('netto'):
            logger.warning(f"Cedolino non parsato completamente: {doc['filename']}")
            return
        
        # Cerca dipendente nel database
        dipendente = await db["employees"].find_one({
            "$or": [
                {"nome_completo": {"$regex": parsed.get('dipendente_nome', ''), "$options": "i"}},
                {"codice_fiscale": parsed.get('codice_fiscale', '')}
            ]
        })
        
        dipendente_id = dipendente["id"] if dipendente else None
        dipendente_nome = parsed.get('dipendente_nome', doc['filename'])
        
        # Crea record in prima_nota_salari
        salario_doc = {
            "id": str(uuid.uuid4()),
            "dipendente_id": dipendente_id,
            "dipendente_nome": dipendente_nome,
            "mese": parsed.get('mese'),
            "anno": parsed.get('anno'),
            "netto": parsed.get('netto', 0),
            "lordo": parsed.get('lordo', 0),
            "inps_dipendente": parsed.get('inps_dipendente', 0),
            "irpef": parsed.get('irpef', 0),
            "pdf_document_id": doc["id"],
            "source": "email_auto",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Verifica se esiste già
        existing = await db["prima_nota_salari"].find_one({
            "dipendente_nome": dipendente_nome,
            "mese": parsed.get('mese'),
            "anno": parsed.get('anno')
        })
        
        if not existing:
            await db["prima_nota_salari"].insert_one(salario_doc)
            logger.info(f"Prima nota salari creata: {dipendente_nome} {parsed.get('mese')}/{parsed.get('anno')}")
        
        # Aggiorna documento come processato
        await db["email_documents"].update_one(
            {"id": doc["id"]},
            {"$set": {
                "processed": True,
                "status": "processato",
                "parsed_data": parsed,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
    except ImportError:
        logger.error("PyMuPDF non installato - impossibile parsare PDF")
    except Exception as e:
        logger.error(f"Errore processing cedolino: {e}")


async def get_email_documents_stats(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """Statistiche sui documenti email salvati in MongoDB."""
    pipeline = [
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "processed": {"$sum": {"$cond": ["$processed", 1, 0]}}
        }}
    ]
    
    stats = {"total": 0, "by_category": {}}
    async for doc in db["email_documents"].aggregate(pipeline):
        cat = doc["_id"]
        stats["by_category"][cat] = {
            "total": doc["count"],
            "processed": doc["processed"],
            "pending": doc["count"] - doc["processed"]
        }
        stats["total"] += doc["count"]
    
    return stats
