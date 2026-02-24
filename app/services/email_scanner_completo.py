"""
Scanner Completo Email - Scansiona TUTTA la posta e associa documenti.

Gestisce:
1. Verbali noleggio (B...)
2. Cartelle esattoriali (071...)
3. F24 e tributi (DMRA...)
4. Altre cartelle con documenti

NON duplica: verifica sempre se il documento esiste già nel DB.
"""
import imaplib
import email
from email.header import decode_header
import os
import re
import uuid
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.database import Database

logger = logging.getLogger(__name__)

# Config
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
EMAIL_ADDRESS = os.environ.get("GMAIL_EMAIL", "ceraldigroupsrl@gmail.com")
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "okzonmhlwrnqjlcf")

# Collections
COLL_VERBALI_POSTA = "verbali_noleggio"
COLL_ESATTORIALI = "cartelle_esattoriali"
COLL_DOCUMENTI_EMAIL = "documenti_email"

# Pattern
TARGA_PATTERN = r'\b([A-Z]{2}\d{3}[A-Z]{2})\b'
VERBALE_PATTERN = r'\b([A-Z]\d{10,12})\b'


def decode_header_value(value: str) -> str:
    """Decodifica header email."""
    if not value:
        return ""
    try:
        decoded = decode_header(value)
        result = ""
        for part, enc in decoded:
            if isinstance(part, bytes):
                result += part.decode(enc or 'utf-8', errors='ignore')
            else:
                result += str(part)
        return result
    except:
        return str(value)


def classifica_cartella(nome: str) -> str:
    """Classifica il tipo di cartella email."""
    nome_clean = nome.strip()
    
    # Verbali noleggio: B/A/T/S + 10-12 cifre
    # Esempi: B20124359436, A18110589028, T23260589335
    if len(nome_clean) >= 11 and nome_clean[0] in ['B', 'A', 'T', 'S']:
        resto = nome_clean[1:]
        if resto.isdigit() and len(resto) >= 10:
            return "verbale_noleggio"
    
    # Esattoriali Agenzia Entrate Riscossione (071)
    if nome_clean.startswith('071') or nome_clean.replace(' ', '').startswith('071'):
        return "esattoriale"
    
    # Esattoriali Regionali (371)
    if nome_clean.startswith('371') or nome_clean.replace(' ', '').startswith('371'):
        return "esattoriale_regionale"
    
    # F24 e tributi DMRA
    if 'DMRA' in nome_clean or nome_clean.startswith('5100'):
        return "f24_tributi"
    
    # Documenti numerici lunghi
    if re.match(r'^\d{10,}$', nome_clean):
        return "documento_numerico"
    
    # 730 dichiarazioni
    if '730' in nome_clean:
        return "dichiarazione_730"
    
    return "altro"


