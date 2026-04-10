"""
Servizio Download COMPLETO Email e Allegati
Scarica TUTTI i PDF dalla posta e li salva nel database.
Gestisce deduplicazione e documenti non associati.
"""

import imaplib
import email
from email.header import decode_header
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
import hashlib
import base64
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Configurazione IMAP - Usa variabili d'ambiente
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
# Configurazione IMAP
IMAP_SERVER = "imap.gmail.com"


def get_email_credentials():
    """Ottieni credenziali email da settings."""
    from app.config import settings
    email_user = settings.EMAIL_USER or settings.GMAIL_EMAIL or settings.EMAIL_ADDRESS or ""
    email_password = settings.EMAIL_PASSWORD or settings.EMAIL_APP_PASSWORD or settings.GMAIL_APP_PASSWORD or ""
    return email_user, email_password

# Mapping categoria -> collezione MongoDB
CATEGORY_COLLECTIONS = {
    "f24": "f24_email_attachments",
    "fattura": "fatture_email_attachments", 
    "busta_paga": "cedolini_email_attachments",
    "estratto_conto": "estratti_email_attachments",
    "quietanza": "quietanze_email_attachments",
    "bonifico": "bonifici_email_attachments",
    "verbale": "verbali_email_attachments",
    "certificato_medico": "certificati_email_attachments",
    "cartella_esattoriale": "cartelle_email_attachments",
    "scheda_tecnica": "schede_tecniche_prodotti",  # Schede tecniche prodotti
    "altro": "documenti_non_associati"  # Documenti da associare manualmente
}

# Pattern per riconoscere il tipo di documento
DOCUMENT_PATTERNS = {
    "f24": [
        r"f[\s\-_]?24", r"modello\s*f24", r"tribut", r"agenzia.*entrate",
        r"inps.*contribut", r"ritenute", r"imu", r"tasi", r"acconto.*irpef"
    ],
    "fattura": [
        r"fattur[ae]", r"invoice", r"n\.\s*\d+.*del", r"ft\s*\d+",
        r"importo.*iva", r"imponibile"
    ],
    "busta_paga": [
        r"busta\s*paga", r"cedolino", r"libro\s*unico", r"lul\s*\d+",
        r"stipendio", r"retribuzione", r"netto.*pagare"
    ],
    "estratto_conto": [
        r"estratto\s*conto", r"moviment[io]", r"saldo.*precedente",
        r"c/c", r"conto\s*corrente", r"iban"
    ],
    "quietanza": [
        r"quietanza", r"ricevuta\s*pagamento", r"attestazione\s*versamento",
        r"pagamento.*effettuato", r"versato"
    ],
    "bonifico": [
        r"bonifico", r"disposizione.*pagamento", r"trasferimento",
        r"cro\s*\d+", r"trn\s*\d+"
    ],
    "verbale": [
        r"verbal[ei]", r"multa", r"sanzione", r"infrazione",
        r"codice.*strada", r"polizia.*municipal"
    ],
    "certificato_medico": [
        r"certificato\s*medico", r"inps.*malattia", r"puc\s*\d+",
        r"prognosi", r"diagnosi"
    ],
    "cartella_esattoriale": [
        r"cartella.*esattorial", r"riscossione", r"equitalia",
        r"ader.*riscossione", r"intimazione"
    ],
    "scheda_tecnica": [
        r"scheda\s*tecnica", r"technical\s*sheet", r"data\s*sheet",
        r"specifica.*tecnic", r"caratteristiche.*prodotto"
    ]
}


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
    except Exception as e:
        logger.debug(f"Errore decodifica header: {e}")
        return str(header_value)


def calculate_pdf_hash(content: bytes) -> str:
    """Calcola hash MD5 del contenuto PDF per deduplicazione."""
    return hashlib.md5(content).hexdigest()


def categorize_document(filename: str, subject: str = "", body: str = "") -> str:
    """
    Categorizza un documento in base al nome file, oggetto e contenuto.
    """
    text_to_check = f"{filename} {subject} {body}".lower()
    
    for category, patterns in DOCUMENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return category
    
    return "altro"


def extract_period_from_text(text: str) -> Dict[str, Any]:
    """Estrae mese e anno dal testo."""
    result = {"mese": None, "anno": None}
    
    # Pattern mese/anno
    mesi_it = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    
    text_lower = text.lower()
    
    # Pattern 1: "gennaio 2025", "febbraio 2024"
    for mese_nome, mese_num in mesi_it.items():
        pattern = rf'{mese_nome}\s*[/_\-]?\s*(\d{{4}})'
        match = re.search(pattern, text_lower)
        if match:
            result["mese"] = mese_num
            result["anno"] = int(match.group(1))
            return result
    
    # Pattern 2: "01/2025"
    match = re.search(r'(\d{1,2})[/_\-](\d{4})', text)
    if match:
        mese = int(match.group(1))
        anno = int(match.group(2))
        if 1 <= mese <= 12 and 2020 <= anno <= 2030:
            result["mese"] = mese
            result["anno"] = anno
            return result
    
    # Pattern 3: "2025" solo anno
    match = re.search(r'20(2[0-9])', text)
    if match:
        result["anno"] = int(f"20{match.group(1)}")
    
    return result


