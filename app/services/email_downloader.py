"""
Sistema Download Email con Allegati PDF
Scarica automaticamente allegati PDF dalla casella email Gmail
e li processa in base al mittente (commercialista vs consulente lavoro)
"""
import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import logging
import uuid
import asyncio

logger = logging.getLogger(__name__)

# Configurazione
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
DOWNLOAD_DIR = "/app/uploads/email_attachments"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Mittenti conosciuti
MITTENTI_CONFIG = {
    "rosaria.marotta@email.it": {
        "tipo": "commercialista",
        "nome": "Rosaria Marotta",
        "categoria_f24": "fiscale",
        "descrizione": "F24 fiscali - IRPEF, IVA, IRAP"
    },
    "grazia.studioferrantini@email.it": {
        "tipo": "consulente_lavoro", 
        "nome": "Grazia Ferrantini",
        "categoria_f24": "contributivo",
        "descrizione": "F24 contributivi - INPS, INAIL"
    },
    "f.ferrantini@email.it": {
        "tipo": "consulente_lavoro",
        "nome": "F. Ferrantini",
        "categoria_f24": "contributivo",
        "descrizione": "F24 contributivi - INPS, INAIL"
    }
}


class EmailDownloader:
    """Classe per gestire il download delle email con allegati."""
    
    def __init__(self, email_address: str, password: str):
        self.email_address = email_address
        self.password = password
        self.connection = None
    
    def connect(self) -> bool:
        """Connessione al server IMAP."""
        try:
            self.connection = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            self.connection.login(self.email_address, self.password)
            logger.info(f"Connesso a {IMAP_SERVER} come {self.email_address}")
            return True
        except Exception as e:
            logger.error(f"Errore connessione IMAP: {e}")
            return False
    
    def disconnect(self):
        """Disconnessione dal server."""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
    
    def decode_header_value(self, value: str) -> str:
        """Decodifica header email."""
        if not value:
            return ""
        decoded_parts = decode_header(value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or 'utf-8', errors='replace')
            else:
                result += part
        return result
    
    def get_mittente_config(self, email_from: str) -> Optional[Dict]:
        """Trova la configurazione del mittente."""
        email_from = email_from.lower()
        for mittente, config in MITTENTI_CONFIG.items():
            if mittente.lower() in email_from:
                return config
        return None
    
    def search_emails(
        self, 
        folder: str = "INBOX",
        from_addresses: List[str] = None,
        since_days: int = 30,
        unseen_only: bool = False
    ) -> List[str]:
        """
        Cerca email nella cartella specificata.
        
        Args:
            folder: Cartella email (INBOX, etc.)
            from_addresses: Lista indirizzi mittente da cercare
            since_days: Cerca email degli ultimi N giorni
            unseen_only: Solo email non lette
        
        Returns:
            Lista di ID email trovate
        """
        try:
            self.connection.select(folder)
            
            # Costruisci criteri di ricerca
            criteria = []
            
            # Filtro data
            since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            criteria.append(f'SINCE {since_date}')
            
            # Filtro non lette
            if unseen_only:
                criteria.append('UNSEEN')
            
            # Se ci sono mittenti specifici, cerca per ognuno
            all_email_ids = []
            
            if from_addresses:
                for from_addr in from_addresses:
                    search_criteria = f'({" ".join(criteria)} FROM "{from_addr}")'
                    status, messages = self.connection.search(None, search_criteria)
                    if status == 'OK' and messages[0]:
                        all_email_ids.extend(messages[0].split())
            else:
                search_criteria = f'({" ".join(criteria)})'
                status, messages = self.connection.search(None, search_criteria)
                if status == 'OK' and messages[0]:
                    all_email_ids = messages[0].split()
            
            # Rimuovi duplicati
            all_email_ids = list(set(all_email_ids))
            
            logger.info(f"Trovate {len(all_email_ids)} email in {folder}")
            return all_email_ids
            
        except Exception as e:
            logger.error(f"Errore ricerca email: {e}")
            return []
    
    def download_attachments(
        self, 
        email_id: bytes,
        extensions: List[str] = ['.pdf']
    ) -> List[Dict[str, Any]]:
        """
        Scarica gli allegati di una email.
        
        Args:
            email_id: ID della email
            extensions: Estensioni file da scaricare
        
        Returns:
            Lista di allegati scaricati con info
        """
        attachments = []
        
        try:
            status, msg_data = self.connection.fetch(email_id, '(RFC822)')
            if status != 'OK':
                return attachments
            
            email_message = email.message_from_bytes(msg_data[0][1])
            
            # Info email
            subject = self.decode_header_value(email_message.get('Subject', ''))
            from_addr = self.decode_header_value(email_message.get('From', ''))
            date_str = email_message.get('Date', '')
            
            # Trova configurazione mittente
            mittente_config = self.get_mittente_config(from_addr)
            
            # Estrai email effettiva dal campo From
            import re
            email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_addr)
            from_email = email_match.group(0) if email_match else from_addr
            
            # Processa parti del messaggio
            for part in email_message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                
                filename = part.get_filename()
                if not filename:
                    continue
                
                filename = self.decode_header_value(filename)
                
                # Verifica estensione
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in extensions:
                    continue
                
                # Scarica allegato
                file_content = part.get_payload(decode=True)
                if not file_content:
                    continue
                
                # Genera nome file univoco
                file_id = str(uuid.uuid4())
                safe_filename = f"{file_id}_{filename}"
                file_path = os.path.join(DOWNLOAD_DIR, safe_filename)
                
                # Salva file
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                
                attachment_info = {
                    "id": file_id,
                    "original_filename": filename,
                    "saved_filename": safe_filename,
                    "file_path": file_path,
                    "file_size": len(file_content),
                    "extension": file_ext,
                    "email_subject": subject,
                    "email_from": from_email,
                    "email_date": date_str,
                    "mittente_tipo": mittente_config.get("tipo") if mittente_config else "sconosciuto",
                    "mittente_nome": mittente_config.get("nome") if mittente_config else from_addr,
                    "categoria_f24": mittente_config.get("categoria_f24") if mittente_config else "generico",
                    "downloaded_at": datetime.now(timezone.utc).isoformat()
                }
                
                attachments.append(attachment_info)
                logger.info(f"Scaricato: {filename} da {from_email}")
            
            return attachments
            
        except Exception as e:
            logger.error(f"Errore download allegati: {e}")
            return attachments
    
    def download_all_from_senders(
        self,
        since_days: int = 30,
        unseen_only: bool = False
    ) -> Dict[str, Any]:
        """
        Scarica tutti gli allegati PDF dai mittenti configurati.
        
        Returns:
            Risultato del download con statistiche
        """
        result = {
            "success": True,
            "totale_email": 0,
            "totale_allegati": 0,
            "allegati_fiscali": 0,
            "allegati_contributivi": 0,
            "allegati": [],
            "errori": []
        }
        
        if not self.connect():
            result["success"] = False
            result["errori"].append("Impossibile connettersi al server email")
            return result
        
        try:
            # Lista mittenti conosciuti
            mittenti = list(MITTENTI_CONFIG.keys())
            
            # Cerca email
            email_ids = self.search_emails(
                from_addresses=mittenti,
                since_days=since_days,
                unseen_only=unseen_only
            )
            
            result["totale_email"] = len(email_ids)
            
            # Scarica allegati
            for email_id in email_ids:
                attachments = self.download_attachments(email_id)
                
                for att in attachments:
                    result["allegati"].append(att)
                    result["totale_allegati"] += 1
                    
                    if att.get("categoria_f24") == "fiscale":
                        result["allegati_fiscali"] += 1
                    elif att.get("categoria_f24") == "contributivo":
                        result["allegati_contributivi"] += 1
            
        except Exception as e:
            result["success"] = False
            result["errori"].append(str(e))
        finally:
            self.disconnect()
        
        return result


async def download_and_process_emails(
    email_address: str,
    password: str,
    since_days: int = 30
) -> Dict[str, Any]:
    """
    Funzione asincrona per scaricare e processare email.
    Da chiamare dal router FastAPI.
    """
    downloader = EmailDownloader(email_address, password)
    
    # Esegui in thread separato per non bloccare
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: downloader.download_all_from_senders(since_days=since_days)
    )
    
    return result


def get_mittenti_configurati() -> Dict[str, Any]:
    """Restituisce la lista dei mittenti configurati."""
    return MITTENTI_CONFIG
