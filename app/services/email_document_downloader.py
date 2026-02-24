"""
Servizio Download Documenti da Email
Scarica automaticamente allegati dalle email e li salva su MongoDB Atlas.
IMPORTANTE: Tutto va salvato su MongoDB, NIENTE filesystem!
Supporta: F24, Fatture, Buste Paga, Estratti Conto, Quietanze
"""

import imaplib
import email
from email.header import decode_header
import os
import re
import uuid
import base64
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import logging
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)

# Directory per salvare i documenti scaricati
DOCUMENTS_DIR = Path("/app/documents")
DOCUMENTS_DIR.mkdir(exist_ok=True)

# Sottocartelle per categoria
CATEGORIES = {
    "f24": "F24",
    "fattura": "Fatture",
    "busta_paga": "Buste Paga", 
    "estratto_conto": "Estratti Conto",
    "quietanza": "Quietanze",
    "bonifico": "Bonifici",
    "cartella_esattoriale": "Cartelle Esattoriali",
    "scheda_tecnica": "Schede Tecniche",
    "altro": "Altri"
}

# Mapping parole chiave -> categoria
KEYWORD_CATEGORY_MAP = {
    "f24": "f24",
    "fattura": "fattura",
    "busta paga": "busta_paga",
    "cedolino": "busta_paga",
    "estratto conto": "estratto_conto",
    "quietanza": "quietanza",
    "bonifico": "bonifico",
    "cartella esattoriale": "cartella_esattoriale",
    "cartella esattoria": "cartella_esattoriale",
    "agenzia entrate riscossione": "cartella_esattoriale",
    "equitalia": "cartella_esattoriale",
    # Schede Tecniche
    "scheda tecnica": "scheda_tecnica",
    "technical sheet": "scheda_tecnica",
    "data sheet": "scheda_tecnica",
    "product specification": "scheda_tecnica",
    "specifica prodotto": "scheda_tecnica",
    "scheda prodotto": "scheda_tecnica",
    "informazioni tecniche": "scheda_tecnica",
    "technical data": "scheda_tecnica"
}

for cat_dir in CATEGORIES.values():
    (DOCUMENTS_DIR / cat_dir).mkdir(exist_ok=True)


def get_category_from_keyword(keyword: str) -> str:
    """Trova la categoria corrispondente a una parola chiave."""
    keyword_lower = keyword.lower().strip()
    for kw, cat in KEYWORD_CATEGORY_MAP.items():
        if kw in keyword_lower or keyword_lower in kw:
            return cat
    return "altro"


def ensure_category_folder(category: str) -> Path:
    """Crea la cartella per una categoria se non esiste."""
    folder_name = CATEGORIES.get(category, category.replace("_", " ").title())
    folder_path = DOCUMENTS_DIR / folder_name
    folder_path.mkdir(exist_ok=True)
    return folder_path


