"""
Sistema di Riconciliazione Automatica Posta ↔ Gestionale

Questo modulo gestisce:
1. Indicizzazione di TUTTI i documenti del gestionale
2. Scansione completa della posta elettronica
3. Matching intelligente tra email/allegati e documenti
4. Associazione automatica PDF ai documenti
5. Archiviazione organizzata

REGOLA FONDAMENTALE: 
Ogni documento del gestionale deve essere tracciabile e associabile
ai file originali presenti nella posta elettronica.
"""
import os
import re
import hashlib
import logging
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timezone
from typing import Dict, Any, List
import base64

from app.database import Database

logger = logging.getLogger(__name__)

# Collections MongoDB
COLLECTION_INDICE = "indice_documenti"  # Indice master di tutti i documenti
COLLECTION_EMAIL_ARCHIVE = "archivio_email"  # Email scaricate
COLLECTION_PDF_ARCHIVE = "archivio_pdf"  # PDF estratti
COLLECTION_MATCH_LOG = "log_riconciliazione"  # Log dei match trovati

# Configurazione Email
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", os.environ.get("GMAIL_EMAIL", "ceraldigroupsrl@gmail.com"))
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD"))

# Tipi di documento da indicizzare
TIPI_DOCUMENTO = [
    "fattura_ricevuta",
    "fattura_emessa", 
    "verbale",
    "bollo",
    "contratto_noleggio",
    "estratto_conto",
    "f24",
    "corrispettivo",
    "ordine_fornitore",
    "ddt",
    "nota_credito"
]

# Pattern per estrazione dati da testo
PATTERNS = {
    "numero_fattura": [
        r'fattura\s*n[°.\s:]*([A-Z0-9/-]+)',
        r'n[°.\s]*fattura\s*([A-Z0-9/-]+)',
        r'fatt\.\s*n[°.\s]*([A-Z0-9/-]+)',
        r'invoice\s*n[°.\s]*([A-Z0-9/-]+)',
        r'FPR\s*(\d+/\d+)',
        r'FIR(\d+)',
    ],
    "numero_verbale": [
        r'\b([A-Z]\d{10,12})\b',
        r'verbale\s*n[°.\s]*(\d+)',
        r'sanzione\s*n[°.\s]*(\d+)',
        r'infrazione\s*n[°.\s]*(\d+)',
    ],
    "targa": [
        r'\b([A-Z]{2}\d{3}[A-Z]{2})\b',
    ],
    "importo": [
        r'€\s*([\d.,]+)',
        r'euro\s*([\d.,]+)',
        r'importo\s*[€]?\s*([\d.,]+)',
        r'totale\s*[€]?\s*([\d.,]+)',
    ],
    "data": [
        r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})',
    ],
    "partita_iva": [
        r'\b(\d{11})\b',
        r'P\.?\s*IVA\s*[:.]?\s*(\d{11})',
    ],
    "codice_fiscale": [
        r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b',
    ],
    "numero_contratto": [
        r'contratto\s*n[°.\s]*([A-Z0-9/-]+)',
        r'n[°.\s]*contratto\s*([A-Z0-9/-]+)',
    ],
    "numero_bollo": [
        r'bollo\s*n[°.\s]*([A-Z0-9]+)',
        r'tassa\s*auto[^\d]*(\d+)',
    ]
}


def decode_email_header(header_value: str) -> str:
    """Decodifica header email."""
    if not header_value:
        return ""
    try:
        decoded = decode_header(header_value)
        result = ""
        for part, enc in decoded:
            if isinstance(part, bytes):
                result += part.decode(enc or 'utf-8', errors='ignore')
            else:
                result += str(part)
        return result
    except (UnicodeDecodeError, LookupError, AttributeError) as e:
        logger.debug(f"Errore decodifica header email: {e}")
        return str(header_value)


def estrai_pattern(testo: str, tipo_pattern: str) -> List[str]:
    """Estrae tutti i match di un pattern dal testo."""
    if not testo or tipo_pattern not in PATTERNS:
        return []
    
    risultati = []
    for pattern in PATTERNS[tipo_pattern]:
        matches = re.findall(pattern, testo, re.IGNORECASE)
        risultati.extend(matches)
    
    return list(set(risultati))


def calcola_hash_contenuto(contenuto: bytes) -> str:
    """Calcola hash SHA256 del contenuto per evitare duplicati."""
    return hashlib.sha256(contenuto).hexdigest()