class EmailFullDownloader:
    """
    Scarica TUTTI gli allegati PDF dalla posta e li salva nel database.
    Supporta deduplicazione e categorizzazione automatica.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.connection = None
        self.stats = {
            "emails_processed": 0,
            "pdfs_downloaded": 0,
            "pdfs_duplicates": 0,
            "pdfs_by_category": {},
            "errors": []
        }
        self._cached_keywords = None  # Cache per le parole chiave
    
    async def _load_admin_keywords(self) -> list:
        """
        Carica le parole chiave amministrative dal database.
        Le parole chiave sono configurate nella pagina Admin.
        """
        # Usa cache se disponibile
        if self._cached_keywords is not None:
            return self._cached_keywords
        
        try:
            config = await self.db["config"].find_one({"tipo": "parole_chiave"})
            if config:
                keywords = []
                # Combina tutte le categorie di parole chiave
                for key in ["generale", "fatture", "f24", "buste_paga", "estratti_conto", "verbali", "altro"]:
                    if key in config and isinstance(config[key], list):
                        keywords.extend(config[key])
                
                # Rimuovi duplicati e valori vuoti
                keywords = list(set(kw.strip() for kw in keywords if kw and kw.strip()))
                
                if keywords:
                    self._cached_keywords = keywords
                    logger.info(f"Caricate {len(keywords)} parole chiave da Admin")
                    return keywords
        except Exception as e:
            logger.warning(f"Errore caricamento parole chiave da DB: {e}")
        
        # Fallback: parole chiave di default se non configurate
        default_keywords = [
            "fattura", "fatture", "invoice", "f24", "tribut",
            "cedolino", "busta paga", "stipendio", "estratto conto",
            "verbale", "multa", "bonifico", "pagamento", "quietanza",
            "scadenza", "importo", "scheda tecnica"
        ]
        self._cached_keywords = default_keywords
        logger.info(f"Usando {len(default_keywords)} parole chiave di default")
        return default_keywords
    
    def connect(self) -> bool:
        """Connette al server IMAP."""
        try:
            email_user, email_password = get_email_credentials()
            if not email_user or not email_password:
                raise Exception("Credenziali email non configurate")
            
            self.connection = imaplib.IMAP4_SSL(IMAP_SERVER)
            self.connection.login(email_user, email_password)
            logger.info(f"Connesso a {IMAP_SERVER} come {email_user}")
            return True
        except Exception as e:
            logger.error(f"Errore connessione IMAP: {e}")
            self.stats["errors"].append(f"Connessione: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnette dal server IMAP."""
        if self.connection:
            try:
                self.connection.logout()
            except Exception as e:
                logger.warning(f"Errore durante disconnessione IMAP: {e}")
            self.connection = None
    
    async def check_duplicate(self, pdf_hash: str) -> bool:
        """Verifica se un PDF con questo hash esiste già."""
        # Controlla in tutte le collezioni di allegati
        for collection_name in CATEGORY_COLLECTIONS.values():
            existing = await self.db[collection_name].find_one({"pdf_hash": pdf_hash})
            if existing:
                return True
        return False
    
    async def save_pdf_to_db(
        self,
        pdf_content: bytes,
        filename: str,
        category: str,
        email_info: Dict[str, Any],
        period_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Salva un PDF nel database nella collezione appropriata.
        Ritorna l'ID del documento salvato o None se duplicato.
        """
        pdf_hash = calculate_pdf_hash(pdf_content)
        
        # Verifica duplicato
        if await self.check_duplicate(pdf_hash):
            self.stats["pdfs_duplicates"] += 1
            logger.debug(f"PDF duplicato saltato: {filename}")
            return None
        
        # Prepara documento
        doc_id = str(uuid.uuid4())
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        document = {
            "id": doc_id,
            "filename": filename,
            "pdf_data": pdf_base64,
            "pdf_hash": pdf_hash,
            "pdf_size": len(pdf_content),
            "category": category,
            "email_subject": email_info.get("subject", ""),
            "email_from": email_info.get("from", ""),
            "email_date": email_info.get("date", ""),
            "email_uid": email_info.get("uid", ""),
            "mese": period_info.get("mese"),
            "anno": period_info.get("anno"),
            "associato": False,  # Da associare manualmente se in "altro"
            "documento_associato_id": None,
            "documento_associato_collection": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed": False
        }
        
        # Determina collezione
        collection_name = CATEGORY_COLLECTIONS.get(category, "documenti_non_associati")
        
        # Salva nel database
        result = await self.db[collection_name].insert_one(document)
        
        if not result.inserted_id:
            logger.error(f"Inserimento fallito per {filename} in {collection_name}")
            return None
        
        self.stats["pdfs_downloaded"] += 1
        self.stats["pdfs_by_category"][category] = self.stats["pdfs_by_category"].get(category, 0) + 1
        
        logger.info(f"PDF salvato: {filename} -> {collection_name}")
        return doc_id
    
    def extract_pdfs_from_email(self, msg: email.message.Message) -> List[Tuple[str, bytes]]:
        """
        Estrae SOLO i PDF da un'email.
        ESCLUDE: PNG, JPG, immagini, firme digitali, XML.
        """
        pdfs = []
        
        # Estensioni da ESCLUDERE completamente
        EXCLUDED_EXTENSIONS = {
            # Firme digitali
            '.p7s', '.p7m', '.p7c', '.sig', '.asc', '.gpg', '.pgp',
            # Testo / XML
            '.xml', '.txt', '.html', '.htm',
            # IMMAGINI - NON AMMINISTRATIVE
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.svg',
            # Altri
            '.zip', '.rar', '.7z', '.exe', '.dll'
        }
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Verifica se è un PDF
                filename = part.get_filename()
                if filename:
                    filename = decode_mime_header(filename)
                    
                    # Salta file esclusi
                    ext = os.path.splitext(filename.lower())[1]
                    if ext in EXCLUDED_EXTENSIONS:
                        logger.debug(f"File escluso (estensione): {filename}")
                        continue
                
                # SOLO PDF veri - niente immagini
                is_pdf = (
                    content_type == "application/pdf" or
                    (filename and filename.lower().endswith(".pdf"))
                )
                
                if is_pdf:
                    try:
                        content = part.get_payload(decode=True)
                        if content and len(content) > 500:  # File valido (>500 bytes)
                            if not filename:
                                filename = f"allegato_{uuid.uuid4().hex[:8]}.pdf"
                            pdfs.append((filename, content))
                    except Exception as e:
                        logger.debug(f"Errore estrazione allegato: {e}")
        else:
            # Email non multipart, verifica se è un PDF direttamente
            content_type = msg.get_content_type()
            if content_type == "application/pdf":
                try:
                    content = msg.get_payload(decode=True)
                    if content:
                        filename = msg.get_filename() or "documento.pdf"
                        pdfs.append((decode_mime_header(filename), content))
                except:
                    pass
        
        return pdfs
    
    async def process_email(self, email_uid: bytes, msg: email.message.Message) -> int:
        """
        Processa una singola email ed estrae i PDF.
        FILTRA: scarica solo email con parole chiave AMMINISTRATIVE dal database.
        """
        pdfs_saved = 0
        
        # Estrai info email
        subject = decode_mime_header(msg.get("Subject", ""))
        from_addr = decode_mime_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        
        # Estrai body per categorizzazione
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                        break
                    except:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
            except:
                pass
        
        # ============================================================
        # FILTRO PAROLE CHIAVE AMMINISTRATIVE DA DATABASE
        # Carica le parole chiave configurate dall'utente in /admin
        # ============================================================
        admin_keywords = await self._load_admin_keywords()
        
        # Combina testo ricercabile: oggetto + corpo
        search_text = f"{subject} {body}".lower()
        
        # Estrai anche i nomi degli allegati
        attachment_names = []
        if msg.is_multipart():
            for part in msg.walk():
                filename = part.get_filename()
                if filename:
                    attachment_names.append(decode_mime_header(filename).lower())
        
        search_text += " " + " ".join(attachment_names)
        
        # Verifica se contiene almeno UNA parola chiave amministrativa
        has_admin_keyword = any(kw.lower() in search_text for kw in admin_keywords)
        
        if not has_admin_keyword:
            # Email non amministrativa - SALTA
            logger.debug(f"Email saltata (no keyword): {subject[:50]}")
            return 0
        
        email_info = {
            "uid": email_uid.decode() if isinstance(email_uid, bytes) else str(email_uid),
            "subject": subject,
            "from": from_addr,
            "date": date_str
        }
        
        # Estrai tutti i PDF
        pdfs = self.extract_pdfs_from_email(msg)
        
        for filename, content in pdfs:
            # Categorizza
            category = categorize_document(filename, subject, body)
            
            # Estrai periodo
            period_info = extract_period_from_text(f"{filename} {subject}")
            
            # Salva nel database
            doc_id = await self.save_pdf_to_db(
                pdf_content=content,
                filename=filename,
                category=category,
                email_info=email_info,
                period_info=period_info
            )
            
            if doc_id:
                pdfs_saved += 1
        
        return pdfs_saved
    
    async def download_all_emails(
        self,
        folder: str = "INBOX",
        days_back: int = 365,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Scarica TUTTE le email con PDF degli ultimi N giorni.
        """
        if not self.connect():
            return {"success": False, "error": "Connessione IMAP fallita", "stats": self.stats}
        
        try:
            # Seleziona cartella
            status, _ = self.connection.select(folder)
            if status != "OK":
                return {"success": False, "error": f"Cartella {folder} non trovata", "stats": self.stats}
            
            # Calcola data di inizio
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            
            # Cerca tutte le email dal periodo
            search_criteria = f'(SINCE "{since_date}")'
            status, messages = self.connection.search(None, search_criteria)
            
            if status != "OK":
                return {"success": False, "error": "Ricerca email fallita", "stats": self.stats}
            
            email_ids = messages[0].split()
            total_emails = len(email_ids)
            logger.info(f"Trovate {total_emails} email da processare")
            
            # Processa in batch
            for i in range(0, total_emails, batch_size):
                batch = email_ids[i:i + batch_size]
                logger.info(f"Processando batch {i//batch_size + 1}: {len(batch)} email")
                
                for email_uid in batch:
                    try:
                        # Scarica email
                        status, msg_data = self.connection.fetch(email_uid, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        # Parse email
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        # Processa
                        await self.process_email(email_uid, msg)
                        self.stats["emails_processed"] += 1
                        
                    except Exception as e:
                        logger.error(f"Errore processing email {email_uid}: {e}")
                        self.stats["errors"].append(str(e))
                
                # Log progresso
                progress = min(i + batch_size, total_emails)
                logger.info(f"Progresso: {progress}/{total_emails} email processate")
            
            return {
                "success": True,
                "stats": self.stats
            }
            
        except Exception as e:
            logger.error(f"Errore download email: {e}")
            return {"success": False, "error": str(e), "stats": self.stats}
        
        finally:
            self.disconnect()
    
    async def download_single_day(self, target_date: datetime) -> Dict[str, Any]:
        """
        Scarica email di un singolo giorno specifico.
        """
        if not self.connect():
            return {"success": False, "error": "Connessione IMAP fallita"}
        
        try:
            self.connection.select("INBOX")
            
            # Cerca email di quel giorno specifico
            date_str = target_date.strftime("%d-%b-%Y")
            next_date_str = (target_date + timedelta(days=1)).strftime("%d-%b-%Y")
            
            search_criteria = f'(SINCE "{date_str}" BEFORE "{next_date_str}")'
            status, messages = self.connection.search(None, search_criteria)
            
            if status != "OK":
                return {"success": False, "error": "Ricerca fallita"}
            
            email_ids = messages[0].split()
            logger.info(f"Trovate {len(email_ids)} email per {date_str}")
            
            for email_uid in email_ids:
                try:
                    status, msg_data = self.connection.fetch(email_uid, "(RFC822)")
                    if status == "OK":
                        msg = email.message_from_bytes(msg_data[0][1])
                        await self.process_email(email_uid, msg)
                        self.stats["emails_processed"] += 1
                except Exception as e:
                    logger.error(f"Errore: {e}")
            
            return {"success": True, "stats": self.stats}
            
        finally:
            self.disconnect()


async def associate_pdf_to_document(
    db: AsyncIOMotorDatabase,
    pdf_id: str,
    source_collection: str,
    target_document_id: str,
    target_collection: str
) -> bool:
    """
    Associa un PDF scaricato a un documento esistente.
    Copia il pdf_data nella collezione di destinazione.
    """
    try:
        # Trova il PDF
        pdf_doc = await db[source_collection].find_one({"id": pdf_id})
        if not pdf_doc:
            return False
        
        # Aggiorna documento destinazione con il PDF
        result = await db[target_collection].update_one(
            {"id": target_document_id},
            {
                "$set": {
                    "pdf_data": pdf_doc["pdf_data"],
                    "pdf_filename": pdf_doc["filename"],
                    "pdf_hash": pdf_doc["pdf_hash"]
                }
            }
        )
        
        if result.modified_count > 0:
            # Marca il PDF come associato
            await db[source_collection].update_one(
                {"id": pdf_id},
                {
                    "$set": {
                        "associato": True,
                        "documento_associato_id": target_document_id,
                        "documento_associato_collection": target_collection,
                        "associated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Errore associazione PDF: {e}")
        return False


async def get_documenti_non_associati(
    db: AsyncIOMotorDatabase,
    category: str = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Recupera i documenti non ancora associati per l'associazione manuale.
    """
    query = {"associato": False}
    if category:
        query["category"] = category
    
    # Cerca in tutte le collezioni di allegati
    results = []
    for coll_name in CATEGORY_COLLECTIONS.values():
        cursor = db[coll_name].find(
            query,
            {"_id": 0, "pdf_data": 0}  # Escludi PDF pesante
        ).limit(limit)
        
        async for doc in cursor:
            doc["source_collection"] = coll_name
            results.append(doc)
    
    return results[:limit]


async def smart_auto_associate(db: AsyncIOMotorDatabase) -> Dict[str, int]:
    """
    Tenta di associare automaticamente i PDF ai documenti esistenti
    basandosi su filename, periodo e categoria.
    """
    stats = {"associated": 0, "skipped": 0, "errors": 0}
    
    # ========== ASSOCIAZIONE CEDOLINI (BUSTE PAGA) ==========
    # Pattern filename: "Busta paga - Vespa Vincenzo - Settembre 2024 - 2.pdf"
    mesi_it = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    
    cursor = db["cedolini_email_attachments"].find({"associato": False})
    async for pdf_doc in cursor:
        try:
            filename = pdf_doc.get("filename", "")
            
            # Estrai nome dipendente e periodo dal filename
            # Pattern: "Busta paga - COGNOME NOME - MESE ANNO"
            import re
            match = re.search(r'[Bb]usta\s*[Pp]aga\s*-\s*([^-]+)\s*-\s*(\w+)\s*(\d{4})', filename)
            
            if match:
                nome_completo = match.group(1).strip()
                mese_str = match.group(2).lower()
                anno = int(match.group(3))
                mese = mesi_it.get(mese_str, pdf_doc.get("mese"))
                
                # Cerca dipendente per nome/cognome
                parts = nome_completo.split()
                if len(parts) >= 2:
                    cognome = parts[0]
                    nome = " ".join(parts[1:])
                    
                    # Cerca cedolino corrispondente
                    cedolino = await db["cedolini"].find_one({
                        "mese": mese,
                        "anno": anno,
                        "$or": [
                            {"pdf_data": None},
                            {"pdf_data": ""},
                            {"pdf_data": {"$exists": False}}
                        ]
                    })
                    
                    if not cedolino:
                        # Cerca anche per nome dipendente
                        cedolino = await db["cedolini"].find_one({
                            "dipendente": {"$regex": cognome, "$options": "i"},
                            "mese": mese,
                            "anno": anno,
                            "$or": [
                                {"pdf_data": None},
                                {"pdf_data": ""},
                                {"pdf_data": {"$exists": False}}
                            ]
                        })
                    
                    if cedolino:
                        # Associa
                        await db["cedolini"].update_one(
                            {"id": cedolino["id"]},
                            {"$set": {
                                "pdf_data": pdf_doc["pdf_data"],
                                "pdf_filename": filename,
                                "pdf_hash": pdf_doc.get("pdf_hash")
                            }}
                        )
                        await db["cedolini_email_attachments"].update_one(
                            {"id": pdf_doc["id"]},
                            {"$set": {
                                "associato": True,
                                "documento_associato_id": cedolino["id"],
                                "documento_associato_collection": "cedolini",
                                "associated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        stats["associated"] += 1
                        logger.info(f"Cedolino associato: {filename} -> {cedolino['id']}")
                        continue
            
            stats["skipped"] += 1
            
        except Exception as e:
            logger.error(f"Errore auto-associazione cedolino: {e}")
            stats["errors"] += 1
    
    # ========== ASSOCIAZIONE F24 ==========
    cursor = db["f24_email_attachments"].find({"associato": False})
    async for pdf_doc in cursor:
        try:
            filename = pdf_doc.get("filename", "")
            
            # Cerca F24 con lo stesso filename che non ha ancora pdf_data
            f24 = await db["f24_unificato"].find_one({
                "$and": [
                    {"$or": [
                        {"file_name": filename},
                        {"filename": filename},
                        {"file_name": {"$regex": filename[:30], "$options": "i"}}
                    ]},
                    {"$or": [
                        {"pdf_data": None},
                        {"pdf_data": ""},
                        {"pdf_data": {"$exists": False}}
                    ]}
                ]
            })
            
            if f24:
                await db["f24_unificato"].update_one(
                    {"id": f24["id"]},
                    {"$set": {
                        "pdf_data": pdf_doc["pdf_data"],
                        "pdf_filename": filename,
                        "pdf_hash": pdf_doc.get("pdf_hash")
                    }}
                )
                await db["f24_email_attachments"].update_one(
                    {"id": pdf_doc["id"]},
                    {"$set": {
                        "associato": True,
                        "documento_associato_id": f24["id"],
                        "documento_associato_collection": "f24_commercialista",
                        "associated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                stats["associated"] += 1
                logger.info(f"F24 associato: {filename}")
            else:
                stats["skipped"] += 1
                
        except Exception as e:
            logger.error(f"Errore auto-associazione F24: {e}")
            stats["errors"] += 1
    
    return stats


async def smart_auto_associate_v2(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Versione migliorata dell'auto-associazione che:
    1. Lavora con la collezione documents_inbox esistente
    2. Associa payslips leggendo i PDF dal filesystem
    3. Associa fatture per P.IVA e importo
    4. Gestisce F24 per periodo e tributi
    """
    stats = {
        "payslips_updated": 0,
        "fatture_associated": 0,
        "f24_associated": 0,
        "documents_inbox_processed": 0,
        "errors": []
    }
    
    # ========== ARCHITETTURA MONGODB-ONLY ==========
    # Questa funzione è DEPRECATA per la migrazione legacy.
    # Tutti i nuovi flussi devono usare pdf_data già presente in MongoDB.
    # Le funzioni sottostanti sono mantenute per retrocompatibilità con dati esistenti.
    
    # ========== 1. SKIP AGGIORNAMENTO DA FILESYSTEM ==========
    # I nuovi documenti devono già avere pdf_data
    # Questo blocco è deprecato ma mantenuto per riferimento
    logger.info("Migrazione payslips da filesystem deprecata - usa pdf_data direttamente")
    
    # ========== 2. PROCESSA DOCUMENTS_INBOX ==========
    # Marca i documenti processati e li collega dove possibile
    
    mesi_it = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    
    # 2a. Processa F24 da documents_inbox (MongoDB-only)
    cursor = db["documents_inbox"].find({
        "category": "f24",
        "status": {"$ne": "associato"},
        "pdf_data": {"$exists": True, "$nin": [None, ""]}
    })
    
    async for doc in cursor:
        try:
            filename = doc.get("filename", "")
            pdf_data = doc.get("pdf_data", "")
            
            # Estrai periodo dal filename (es: F24_IVA_09_2025, F24_dicembre_2025)
            period_match = re.search(r'(\d{2})_(\d{4})|(\w+)_(\d{4})', filename)
            mese = None
            anno = None
            
            if period_match:
                if period_match.group(1):  # Pattern numerico: 09_2025
                    mese = int(period_match.group(1))
                    anno = int(period_match.group(2))
                elif period_match.group(3):  # Pattern testuale: dicembre_2025
                    mese_str = period_match.group(3).lower()
                    mese = mesi_it.get(mese_str)
                    anno = int(period_match.group(4))
            
            # Cerca F24 corrispondente
            query = {}
            if mese and anno:
                query = {"mese": mese, "anno": anno}
            else:
                # Cerca per nome file simile
                query = {"$or": [
                    {"file_name": {"$regex": filename[:20], "$options": "i"}},
                    {"filename": {"$regex": filename[:20], "$options": "i"}}
                ]}
            
            f24 = await db["f24_unificato"].find_one(query)
            
            if f24 and pdf_data:
                # Architettura MongoDB-only: usa pdf_data già presente
                await db["f24_unificato"].update_one(
                    {"id": f24["id"]},
                    {"$set": {
                        "pdf_data": pdf_data,  # MongoDB-only
                        "pdf_hash": calculate_pdf_hash(base64.b64decode(pdf_data)) if pdf_data else None
                    }}
                )
                
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "associato",
                        "associated_to": f24["id"],
                        "associated_collection": "f24_commercialista",
                        "associated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                stats["f24_associated"] += 1
                stats["documents_inbox_processed"] += 1
                logger.info(f"F24 associato: {filename}")
            
        except Exception as e:
            logger.error(f"Errore associazione F24: {e}")
            stats["errors"].append(f"F24 {doc.get('id')}: {str(e)}")
    
    # 2b. Processa Fatture da documents_inbox (MongoDB-only)
    cursor = db["documents_inbox"].find({
        "category": "fattura",
        "status": {"$ne": "associato"},
        "pdf_data": {"$exists": True, "$nin": [None, ""]}
    })
    
    async for doc in cursor:
        try:
            filename = doc.get("filename", "")
            pdf_data = doc.get("pdf_data", "")
            email_subject = doc.get("email_subject", "")
            
            # Estrai numero fattura dal filename o subject
            # Pattern comuni: FT_001_2025, Fattura_123, n_456
            num_match = re.search(r'(?:FT|fattura|n)[_\s\-]?(\d+)', filename + " " + email_subject, re.IGNORECASE)
            
            invoice = None
            if num_match:
                num = num_match.group(1)
                invoice = await db["invoices"].find_one({
                    "invoice_number": {"$regex": num, "$options": "i"}
                })
            
            if invoice and pdf_data:
                # Architettura MongoDB-only: usa pdf_data già presente
                await db["invoices"].update_one(
                    {"id": invoice["id"]},
                    {"$set": {
                        "pdf_data": pdf_data,  # MongoDB-only
                        "pdf_hash": calculate_pdf_hash(base64.b64decode(pdf_data)) if pdf_data else None
                    }}
                )
                
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "associato",
                        "associated_to": invoice["id"],
                        "associated_collection": "invoices",
                        "associated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                stats["fatture_associated"] += 1
                stats["documents_inbox_processed"] += 1
                logger.info(f"Fattura associata: {filename}")
            
        except Exception as e:
            logger.error(f"Errore associazione fattura: {e}")
            stats["errors"].append(f"Fattura {doc.get('id')}: {str(e)}")
    
    return stats


async def populate_payslips_pdf_data(db: AsyncIOMotorDatabase) -> Dict[str, int]:
    """
    DEPRECATO: Funzione di migrazione legacy per popolare pdf_data da filesystem.
    I nuovi documenti devono già avere pdf_data quando vengono scaricati dalle email.
    Mantenuta per retrocompatibilità con dati esistenti.
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0, "deprecated": True}
    
    logger.warning("populate_payslips_pdf_data è DEPRECATO. I nuovi flussi usano pdf_data direttamente.")
    
    # Cerca payslips che hanno solo pdf_data mancante (per migrazione)
    cursor = db["cedolini"].find({
        "$or": [
            {"pdf_data": None},
            {"pdf_data": ""},
            {"pdf_data": {"$exists": False}}
        ]
    })
    
    async for payslip in cursor:
        try:
            # Se non ha pdf_data, lo salta - i nuovi documenti devono averlo
            stats["skipped"] += 1
            continue
            
        except Exception as e:
            logger.error(f"Errore popolamento payslip: {e}")
            stats["errors"] += 1
    
    return stats


async def get_documents_inbox_stats(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Statistiche sulla collezione documents_inbox.
    """
    pipeline = [
        {"$group": {
            "_id": {"category": "$category", "status": "$status"},
            "count": {"$sum": 1}
        }}
    ]
    
    stats = {
        "by_category": {},
        "by_status": {},
        "total": await db["documents_inbox"].count_documents({})
    }
    
    async for doc in db["documents_inbox"].aggregate(pipeline):
        cat = doc["_id"].get("category", "unknown")
        status = doc["_id"].get("status", "unknown")
        count = doc["count"]
        
        if cat not in stats["by_category"]:
            stats["by_category"][cat] = {"total": 0, "nuovo": 0, "processato": 0, "associato": 0}
        stats["by_category"][cat]["total"] += count
        stats["by_category"][cat][status] = stats["by_category"][cat].get(status, 0) + count
        
        stats["by_status"][status] = stats["by_status"].get(status, 0) + count
    
    return stats


async def sync_filesystem_pdfs_to_db(db: AsyncIOMotorDatabase, base_dir: str = "/app/documents") -> Dict[str, Any]:
    """
    Scansiona i PDF sul filesystem e li sincronizza con documents_inbox.
    Per ogni file:
    1. Calcola hash per deduplicazione
    2. Se nuovo, lo aggiunge a documents_inbox
    3. Aggiorna il filepath se il file esiste ma il path è cambiato
    """
    stats = {
        "files_scanned": 0,
        "new_added": 0,
        "paths_updated": 0,
        "duplicates_skipped": 0,
        "errors": []
    }
    
    # Mapping directory -> categoria
    DIR_TO_CATEGORY = {
        "F24": "f24",
        "Fatture": "fattura",
        "Buste Paga": "busta_paga",
        "Estratti Conto": "estratto_conto",
        "Quietanze": "quietanza",
        "Bonifici": "bonifico",
        "Verbali": "verbale",
        "Certificati Medici": "certificato_medico",
        "Cartelle Esattoriali": "cartella_esattoriale",
        "Altri": "altro"
    }
    
    for dir_name, category in DIR_TO_CATEGORY.items():
        dir_path = os.path.join(base_dir, dir_name)
        if not os.path.exists(dir_path):
            continue
        
        for filename in os.listdir(dir_path):
            if not filename.lower().endswith('.pdf'):
                continue
            
            filepath = os.path.join(dir_path, filename)
            stats["files_scanned"] += 1
            
            try:
                # Leggi e calcola hash
                with open(filepath, "rb") as f:
                    content = f.read()
                
                file_hash = calculate_pdf_hash(content)
                
                # Controlla se esiste già per hash
                existing = await db["documents_inbox"].find_one({"file_hash": file_hash})
                
                if existing:
                    # Aggiorna il filepath se diverso
                    if existing.get("filepath") != filepath:
                        await db["documents_inbox"].update_one(
                            {"id": existing["id"]},
                            {"$set": {"filepath": filepath, "file_exists": True}}
                        )
                        stats["paths_updated"] += 1
                    else:
                        stats["duplicates_skipped"] += 1
                    continue
                
                # Nuovo documento - aggiungi
                doc_id = str(uuid.uuid4())
                new_doc = {
                    "id": doc_id,
                    "filename": filename,
                    "filepath": filepath,
                    "category": category,
                    "category_label": dir_name,
                    "size_bytes": len(content),
                    "file_hash": file_hash,
                    "status": "nuovo",
                    "processed": False,
                    "file_exists": True,
                    "source": "filesystem_sync",
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db["documents_inbox"].insert_one(new_doc)
                stats["new_added"] += 1
                
            except Exception as e:
                logger.error(f"Errore sync file {filepath}: {e}")
                stats["errors"].append(f"{filename}: {str(e)}")
    
    return stats


async def associate_f24_from_filesystem(db: AsyncIOMotorDatabase) -> Dict[str, int]:
    """
    Associa i PDF F24 dal filesystem ai record f24_commercialista.
    Usa pattern matching su periodo e tipo tributo.
    """
    stats = {"associated": 0, "skipped": 0, "errors": 0}
    
    mesi_it = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    
    # Trova tutti gli F24 in documents_inbox con file esistente
    cursor = db["documents_inbox"].find({
        "category": "f24",
        "file_exists": True,
        "status": {"$ne": "associato"}
    })
    
    async for doc in cursor:
        try:
            filename = doc.get("filename", "")
            filepath = doc.get("filepath", "")
            
            if not filepath or not os.path.exists(filepath):
                stats["skipped"] += 1
                continue
            
            # Estrai info dal filename
            # Pattern comuni: F24_IVA_09_2025, F24_ravv_II_acc_Ires_2023
            
            mese = None
            anno = None
            tributo_pattern = None
            
            # Pattern 1: mese numerico/anno (IVA_09_2025, IVA_11.25)
            match = re.search(r'(\d{1,2})[._](\d{2,4})', filename)
            if match:
                m = int(match.group(1))
                a = match.group(2)
                if len(a) == 2:
                    a = f"20{a}"
                anno = int(a)
                if 1 <= m <= 12:
                    mese = m
            
            # Pattern 2: anno esplicito
            if not anno:
                match = re.search(r'20(2[0-9])', filename)
                if match:
                    anno = int(f"20{match.group(1)}")
            
            # Identifica tipo tributo
            filename_lower = filename.lower()
            if "iva" in filename_lower:
                tributo_pattern = "iva"
            elif "ires" in filename_lower or "irpef" in filename_lower:
                tributo_pattern = "imposte_reddito"
            elif "inps" in filename_lower:
                tributo_pattern = "contributi"
            elif "imu" in filename_lower or "tasi" in filename_lower:
                tributo_pattern = "tributi_locali"
            elif "1040" in filename_lower or "ritenute" in filename_lower:
                tributo_pattern = "ritenute"
            
            # Cerca F24 corrispondente
            query = {"$or": [
                {"pdf_data": None},
                {"pdf_data": ""},
                {"pdf_data": {"$exists": False}}
            ]}
            
            if mese and anno:
                query["mese"] = mese
                query["anno"] = anno
            elif anno:
                query["anno"] = anno
            
            f24 = await db["f24_unificato"].find_one(query)
            
            if f24:
                # Leggi PDF e associa
                with open(filepath, "rb") as f:
                    pdf_content = f.read()
                
                pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
                
                await db["f24_unificato"].update_one(
                    {"id": f24["id"]},
                    {"$set": {
                        "pdf_data": pdf_base64,
                        "pdf_hash": calculate_pdf_hash(pdf_content),
                        "pdf_filepath": filepath,
                        "pdf_filename": filename
                    }}
                )
                
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "associato",
                        "associated_to": f24["id"],
                        "associated_collection": "f24_commercialista",
                        "associated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                stats["associated"] += 1
                logger.info(f"F24 associato: {filename} -> {f24['id']}")
            else:
                stats["skipped"] += 1
                
        except Exception as e:
            logger.error(f"Errore associazione F24: {e}")
            stats["errors"] += 1
    
    return stats


async def process_cedolini_to_prima_nota(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Processa i cedolini scaricati ed estrae i dati per prima_nota_salari.
    Usa PyMuPDF per estrarre testo e pattern matching per i dati.
    """
    import fitz  # PyMuPDF
    
    stats = {
        "processed": 0,
        "created_prima_nota": 0,
        "skipped": 0,
        "errors": []
    }
    
    mesi_it = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
        "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12
    }
    
    # Trova cedolini non processati
    cursor = db["cedolini_email_attachments"].find({
        "processed": {"$ne": True},
        "pdf_data": {"$exists": True, "$ne": None}
    })
    
    async for cedolino in cursor:
        try:
            # Decodifica PDF
            pdf_bytes = base64.b64decode(cedolino["pdf_data"])
            
            # Estrai testo con PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            if not text.strip():
                stats["skipped"] += 1
                continue
            
            # Estrai dati dal testo
            parsed_data = {}
            
            # Nome dipendente - pattern specifico per cedolini italiani
            # La riga tipica è: "31/12/2019 VESPA VINCENZO  26/12/1967 VSPVCN67T26F839P"
            # Cerchiamo data + NOME COGNOME + data_nascita + codice_fiscale
            nome_patterns = [
                # Pattern completo con CF: DATA NOME DATA_NASCITA CF
                r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z]+\s+[A-Z][A-Z]+)\s+\d{2}/\d{2}/\d{4}\s+[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]',
                # Pattern senza data nascita ma con CF
                r'([A-Z][A-Z]+\s+[A-Z][A-Z]+)\s+\d{2}/\d{2}/\d{4}\s+[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]',
            ]
            for pattern in nome_patterns:
                match = re.search(pattern, text)
                if match:
                    parsed_data['dipendente_nome'] = match.group(1).strip().title()
                    break
            
            # Se non trovato nel testo, usa il filename
            if not parsed_data.get('dipendente_nome'):
                filename = cedolino.get("filename", "")
                match = re.search(r'(?:Busta paga|Cedolino)[^\w-]*-?\s*([A-Za-z]+\s+[A-Za-z]+)', filename, re.IGNORECASE)
                if match:
                    parsed_data['dipendente_nome'] = match.group(1).strip().title()
            
            # Codice Fiscale
            cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
            if cf_match:
                parsed_data['codice_fiscale'] = cf_match.group(1)
            
            # Periodo (mese/anno) - pattern specifico per cedolini
            # Pattern: "DICEMBRE  2019" o "NOVEMBRE 2024"
            mese_pattern = r'(GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE)\s+(\d{4})'
            match = re.search(mese_pattern, text, re.IGNORECASE)
            if match:
                mese_nome = match.group(1).lower()
                parsed_data['mese'] = mesi_it.get(mese_nome[:3])
                parsed_data['anno'] = int(match.group(2))
            
            # Importi
            # Netto - pattern per cedolini italiani: cerca dopo "TOTALE NETTO" o simili
            # Il formato può essere "1.035,00+" o "1035,00"
            netto_patterns = [
                r'TOTALE\s+NETTO\s*([\d.,]+)',
                r'(?:Netto|Netto a pagare|Netto in busta)[:\s]*[€]?\s*([\d.,]+)',
                r'(\d{1,3}(?:\.\d{3})*,\d{2})\+?\s*$',  # Pattern numerico con + alla fine
            ]
            for pattern in netto_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match_val in matches:
                    val = match_val if isinstance(match_val, str) else match_val[0]
                    val = val.replace('.', '').replace(',', '.').replace('+', '')
                    try:
                        num = float(val)
                        if 100 < num < 10000:  # Range ragionevole per uno stipendio netto
                            parsed_data['netto'] = num
                            break
                    except:
                        pass
                if parsed_data.get('netto'):
                    break
            
            # Lordo / Totale Competenze
            lordo_match = re.search(r'TOTALE\s+COMPETENZE\s*([\d.,]+)', text, re.IGNORECASE)
            if lordo_match:
                val = lordo_match.group(1).replace('.', '').replace(',', '.').replace('+', '')
                try:
                    parsed_data['lordo'] = float(val)
                except:
                    pass
            
            # INPS (Ritenute Previdenziali)
            inps_match = re.search(r'RITENUTE\s+PREVIDENZIALI\s*([\d.,]+)', text, re.IGNORECASE)
            if inps_match:
                val = inps_match.group(1).replace('.', '').replace(',', '.').replace('-', '')
                try:
                    parsed_data['inps'] = float(val)
                except:
                    pass
            
            # IRPEF (Ritenute Fiscali)
            irpef_match = re.search(r'RITENUTE\s+FISCALI\s*([\d.,]+)', text, re.IGNORECASE)
            if irpef_match:
                val = irpef_match.group(1).replace('.', '').replace(',', '.').replace('-', '')
                try:
                    parsed_data['irpef'] = float(val)
                except:
                    pass
            
            # Se abbiamo abbastanza dati, crea record in prima_nota_salari
            if parsed_data.get('dipendente_nome') and parsed_data.get('netto'):
                # Cerca dipendente esistente
                dipendente = await db["dipendenti"].find_one({
                    "$or": [
                        {"nome_completo": {"$regex": parsed_data['dipendente_nome'], "$options": "i"}},
                        {"codice_fiscale": parsed_data.get('codice_fiscale', '')}
                    ]
                })
                
                dipendente_id = dipendente["id"] if dipendente else None
                
                # Verifica se esiste già in prima_nota_salari
                existing = await db["prima_nota_salari"].find_one({
                    "dipendente_nome": {"$regex": parsed_data['dipendente_nome'], "$options": "i"},
                    "mese": parsed_data.get('mese'),
                    "anno": parsed_data.get('anno')
                })
                
                if not existing:
                    # Crea nuovo record
                    salario_doc = {
                        "id": str(uuid.uuid4()),
                        "dipendente_id": dipendente_id,
                        "dipendente_nome": parsed_data['dipendente_nome'],
                        "codice_fiscale": parsed_data.get('codice_fiscale'),
                        "mese": parsed_data.get('mese'),
                        "anno": parsed_data.get('anno'),
                        "netto": parsed_data.get('netto', 0),
                        "lordo": parsed_data.get('lordo', 0),
                        "inps": parsed_data.get('inps', 0),
                        "irpef": parsed_data.get('irpef', 0),
                        "cedolino_id": cedolino["id"],
                        "source": "email_cedolino_auto",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db["prima_nota_salari"].insert_one(salario_doc)
                    stats["created_prima_nota"] += 1
                    logger.info(f"Prima nota salari creata: {parsed_data['dipendente_nome']} {parsed_data.get('mese')}/{parsed_data.get('anno')} - €{parsed_data.get('netto')}")
            
            # Aggiorna cedolino come processato
            await db["cedolini_email_attachments"].update_one(
                {"id": cedolino["id"]},
                {"$set": {
                    "processed": True,
                    "parsed_data": parsed_data,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            stats["processed"] += 1
            
        except Exception as e:
            logger.error(f"Errore processing cedolino {cedolino.get('filename')}: {e}")
            stats["errors"].append(f"{cedolino.get('filename')}: {str(e)}")
    
    return stats