def decode_mime_header(header_value: str) -> str:
    """Decodifica header MIME."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def categorize_document(filename: str, subject: str = "", sender: str = "", search_keywords: List[str] = None) -> str:
    """
    Categorizza un documento in base al nome file, oggetto, mittente e parole chiave di ricerca.
    Ora supporta tutte le categorie, non solo F24.
    """
    filename_lower = filename.lower()
    subject_lower = subject.lower()
    sender_lower = sender.lower()
    
    # Se ci sono parole chiave specifiche dalla ricerca, usa quelle per determinare la categoria
    if search_keywords:
        for kw in search_keywords:
            kw_lower = kw.lower()
            if kw_lower in subject_lower or kw_lower in filename_lower:
                return get_category_from_keyword(kw)
    
    # Cartelle Esattoriali
    cartella_patterns = ['cartella esattoriale', 'cartella esattoria', 'agenzia entrate riscossione', 
                         'equitalia', 'ader', 'intimazione', 'ingiunzione']
    if any(x in subject_lower or x in filename_lower for x in cartella_patterns):
        return "cartella_esattoriale"
    
    # F24 - Pattern nell'oggetto o nel nome file
    f24_patterns = ['f24', 'f-24', 'f_24', 'mod.f24', 'modello f24', 'tribut']
    if any(x in subject_lower or x in filename_lower for x in f24_patterns):
        return "f24"
    
    # Quietanze F24
    if any(x in filename_lower or x in subject_lower for x in ['quietanza', 'ricevuta f24', 'pagamento f24']):
        return "quietanza"
    
    # Fatture
    fattura_patterns = ['fattura', 'invoice', 'fatt.', 'ft.']
    if any(x in subject_lower or x in filename_lower for x in fattura_patterns):
        return "fattura"
    
    # Buste paga
    busta_patterns = ['busta paga', 'cedolino', 'lul', 'libro unico']
    if any(x in subject_lower or x in filename_lower for x in busta_patterns):
        return "busta_paga"
    
    # Estratti conto
    estratto_patterns = ['estratto conto', 'movimenti', 'saldo']
    if any(x in subject_lower or x in filename_lower for x in estratto_patterns):
        return "estratto_conto"
    
    # Bonifici
    bonifico_patterns = ['bonifico', 'sepa', 'disposizione']
    if any(x in subject_lower or x in filename_lower for x in bonifico_patterns):
        return "bonifico"
    
    # Default: altro (accetta comunque il documento)
    return "altro"


def calculate_file_hash(content: bytes) -> str:
    """Calcola hash MD5 per evitare duplicati."""
    return hashlib.md5(content).hexdigest()


def extract_document_period(content: bytes, category: str, filename: str) -> Optional[Dict[str, Any]]:
    """
    Estrae il periodo di riferimento da un documento PDF.
    Questo permette di identificare documenti con stesso nome ma periodi diversi.
    
    Returns:
        Dict con mese, anno e identificatore univoco del periodo
        None se non riesce a estrarre
    """
    import re
    
    period_info = {
        "mese": None,
        "anno": None,
        "periodo_raw": None,
        "identificatore_periodo": None
    }
    
    try:
        # Prova a estrarre testo dal PDF
        import pdfplumber
        import io
        
        text = ""
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages[:3]:  # Solo prime 3 pagine per velocità
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        
        text_lower = text.lower()
        
        # Dizionari comuni per i mesi
        mesi_it = {
            'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
            'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
            'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
        }
        mesi_short = {
            'gen': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'mag': 5, 'giu': 6,
            'lug': 7, 'ago': 8, 'set': 9, 'ott': 10, 'nov': 11, 'dic': 12
        }
        
        # Pattern comuni per periodi
        # Formato: "GENNAIO 2026", "01/2026", "2026-01", "Mese: 01 Anno: 2026"
        
        # Pattern 1: "GENNAIO 2026" o "gennaio 2026"
        for mese_nome, mese_num in mesi_it.items():
            pattern = rf'{mese_nome}\s+(\d{{4}})'
            match = re.search(pattern, text_lower)
            if match:
                period_info["mese"] = mese_num
                period_info["anno"] = int(match.group(1))
                period_info["periodo_raw"] = f"{mese_nome} {match.group(1)}"
                break
        
        # Pattern 2: "01/2026" o "1/2026" (mese/anno)
        if not period_info["mese"]:
            match = re.search(r'\b(\d{1,2})/(\d{4})\b', text)
            if match:
                mese = int(match.group(1))
                anno = int(match.group(2))
                if 1 <= mese <= 12 and 2020 <= anno <= 2030:
                    period_info["mese"] = mese
                    period_info["anno"] = anno
                    period_info["periodo_raw"] = f"{mese:02d}/{anno}"
        
        # Pattern 3: Per F24 cerca "Scadenza DD/MM/YYYY"
        if category == "f24" and not period_info["mese"]:
            match = re.search(r'scadenza\s+(\d{2})/(\d{2})/(\d{4})', text_lower)
            if match:
                period_info["mese"] = int(match.group(2))
                period_info["anno"] = int(match.group(3))
                period_info["periodo_raw"] = f"scadenza_{match.group(1)}/{match.group(2)}/{match.group(3)}"
        
        # Pattern 4: Per estratti conto cerca "DAL DD/MM/YYYY AL DD/MM/YYYY"
        if category == "estratto_conto" and not period_info["mese"]:
            match = re.search(r'dal\s+\d{2}/(\d{2})/(\d{4})\s+al\s+\d{2}/(\d{2})/(\d{4})', text_lower)
            if match:
                # Usa il mese finale come riferimento
                period_info["mese"] = int(match.group(3))
                period_info["anno"] = int(match.group(4))
                period_info["periodo_raw"] = f"{match.group(3)}/{match.group(4)}"
        
        # Pattern 5: Per Nexi cerca date nel formato "DD MMM YYYY"
        if not period_info["mese"]:
            for mese_short_key, mese_num in mesi_short.items():
                pattern = rf'\d{{2}}\s+{mese_short_key}\w*\s+(\d{{4}})'
                match = re.search(pattern, text_lower)
                if match:
                    period_info["mese"] = mese_num
                    period_info["anno"] = int(match.group(1))
                    period_info["periodo_raw"] = f"{mese_short_key}_{match.group(1)}"
                    break
        
        # Pattern 6: Per IVA cerca "LIQUIDAZIONE IVA MESE/TRIMESTRE"
        if not period_info["mese"]:
            # IVA mensile: "liquidazione iva gennaio", "iva mese di febbraio"
            iva_patterns = [
                r'(?:liquidazione\s+)?iva\s+(?:mese\s+(?:di\s+)?)?(\w+)\s+(\d{4})',
                r'versamento\s+iva\s+(\w+)\s+(\d{4})',
                r'iva\s+(\w+)\s+(\d{4})',
            ]
            for pattern in iva_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    mese_str = match.group(1)
                    anno_str = match.group(2)
                    if mese_str in mesi_it:
                        period_info["mese"] = mesi_it[mese_str]
                        period_info["anno"] = int(anno_str)
                        period_info["periodo_raw"] = f"iva_{mese_str}_{anno_str}"
                        break
            
            # IVA trimestrale: "1° trimestre", "I trimestre", "primo trimestre"
            if not period_info["mese"]:
                trimestre_map = {
                    '1': 3, 'i': 3, 'primo': 3, '1°': 3,
                    '2': 6, 'ii': 6, 'secondo': 6, '2°': 6,
                    '3': 9, 'iii': 9, 'terzo': 9, '3°': 9,
                    '4': 12, 'iv': 12, 'quarto': 12, '4°': 12,
                }
                match = re.search(r'(\d|i{1,3}v?|primo|secondo|terzo|quarto|\d°)\s*trimestre\s*(\d{4})?', text_lower)
                if match:
                    trim_key = match.group(1).strip()
                    if trim_key in trimestre_map:
                        period_info["mese"] = trimestre_map[trim_key]
                        if match.group(2):
                            period_info["anno"] = int(match.group(2))
                        period_info["periodo_raw"] = f"trim_{trim_key}"
        
        # Pattern 7: Per bonifici cerca "DATA ESECUZIONE/VALUTA DD/MM/YYYY"
        if not period_info["mese"]:
            bonifico_patterns = [
                r'data\s+(?:esecuzione|valuta|operazione)\s*:?\s*(\d{2})/(\d{2})/(\d{4})',
                r'(?:eseguito|disposto)\s+(?:il|in data)\s+(\d{2})/(\d{2})/(\d{4})',
                r'bonifico\s+.*?(\d{2})/(\d{2})/(\d{4})',
            ]
            for pattern in bonifico_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    period_info["mese"] = int(match.group(2))
                    period_info["anno"] = int(match.group(3))
                    period_info["periodo_raw"] = f"bonifico_{match.group(1)}/{match.group(2)}/{match.group(3)}"
                    break
        
        # Pattern 8: Data generica DD/MM/YYYY (ultima risorsa per qualsiasi documento)
        if not period_info["mese"]:
            # Cerca tutte le date nel documento e usa la più recente
            date_matches = re.findall(r'(\d{2})/(\d{2})/(\d{4})', text)
            if date_matches:
                # Prendi la prima data trovata (solitamente è la più rilevante)
                for day, month, year in date_matches:
                    m = int(month)
                    y = int(year)
                    if 1 <= m <= 12 and 2020 <= y <= 2030:
                        period_info["mese"] = m
                        period_info["anno"] = y
                        period_info["periodo_raw"] = f"data_{day}/{month}/{year}"
                        break
        
        # Pattern 9: Cerca anno nel filename se non trovato
        if not period_info["anno"]:
            match = re.search(r'20(\d{2})', filename)
            if match:
                period_info["anno"] = int(f"20{match.group(1)}")
        
        # Crea identificatore univoco del periodo
        if period_info["mese"] and period_info["anno"]:
            period_info["identificatore_periodo"] = f"{period_info['anno']:04d}_{period_info['mese']:02d}"
        elif period_info["anno"]:
            period_info["identificatore_periodo"] = f"{period_info['anno']:04d}_00"
        
    except Exception as e:
        logger.debug(f"Impossibile estrarre periodo da {filename}: {e}")
    
    return period_info if period_info["identificatore_periodo"] else None


class EmailDocumentDownloader:
    """Classe per scaricare documenti dalle email via IMAP."""
    
    def __init__(self, email_user: str, email_password: str, imap_server: str = "imap.gmail.com"):
        self.email_user = email_user
        self.email_password = email_password
        self.imap_server = imap_server
        self.connection = None
        
    def connect(self) -> bool:
        """Connette al server IMAP."""
        try:
            self.connection = imaplib.IMAP4_SSL(self.imap_server)
            self.connection.login(self.email_user, self.email_password)
            logger.info(f"Connesso a {self.imap_server} come {self.email_user}")
            return True
        except Exception as e:
            logger.error(f"Errore connessione IMAP: {e}")
            return False
    
    def disconnect(self):
        """Disconnette dal server IMAP."""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None
    
    def search_emails_with_attachments(
        self, 
        folder: str = "INBOX",
        since_date: Optional[str] = None,
        search_criteria: Optional[str] = None,
        search_keywords: Optional[List[str]] = None,
        limit: int = 200
    ) -> List[bytes]:
        """
        Cerca email con allegati.
        since_date: formato "01-Jan-2025"
        search_keywords: lista di parole chiave da cercare nell'oggetto
        """
        if not self.connection:
            return []
        
        try:
            self.connection.select(folder)
            
            # Costruisci criteri di ricerca
            criteria = []
            if since_date:
                criteria.append(f'SINCE {since_date}')
            if search_criteria:
                criteria.append(search_criteria)
            
            # Se ci sono parole chiave, costruisci il filtro OR
            if search_keywords and len(search_keywords) > 0:
                # Costruisci OR per ogni parola chiave
                keyword_criteria = []
                for kw in search_keywords:
                    keyword_criteria.append(f'(SUBJECT "{kw}")')
                
                if len(keyword_criteria) == 1:
                    criteria.append(keyword_criteria[0])
                else:
                    # Costruisci OR ricorsivo: (OR (a) (OR (b) (c)))
                    or_expr = keyword_criteria[-1]
                    for i in range(len(keyword_criteria) - 2, -1, -1):
                        or_expr = f'(OR {keyword_criteria[i]} {or_expr})'
                    criteria.append(or_expr)
            
            search_string = ' '.join(criteria) if criteria else 'ALL'
            logger.info(f"Ricerca email con criteri: {search_string}")
            
            status, messages = self.connection.search(None, search_string)
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            
            # Limita e prendi i più recenti
            if len(email_ids) > limit:
                email_ids = email_ids[-limit:]
            
            logger.info(f"Trovate {len(email_ids)} email")
            return email_ids
            
        except Exception as e:
            logger.error(f"Errore ricerca email: {e}")
            return []
    
    def download_attachments_from_email(
        self, 
        email_id: bytes,
        allowed_extensions: List[str] = ['.pdf', '.xml', '.xlsx', '.xls', '.csv', '.p7m'],
        search_keywords: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Scarica allegati da una singola email.
        Ritorna lista di documenti scaricati.
        """
        if not self.connection:
            return []
        
        documents = []
        
        try:
            status, msg_data = self.connection.fetch(email_id, '(RFC822)')
            
            if status != 'OK':
                return []
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Estrai metadati email
                    subject = decode_mime_header(msg.get('Subject', ''))
                    sender = decode_mime_header(msg.get('From', ''))
                    date_str = msg.get('Date', '')
                    message_id = msg.get('Message-ID', str(uuid.uuid4()))
                    
                    # Parse data
                    try:
                        email_date = email.utils.parsedate_to_datetime(date_str)
                    except:
                        email_date = datetime.now(timezone.utc)
                    
                    # Cerca allegati
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        
                        filename = part.get_filename()
                        if not filename:
                            continue
                        
                        filename = decode_mime_header(filename)
                        
                        # Controlla estensione
                        ext = os.path.splitext(filename)[1].lower()
                        if ext not in allowed_extensions:
                            continue
                        
                        # Scarica contenuto
                        content = part.get_payload(decode=True)
                        if not content:
                            continue
                        
                        # Calcola hash per evitare duplicati
                        file_hash = calculate_file_hash(content)
                        
                        # Categorizza documento
                        category = categorize_document(filename, subject, sender, search_keywords)
                        
                        # Se non riesce a categorizzare, usa "altro"
                        if category is None:
                            category = "altro"
                        
                        # NUOVO: Estrai periodo dal documento per identificazione intelligente
                        # Applica a TUTTI i PDF, non solo categorie specifiche
                        period_info = None
                        if ext == '.pdf':
                            try:
                                period_info = extract_document_period(content, category, filename)
                                if period_info:
                                    logger.info(f"📅 Periodo estratto da {filename}: {period_info.get('periodo_raw', 'N/D')} (cat: {category})")
                            except Exception as e:
                                logger.debug(f"Errore estrazione periodo: {e}")
                        
                        # Assicurati che la cartella esista
                        ensure_category_folder(category)
                        
                        # Genera nome file univoco
                        timestamp = email_date.strftime('%Y%m%d_%H%M%S')
                        safe_filename = re.sub(r'[^\w\-_\.]', '_', filename)
                        unique_filename = f"{timestamp}_{safe_filename}"
                        
                        # IMPORTANTE: Salva contenuto PDF come base64 in MongoDB
                        # NO FILESYSTEM - TUTTO SU MONGODB ATLAS
                        pdf_base64 = base64.b64encode(content).decode('utf-8')
                        
                        documents.append({
                            "id": str(uuid.uuid4()),
                            "filename": filename,
                            "filename_saved": unique_filename,
                            "pdf_data": pdf_base64,  # Contenuto PDF in MongoDB!
                            "category": category,
                            "category_label": CATEGORIES.get(category, category.replace("_", " ").title()),
                            "size_bytes": len(content),
                            "file_hash": file_hash,
                            # NUOVO: Informazioni sul periodo per identificazione intelligente
                            "periodo_mese": period_info.get("mese") if period_info else None,
                            "periodo_anno": period_info.get("anno") if period_info else None,
                            "periodo_raw": period_info.get("periodo_raw") if period_info else None,
                            "identificatore_periodo": period_info.get("identificatore_periodo") if period_info else None,
                            "email_subject": subject[:200],
                            "email_from": sender[:200],
                            "email_date": email_date.isoformat(),
                            "email_message_id": message_id,
                            "downloaded_at": datetime.now(timezone.utc).isoformat(),
                            "status": "nuovo",  # nuovo, processato, errore
                            "processed": False,
                            "processed_to": None  # dove è stato caricato
                        })
                        
                        logger.info(f"Salvato su MongoDB: {filename} -> {category}")
            
        except Exception as e:
            logger.error(f"Errore download allegati: {e}")
        
        return documents
    
    def download_all_attachments(
        self,
        folder: str = "INBOX",
        since_date: Optional[str] = None,
        limit: int = 200,
        search_keywords: List[str] = None
    ) -> Tuple[List[Dict], Dict[str, int]]:
        """
        Scarica tutti gli allegati dalle email.
        Ritorna (lista documenti, statistiche).
        
        Args:
            search_keywords: Lista di parole chiave per filtrare le email
        """
        all_documents = []
        stats = {
            "emails_checked": 0,
            "documents_found": 0,
            "by_category": {}
        }
        
        email_ids = self.search_emails_with_attachments(
            folder, 
            since_date, 
            limit=limit,
            search_keywords=search_keywords
        )
        stats["emails_checked"] = len(email_ids)
        
        for email_id in email_ids:
            docs = self.download_attachments_from_email(email_id, search_keywords=search_keywords)
            all_documents.extend(docs)
            
            for doc in docs:
                cat = doc["category"]
                stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        
        stats["documents_found"] = len(all_documents)
        
        return all_documents, stats