async def costruisci_indice_documenti() -> Dict[str, Any]:
    """
    Costruisce l'indice master di TUTTI i documenti del gestionale.
    Questo indice viene usato per il matching con le email.
    
    Returns:
        Statistiche della costruzione indice
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documenti_indicizzati": 0,
        "per_tipo": {},
        "chiavi_ricerca": 0
    }
    
    # 1. Indicizza FATTURE RICEVUTE
    fatture = await db["invoices"].find({}).to_list(10000)
    for f in fatture:
        chiavi = []
        
        # Aggiungi tutte le chiavi di ricerca possibili
        if f.get("invoice_number"):
            chiavi.append(f["invoice_number"].upper())
        if f.get("numero_documento"):
            chiavi.append(f["numero_documento"].upper())
        if f.get("supplier_vat"):
            chiavi.append(f["supplier_vat"])
        if f.get("total_amount"):
            chiavi.append(str(round(float(f["total_amount"]), 2)))
        
        doc_indice = {
            "id": str(f.get("_id", f.get("id"))),
            "tipo": "fattura_ricevuta",
            "chiavi_ricerca": chiavi,
            "numero": f.get("invoice_number") or f.get("numero_documento"),
            "data": f.get("invoice_date"),
            "importo": f.get("total_amount"),
            "fornitore": f.get("supplier_name"),
            "fornitore_piva": f.get("supplier_vat"),
            "descrizione": f.get("causale") or f.get("oggetto"),
            "pdf_associati": f.get("pdf_allegati", []),
            "email_associata": f.get("email_id"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLLECTION_INDICE].update_one(
            {"id": doc_indice["id"], "tipo": "fattura_ricevuta"},
            {"$set": doc_indice},
            upsert=True
        )
        risultato["documenti_indicizzati"] += 1
        risultato["chiavi_ricerca"] += len(chiavi)
    
    risultato["per_tipo"]["fattura_ricevuta"] = len(fatture)
    
    # 2. Indicizza VERBALI
    verbali = await db["verbali_noleggio_completi"].find({}).to_list(5000)
    for v in verbali:
        chiavi = []
        if v.get("numero_verbale"):
            chiavi.append(v["numero_verbale"].upper())
        if v.get("targa"):
            chiavi.append(v["targa"].upper())
        if v.get("importo"):
            chiavi.append(str(round(float(v["importo"]), 2)))
        if v.get("numero_fattura"):
            chiavi.append(v["numero_fattura"].upper())
        
        doc_indice = {
            "id": v.get("id"),
            "tipo": "verbale",
            "chiavi_ricerca": chiavi,
            "numero": v.get("numero_verbale"),
            "data": v.get("data_verbale") or v.get("data_fattura"),
            "importo": v.get("importo"),
            "targa": v.get("targa"),
            "driver": v.get("driver"),
            "fornitore": v.get("fornitore"),
            "descrizione": v.get("descrizione"),
            "pdf_associati": v.get("pdf_allegati", []),
            "email_associata": v.get("email_id"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLLECTION_INDICE].update_one(
            {"id": doc_indice["id"], "tipo": "verbale"},
            {"$set": doc_indice},
            upsert=True
        )
        risultato["documenti_indicizzati"] += 1
        risultato["chiavi_ricerca"] += len(chiavi)
    
    risultato["per_tipo"]["verbale"] = len(verbali)
    
    # 3. Indicizza VEICOLI NOLEGGIO
    veicoli = await db["veicoli_noleggio"].find({}).to_list(1000)
    for veic in veicoli:
        chiavi = []
        if veic.get("targa"):
            chiavi.append(veic["targa"].upper())
        if veic.get("contratto"):
            chiavi.append(str(veic["contratto"]))
        if veic.get("codice_cliente"):
            chiavi.append(str(veic["codice_cliente"]))
        
        doc_indice = {
            "id": veic.get("id"),
            "tipo": "contratto_noleggio",
            "chiavi_ricerca": chiavi,
            "numero": veic.get("contratto"),
            "targa": veic.get("targa"),
            "driver": veic.get("driver"),
            "fornitore": veic.get("fornitore_noleggio"),
            "data_inizio": veic.get("data_inizio"),
            "data_fine": veic.get("data_fine"),
            "pdf_associati": veic.get("pdf_allegati", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLLECTION_INDICE].update_one(
            {"id": doc_indice["id"], "tipo": "contratto_noleggio"},
            {"$set": doc_indice},
            upsert=True
        )
        risultato["documenti_indicizzati"] += 1
        risultato["chiavi_ricerca"] += len(chiavi)
    
    risultato["per_tipo"]["contratto_noleggio"] = len(veicoli)
    
    # 4. Indicizza COSTI NOLEGGIO (bolli, riparazioni, etc.)
    costi = await db["costi_noleggio"].find({"eliminato": {"$ne": True}}).to_list(5000)
    for c in costi:
        chiavi = []
        if c.get("targa"):
            chiavi.append(c["targa"].upper())
        if c.get("numero_fattura"):
            chiavi.append(c["numero_fattura"].upper())
        if c.get("importo"):
            chiavi.append(str(round(float(c["importo"]), 2)))
        
        doc_indice = {
            "id": c.get("id"),
            "tipo": c.get("tipo_costo", "costo_noleggio"),
            "chiavi_ricerca": chiavi,
            "numero": c.get("numero_fattura"),
            "data": c.get("data"),
            "importo": c.get("importo"),
            "targa": c.get("targa"),
            "fornitore": c.get("fornitore"),
            "descrizione": c.get("descrizione"),
            "pdf_associati": c.get("pdf_allegati", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLLECTION_INDICE].update_one(
            {"id": doc_indice["id"], "tipo": doc_indice["tipo"]},
            {"$set": doc_indice},
            upsert=True
        )
        risultato["documenti_indicizzati"] += 1
        risultato["chiavi_ricerca"] += len(chiavi)
    
    risultato["per_tipo"]["costi_noleggio"] = len(costi)
    
    # 5. Indicizza F24
    f24 = await db["f24_unificato"].find({}).to_list(5000)
    for f in f24:
        chiavi = []
        if f.get("numero"):
            chiavi.append(str(f["numero"]))
        if f.get("importo_totale"):
            chiavi.append(str(round(float(f["importo_totale"]), 2)))
        
        doc_indice = {
            "id": str(f.get("_id", f.get("id"))),
            "tipo": "f24",
            "chiavi_ricerca": chiavi,
            "numero": f.get("numero"),
            "data": f.get("data_scadenza") or f.get("data"),
            "importo": f.get("importo_totale"),
            "descrizione": f.get("note"),
            "pdf_associati": f.get("pdf_allegati", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLLECTION_INDICE].update_one(
            {"id": doc_indice["id"], "tipo": "f24"},
            {"$set": doc_indice},
            upsert=True
        )
        risultato["documenti_indicizzati"] += 1
        risultato["chiavi_ricerca"] += len(chiavi)
    
    risultato["per_tipo"]["f24"] = len(f24)
    
    logger.info(f"Indice costruito: {risultato}")
    return risultato


async def cerca_match_in_indice(testo: str, allegato_nome: str = None) -> List[Dict[str, Any]]:
    """
    Cerca match tra un testo (email/allegato) e l'indice documenti.
    
    Args:
        testo: Contenuto testuale da analizzare
        allegato_nome: Nome file allegato (opzionale)
    
    Returns:
        Lista di documenti che matchano
    """
    db = Database.get_db()
    
    matches = []
    testo_upper = (testo or "").upper()
    nome_upper = (allegato_nome or "").upper()
    testo_completo = f"{testo_upper} {nome_upper}"
    
    # Estrai tutti i pattern dal testo
    pattern_trovati = {
        "numeri_fattura": estrai_pattern(testo_completo, "numero_fattura"),
        "numeri_verbale": estrai_pattern(testo_completo, "numero_verbale"),
        "targhe": estrai_pattern(testo_completo, "targa"),
        "importi": estrai_pattern(testo_completo, "importo"),
        "piva": estrai_pattern(testo_completo, "partita_iva"),
    }
    
    # Crea lista di chiavi da cercare
    chiavi_da_cercare = []
    for tipo, valori in pattern_trovati.items():
        for v in valori:
            chiavi_da_cercare.append(v.upper().replace(".", "").replace(",", "."))
    
    if not chiavi_da_cercare:
        return []
    
    # Cerca nell'indice
    query = {"chiavi_ricerca": {"$in": chiavi_da_cercare}}
    cursor = db[COLLECTION_INDICE].find(query, {"_id": 0})
    
    async for doc in cursor:
        # Calcola score di matching
        score = 0
        chiavi_matchate = []
        for chiave in doc.get("chiavi_ricerca", []):
            if chiave.upper() in chiavi_da_cercare:
                score += 1
                chiavi_matchate.append(chiave)
        
        if score > 0:
            matches.append({
                **doc,
                "match_score": score,
                "chiavi_matchate": chiavi_matchate,
                "pattern_trovati": pattern_trovati
            })
    
    # Ordina per score
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    return matches


async def scansiona_cartella_email(
    mail_connection,
    cartella: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Scansiona una cartella email e estrae tutte le email con allegati.
    """
    emails_trovate = []
    
    try:
        status, _ = mail_connection.select(f'"{cartella}"')
        if status != 'OK':
            return []
        
        # Cerca tutte le email
        status, messages = mail_connection.search(None, 'ALL')
        if status != 'OK':
            return []
        
        email_ids = messages[0].split()[-limit:]  # Ultime N email
        
        for email_id in email_ids:
            try:
                status, msg_data = mail_connection.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Estrai metadati
                subject = decode_email_header(msg.get("Subject", ""))
                from_addr = decode_email_header(msg.get("From", ""))
                date_str = msg.get("Date", "")
                
                # Estrai corpo e allegati
                corpo = ""
                allegati = []
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disp = str(part.get("Content-Disposition", ""))
                        
                        if content_type == "text/plain" and "attachment" not in content_disp:
                            try:
                                corpo += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            except (UnicodeDecodeError, AttributeError) as e:
                                logger.debug(f"Errore decodifica payload email: {e}")
                                pass
                        
                        elif "attachment" in content_disp or content_type == "application/pdf":
                            filename = part.get_filename()
                            if filename:
                                filename = decode_email_header(filename)
                                payload = part.get_payload(decode=True)
                                if payload:
                                    allegati.append({
                                        "filename": filename,
                                        "content_type": content_type,
                                        "size": len(payload),
                                        "hash": calcola_hash_contenuto(payload),
                                        "content_base64": base64.b64encode(payload).decode('utf-8') if len(payload) < 5_000_000 else None  # Max 5MB
                                    })
                else:
                    try:
                        corpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except (UnicodeDecodeError, AttributeError) as e:
                        logger.debug(f"Errore decodifica body email: {e}")
                        pass
                
                emails_trovate.append({
                    "email_id": email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                    "cartella": cartella,
                    "subject": subject,
                    "from": from_addr,
                    "date": date_str,
                    "corpo": corpo[:10000],  # Limita a 10KB
                    "allegati": allegati,
                    "has_pdf": any(a["content_type"] == "application/pdf" for a in allegati)
                })
                
            except Exception as e:
                logger.error(f"Errore parsing email {email_id}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Errore scansione cartella {cartella}: {e}")
    
    return emails_trovate