def get_imap_connection():
    """Crea connessione IMAP."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        return mail
    except Exception as e:
        logger.error(f"Errore connessione IMAP: {e}")
        return None


async def get_cartelle_da_scansionare() -> Dict[str, List[str]]:
    """
    Ottiene tutte le cartelle email classificate per tipo.
    """
    mail = get_imap_connection()
    if not mail:
        return {}
    
    try:
        status, folders = mail.list()
        
        risultato = {
            "verbale_noleggio": [],
            "esattoriale": [],
            "esattoriale_regionale": [],
            "f24_tributi": [],
            "documento_numerico": [],
            "dichiarazione_730": [],
            "altro": []
        }
        
        for folder in folders:
            folder_str = folder.decode()
            if '"/"' in folder_str:
                name = folder_str.split('"/"')[-1].strip().strip('"')
                
                # Salta cartelle di sistema
                if name in ['INBOX', 'Sent', 'Drafts', 'Trash', 'Spam', '[Gmail]']:
                    continue
                if name.startswith('[Gmail]'):
                    continue
                
                tipo = classifica_cartella(name)
                if tipo not in risultato:
                    risultato[tipo] = []
                risultato[tipo].append(name)
        
        mail.logout()
        return risultato
        
    except Exception as e:
        logger.error(f"Errore lista cartelle: {e}")
        if mail:
            mail.logout()
        return {}


async def scarica_documenti_cartella(
    cartella: str,
    tipo: str,
    max_email: int = 10
) -> Dict[str, Any]:
    """
    Scarica tutti i documenti da una cartella email.
    
    Returns:
        {
            "cartella": str,
            "tipo": str,
            "documenti": [...],
            "errori": [...]
        }
    """
    db = Database.get_db()
    mail = get_imap_connection()
    
    if not mail:
        return {"cartella": cartella, "tipo": tipo, "documenti": [], "errori": ["Connessione fallita"]}
    
    risultato = {
        "cartella": cartella,
        "tipo": tipo,
        "documenti": [],
        "errori": []
    }
    
    try:
        # Seleziona cartella
        status, _ = mail.select(f'"{cartella}"', readonly=True)
        if status != 'OK':
            risultato["errori"].append("Impossibile selezionare cartella")
            mail.logout()
            return risultato
        
        # Cerca email
        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            mail.logout()
            return risultato
        
        msg_ids = messages[0].split()
        
        for msg_id in msg_ids[:max_email]:
            try:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Info email
                subject = decode_header_value(msg.get('Subject', ''))
                sender = msg.get('From', '')
                date_str = msg.get('Date', '')
                message_id = msg.get('Message-ID', '')
                
                # Cerca allegati PDF
                allegati = []
                if msg.is_multipart():
                    for part in msg.walk():
                        filename = part.get_filename()
                        if filename:
                            filename = decode_header_value(filename)
                            content_type = part.get_content_type()
                            
                            # Scarica contenuto
                            content = part.get_payload(decode=True)
                            if content:
                                allegati.append({
                                    "filename": filename,
                                    "content_type": content_type,
                                    "size": len(content),
                                    "content_base64": base64.b64encode(content).decode('utf-8') if len(content) < 10_000_000 else None  # Max 10MB
                                })
                
                if allegati:
                    doc = {
                        "cartella": cartella,
                        "tipo_cartella": tipo,
                        "subject": subject,
                        "sender": sender,
                        "date": date_str,
                        "message_id": message_id,
                        "allegati": allegati
                    }
                    risultato["documenti"].append(doc)
                    
            except Exception as e:
                risultato["errori"].append(f"Email {msg_id}: {str(e)}")
        
        mail.logout()
        return risultato
        
    except Exception as e:
        risultato["errori"].append(str(e))
        if mail:
            mail.logout()
        return risultato


async def salva_documenti_scansionati(risultato_scan: Dict[str, Any]) -> Dict[str, int]:
    """
    Salva i documenti scansionati nel database.
    NON duplica documenti già esistenti.
    """
    db = Database.get_db()
    
    stats = {"salvati": 0, "duplicati": 0, "errori": 0}
    
    cartella = risultato_scan.get("cartella")
    tipo = risultato_scan.get("tipo_cartella", risultato_scan.get("tipo"))
    
    for doc in risultato_scan.get("documenti", []):
        try:
            # Genera ID univoco basato su cartella + message_id
            doc_id = f"{cartella}_{doc.get('message_id', uuid.uuid4().hex)}"
            
            # Verifica duplicato
            existing = await db[COLL_DOCUMENTI_EMAIL].find_one({"doc_id": doc_id})
            if existing:
                stats["duplicati"] += 1
                continue
            
            # Prepara record
            record = {
                "id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "cartella": cartella,
                "tipo_cartella": tipo,
                "subject": doc.get("subject"),
                "sender": doc.get("sender"),
                "date": doc.get("date"),
                "message_id": doc.get("message_id"),
                "allegati": doc.get("allegati", []),
                "num_allegati": len(doc.get("allegati", [])),
                
                # Associazioni (da compilare dopo)
                "verbale_associato": None,
                "fattura_associata": None,
                "esattoriale_associato": None,
                
                # Metadata
                "processato": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLL_DOCUMENTI_EMAIL].insert_one(record)
            stats["salvati"] += 1
            
        except Exception as e:
            logger.error(f"Errore salvataggio documento: {e}")
            stats["errori"] += 1
    
    return stats


async def scansiona_tutte_cartelle(
    tipi: List[str] = None,
    max_cartelle: int = 100,
    max_email_per_cartella: int = 5
) -> Dict[str, Any]:
    """
    Scansiona tutte le cartelle email e salva i documenti.
    
    Args:
        tipi: Lista di tipi da scansionare (default: tutti)
        max_cartelle: Numero massimo di cartelle per tipo
        max_email_per_cartella: Numero massimo di email per cartella
    
    Returns:
        Statistiche complete della scansione
    """
    if tipi is None:
        tipi = ["verbale_noleggio", "esattoriale", "esattoriale_regionale", "f24_tributi"]
    
    # Ottieni cartelle
    cartelle_per_tipo = await get_cartelle_da_scansionare()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tipi_scansionati": tipi,
        "cartelle_totali": 0,
        "documenti_totali": 0,
        "salvati": 0,
        "duplicati": 0,
        "errori": 0,
        "dettaglio_per_tipo": {}
    }
    
    for tipo in tipi:
        cartelle = cartelle_per_tipo.get(tipo, [])[:max_cartelle]
        
        tipo_stats = {
            "cartelle": len(cartelle),
            "documenti": 0,
            "salvati": 0,
            "duplicati": 0
        }
        
        for cartella in cartelle:
            try:
                # Scarica documenti
                scan_result = await scarica_documenti_cartella(
                    cartella, tipo, max_email_per_cartella
                )
                
                tipo_stats["documenti"] += len(scan_result.get("documenti", []))
                
                # Salva
                save_result = await salva_documenti_scansionati(scan_result)
                tipo_stats["salvati"] += save_result["salvati"]
                tipo_stats["duplicati"] += save_result["duplicati"]
                
                logger.info(f"Scansionata {cartella}: {save_result['salvati']} nuovi documenti")
                
            except Exception as e:
                logger.error(f"Errore scansione {cartella}: {e}")
                risultato["errori"] += 1
        
        risultato["dettaglio_per_tipo"][tipo] = tipo_stats
        risultato["cartelle_totali"] += tipo_stats["cartelle"]
        risultato["documenti_totali"] += tipo_stats["documenti"]
        risultato["salvati"] += tipo_stats["salvati"]
        risultato["duplicati"] += tipo_stats["duplicati"]
    
    return risultato


async def associa_documenti_a_verbali() -> Dict[str, Any]:
    """
    Associa i documenti email scaricati ai verbali nel database.
    Cerca corrispondenze per numero verbale o targa.
    """
    db = Database.get_db()
    
    risultato = {
        "documenti_analizzati": 0,
        "associazioni_create": 0,
        "nessuna_corrispondenza": 0
    }
    
    # Prendi documenti non ancora processati
    cursor = db[COLL_DOCUMENTI_EMAIL].find({"processato": False})
    
    async for doc in cursor:
        risultato["documenti_analizzati"] += 1
        
        cartella = doc.get("cartella", "")
        subject = doc.get("subject", "")
        
        # Cerca numero verbale nel nome cartella o subject
        numero_verbale = None
        match = re.search(VERBALE_PATTERN, cartella)
        if match:
            numero_verbale = match.group(1)
        else:
            match = re.search(VERBALE_PATTERN, subject)
            if match:
                numero_verbale = match.group(1)
        
        if numero_verbale:
            # Cerca verbale nel database
            verbale = await db["verbali_noleggio_completi"].find_one(
                {"numero_verbale": numero_verbale}
            )
            
            if verbale:
                # Associa
                await db[COLL_DOCUMENTI_EMAIL].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "verbale_associato": verbale["id"],
                        "processato": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Aggiorna anche il verbale con riferimento al PDF
                await db["verbali_noleggio_completi"].update_one(
                    {"id": verbale["id"]},
                    {"$set": {
                        "pdf_downloaded": True,
                        "documento_email_id": doc["id"],
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                risultato["associazioni_create"] += 1
                continue
        
        # Se nessuna corrispondenza, marca come processato
        await db[COLL_DOCUMENTI_EMAIL].update_one(
            {"id": doc["id"]},
            {"$set": {"processato": True}}
        )
        risultato["nessuna_corrispondenza"] += 1
    
    return risultato


async def get_statistiche_documenti() -> Dict[str, Any]:
    """Statistiche complete dei documenti email."""
    db = Database.get_db()
    
    # Documenti email scaricati
    totale = await db[COLL_DOCUMENTI_EMAIL].count_documents({})
    
    # Per tipo
    per_tipo = {}
    pipeline = [
        {"$group": {"_id": "$tipo_cartella", "count": {"$sum": 1}}}
    ]
    async for doc in db[COLL_DOCUMENTI_EMAIL].aggregate(pipeline):
        per_tipo[doc["_id"] or "sconosciuto"] = doc["count"]
    
    # Verbali
    verbali_fatture = await db["verbali_noleggio_completi"].count_documents({})
    verbali_con_pdf = await db["verbali_noleggio_completi"].count_documents({"pdf_downloaded": True})
    verbali_attesa = await db[COLL_DOCUMENTI_EMAIL].count_documents({
        "tipo_cartella": "verbale_noleggio",
        "stato": "in_attesa_fattura"
    })
    verbali_associati = await db[COLL_DOCUMENTI_EMAIL].count_documents({
        "tipo_cartella": "verbale_noleggio",
        "verbale_associato": {"$ne": None}
    })
    
    return {
        "totale_documenti_email": totale,
        "per_tipo": per_tipo,
        "verbali": {
            "estratti_da_fatture": verbali_fatture,
            "con_pdf_scaricato": verbali_con_pdf,
            "in_attesa_fattura": verbali_attesa,
            "associati": verbali_associati
        },
        "esattoriali": per_tipo.get("esattoriale", 0) + per_tipo.get("esattoriale_regionale", 0),
        "f24_tributi": per_tipo.get("f24_tributi", 0)
    }