async def download_documents_from_email(
    db,
    email_user: str,
    email_password: str,
    since_days: int = 30,
    folder: str = "INBOX",
    max_emails: int = 200,
    search_keywords: List[str] = None
) -> Dict[str, Any]:
    """
    Funzione principale per scaricare documenti da email.
    Salva i metadati nel database.
    
    Args:
        search_keywords: Lista di parole chiave da cercare nell'oggetto email.
                        Se None, scarica tutti i documenti senza filtro.
    """
    from datetime import timedelta
    
    # Calcola data "since"
    since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    
    downloader = EmailDocumentDownloader(email_user, email_password)
    
    if not downloader.connect():
        return {
            "success": False,
            "error": "Impossibile connettersi al server email",
            "documents": [],
            "stats": {}
        }
    
    try:
        documents, stats = downloader.download_all_attachments(
            folder=folder,
            since_date=since_date,
            limit=max_emails,
            search_keywords=search_keywords
        )
        
        # Salva nel database evitando duplicati con logica intelligente
        new_documents = []
        duplicates = 0
        period_duplicates = 0
        
        for doc in documents:
            is_duplicate = False
            duplicate_reason = None
            
            # METODO 1: Controllo hash (file identico byte per byte)
            existing_hash = await db["documents_inbox"].find_one({"file_hash": doc["file_hash"]})
            if existing_hash:
                is_duplicate = True
                duplicate_reason = "hash_identico"
            
            # METODO 2: Controllo periodo (stesso documento per stesso periodo)
            # Questo è il caso: "estratto_conto.pdf" di gennaio vs "estratto_conto.pdf" di febbraio
            # Stesso nome file ma periodi diversi → NON è un duplicato
            # Stesso nome file E stesso periodo → È un duplicato
            if not is_duplicate and doc.get("identificatore_periodo"):
                existing_period = await db["documents_inbox"].find_one({
                    "category": doc["category"],
                    "identificatore_periodo": doc["identificatore_periodo"],
                    # Escludi documenti con hash diverso (potrebbero essere versioni corrette)
                    # Ma includi se il filename originale è simile
                    "$or": [
                        {"filename": doc["filename"]},
                        {"filename": {"$regex": doc["filename"].replace(".pdf", "").replace(".PDF", ""), "$options": "i"}}
                    ]
                })
                if existing_period:
                    # Verifica che non sia un aggiornamento/correzione (dimensione molto diversa)
                    size_diff = abs(existing_period.get("size_bytes", 0) - doc["size_bytes"])
                    size_ratio = size_diff / max(existing_period.get("size_bytes", 1), doc["size_bytes"])
                    
                    if size_ratio < 0.1:  # Differenza < 10% = probabilmente stesso documento
                        is_duplicate = True
                        duplicate_reason = "stesso_periodo"
                        period_duplicates += 1
                        logger.info(f"⏭️ Documento {doc['filename']} periodo {doc['identificatore_periodo']} già presente, saltato")
                    else:
                        # Dimensione molto diversa = probabilmente versione aggiornata, accetta
                        logger.info(f"📝 Documento {doc['filename']} periodo {doc['identificatore_periodo']} aggiornato (size diff: {size_ratio:.0%})")
            
            if is_duplicate:
                duplicates += 1
                continue
            
            # Crea copia per database (evita che insert_one modifichi l'originale con _id)
            doc_to_insert = dict(doc)
            await db["documents_inbox"].insert_one(doc_to_insert.copy())
            
            # Log dettagliato per documenti nuovi
            if doc.get("identificatore_periodo"):
                logger.info(f"✅ Nuovo documento: {doc['filename']} - Periodo: {doc.get('periodo_raw', 'N/D')} - Categoria: {doc['category']}")
            else:
                logger.info(f"✅ Nuovo documento: {doc['filename']} - Categoria: {doc['category']} (periodo non estratto)")
            
            # Appendi documento senza _id per risposta JSON
            new_documents.append(doc)
        
        stats["new_documents"] = len(new_documents)
        stats["duplicates_skipped"] = duplicates
        stats["period_duplicates"] = period_duplicates
        stats["search_keywords"] = search_keywords
        
        # === PARSING AUTOMATICO CON AI ===
        # Processa automaticamente i nuovi documenti con il parser AI
        ai_parsed = 0
        ai_errors = 0
        
        try:
            from app.services.ai_integration_service import process_document_with_ai
            import base64
            
            for doc in new_documents:
                try:
                    # Determina tipo documento dalla categoria email
                    category = doc.get("category", "altro")
                    doc_type = "auto"
                    if category == "fattura":
                        doc_type = "fattura"
                    elif category == "f24" or category == "quietanza":
                        doc_type = "f24"
                    elif category == "busta_paga":
                        doc_type = "busta_paga"
                    
                    # Decodifica PDF
                    pdf_data = base64.b64decode(doc.get("pdf_data", ""))
                    
                    if pdf_data:
                        result = await process_document_with_ai(
                            db=db,
                            document_id=doc["id"],
                            pdf_data=pdf_data,
                            document_type=doc_type,
                            collection="documents_inbox"
                        )
                        
                        if result.get("success"):
                            ai_parsed += 1
                            logger.info(f"🧠 AI parsed: {doc['filename']} -> {result.get('detected_type')}")
                        else:
                            ai_errors += 1
                            
                except Exception as e:
                    ai_errors += 1
                    logger.warning(f"AI parsing error for {doc.get('filename')}: {e}")
                    
        except ImportError as e:
            logger.warning(f"AI parser non disponibile: {e}")
        
        stats["ai_parsed"] = ai_parsed
        stats["ai_errors"] = ai_errors
        
        return {
            "success": True,
            "documents": new_documents,
            "stats": stats
        }
        
    finally:
        downloader.disconnect()


def get_document_content(filepath: str) -> Optional[bytes]:
    """Legge il contenuto di un documento salvato."""
    try:
        with open(filepath, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Errore lettura file {filepath}: {e}")
        return None