async def riconcilia_email_con_gestionale(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Riconcilia una singola email con i documenti del gestionale.
    
    Args:
        email_data: Dati email da riconciliare
    
    Returns:
        Risultato riconciliazione con match trovati
    """
    db = Database.get_db()
    
    # Costruisci testo completo per ricerca
    testo_ricerca = f"{email_data.get('subject', '')} {email_data.get('corpo', '')}"
    for allegato in email_data.get("allegati", []):
        testo_ricerca += f" {allegato.get('filename', '')}"
    
    # Cerca match
    matches = await cerca_match_in_indice(testo_ricerca)
    
    risultato = {
        "email_id": email_data.get("email_id"),
        "cartella": email_data.get("cartella"),
        "subject": email_data.get("subject"),
        "matches_trovati": len(matches),
        "matches": matches[:10],  # Top 10 match
        "allegati_count": len(email_data.get("allegati", [])),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Se ci sono match, associa i PDF
    if matches and email_data.get("allegati"):
        for match in matches[:5]:  # Top 5 match
            doc_id = match.get("id")
            doc_tipo = match.get("tipo")
            
            # Trova la collection corretta
            collection_map = {
                "fattura_ricevuta": "invoices",
                "verbale": "verbali_noleggio_completi",
                "contratto_noleggio": "veicoli_noleggio",
                "bollo": "costi_noleggio",
                "riparazioni": "costi_noleggio",
                "f24": "f24",
            }
            
            collection = collection_map.get(doc_tipo)
            if collection:
                # Aggiungi PDF allegati al documento
                for allegato in email_data.get("allegati", []):
                    if allegato.get("content_type") == "application/pdf":
                        pdf_record = {
                            "filename": allegato.get("filename"),
                            "hash": allegato.get("hash"),
                            "size": allegato.get("size"),
                            "email_id": email_data.get("email_id"),
                            "cartella": email_data.get("cartella"),
                            "scaricato_at": datetime.now(timezone.utc).isoformat()
                        }
                        
                        await db[collection].update_one(
                            {"id": doc_id},
                            {
                                "$addToSet": {"pdf_allegati": pdf_record},
                                "$set": {
                                    "email_id": email_data.get("email_id"),
                                    "email_associata": True,
                                    "updated_at": datetime.now(timezone.utc).isoformat()
                                }
                            }
                        )
                        
                        # Salva anche nell'archivio PDF
                        await db[COLLECTION_PDF_ARCHIVE].update_one(
                            {"hash": allegato.get("hash")},
                            {"$set": {
                                "hash": allegato.get("hash"),
                                "filename": allegato.get("filename"),
                                "size": allegato.get("size"),
                                "content_base64": allegato.get("content_base64"),
                                "email_id": email_data.get("email_id"),
                                "cartella": email_data.get("cartella"),
                                "documento_id": doc_id,
                                "documento_tipo": doc_tipo,
                                "created_at": datetime.now(timezone.utc).isoformat()
                            }},
                            upsert=True
                        )
                
                risultato["pdf_associati"] = True
    
    # Log della riconciliazione
    await db[COLLECTION_MATCH_LOG].insert_one(risultato)
    
    return risultato


async def scansiona_tutta_posta_e_riconcilia(limit_per_cartella: int = 50) -> Dict[str, Any]:
    """
    Scansiona TUTTA la posta elettronica e riconcilia con il gestionale.
    
    Args:
        limit_per_cartella: Numero max email per cartella
    
    Returns:
        Statistiche complete della riconciliazione
    """
    risultato_totale = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cartelle_scansionate": 0,
        "email_processate": 0,
        "match_trovati": 0,
        "pdf_associati": 0,
        "errori": [],
        "dettaglio_cartelle": {}
    }
    
    # Connessione IMAP
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except Exception as e:
        risultato_totale["errori"].append(f"Connessione IMAP fallita: {e}")
        return risultato_totale
    
    try:
        # Lista tutte le cartelle
        status, folders = mail.list()
        if status != 'OK':
            risultato_totale["errori"].append("Impossibile listare cartelle")
            return risultato_totale
        
        cartelle = []
        for folder in folders:
            try:
                folder_str = folder.decode()
                # Estrai nome cartella
                match = re.search(r'"([^"]+)"$', folder_str)
                if match:
                    cartelle.append(match.group(1))
            except (UnicodeDecodeError, AttributeError) as e:
                logger.debug(f"Errore parsing cartella email: {e}")
                continue
        
        logger.info(f"Trovate {len(cartelle)} cartelle da scansionare")
        
        # Scansiona ogni cartella
        for cartella in cartelle:
            try:
                emails = await scansiona_cartella_email(mail, cartella, limit_per_cartella)
                risultato_totale["cartelle_scansionate"] += 1
                risultato_totale["dettaglio_cartelle"][cartella] = {
                    "email_trovate": len(emails),
                    "match": 0
                }
                
                # Riconcilia ogni email
                for email_data in emails:
                    risultato_totale["email_processate"] += 1
                    
                    riconciliazione = await riconcilia_email_con_gestionale(email_data)
                    
                    if riconciliazione.get("matches_trovati", 0) > 0:
                        risultato_totale["match_trovati"] += riconciliazione["matches_trovati"]
                        risultato_totale["dettaglio_cartelle"][cartella]["match"] += 1
                    
                    if riconciliazione.get("pdf_associati"):
                        risultato_totale["pdf_associati"] += 1
                
            except Exception as e:
                risultato_totale["errori"].append(f"Errore cartella {cartella}: {str(e)}")
                continue
        
    finally:
        mail.logout()
    
    logger.info(f"Riconciliazione completata: {risultato_totale}")
    return risultato_totale


async def get_statistiche_indice() -> Dict[str, Any]:
    """Restituisce statistiche sull'indice documenti."""
    db = Database.get_db()
    
    totale = await db[COLLECTION_INDICE].count_documents({})
    
    # Conta per tipo
    pipeline = [
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}}
    ]
    per_tipo = await db[COLLECTION_INDICE].aggregate(pipeline).to_list(100)
    
    # Conta documenti con PDF associati
    con_pdf = await db[COLLECTION_INDICE].count_documents({"pdf_associati": {"$ne": []}})
    
    # Conta PDF nell'archivio
    pdf_archiviati = await db[COLLECTION_PDF_ARCHIVE].count_documents({})
    
    # Ultime riconciliazioni
    ultime = await db[COLLECTION_MATCH_LOG].find({}).sort("timestamp", -1).limit(10).to_list(10)
    
    return {
        "totale_documenti_indicizzati": totale,
        "documenti_per_tipo": {s["_id"]: s["count"] for s in per_tipo},
        "documenti_con_pdf": con_pdf,
        "pdf_archiviati": pdf_archiviati,
        "ultime_riconciliazioni": [{
            "timestamp": r.get("timestamp"),
            "cartella": r.get("cartella"),
            "subject": r.get("subject", "")[:50],
            "matches": r.get("matches_trovati", 0)
        } for r in ultime]
    }
