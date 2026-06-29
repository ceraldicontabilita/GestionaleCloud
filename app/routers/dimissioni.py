"""
Router Dimissioni Dipendenti
Cerca email "Notifica richiesta recesso rapporto di lavoro" e aggiorna anagrafica dipendenti
"""

import os
import re
import base64
import imaplib
import email
import logging
from email.header import decode_header
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Query

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurazione email
EMAIL = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")

COLLECTION_DIMISSIONI = "dimissioni"


def decode_email_subject(subject: str) -> str:
    """Decodifica il subject dell'email"""
    if not subject:
        return ""
    decoded_parts = decode_header(subject)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def estrai_dati_dimissioni(testo: str, allegati: List[str] = None) -> Dict[str, Any]:
    """
    Estrae i dati dalla notifica dimissioni.
    Cerca: nome dipendente, codice fiscale, data dimissioni, data decorrenza
    
    Pattern codice fiscale italiano:
    - 6 lettere (cognome + nome)
    - 2 cifre (anno nascita)
    - 1 lettera (mese nascita)
    - 2 cifre (giorno nascita + sesso)
    - 1 lettera (comune)
    - 3 cifre (codice comune)
    - 1 lettera (controllo)
    Esempio: CRLVLR88H14F839O
    """
    dati = {
        "dipendente_nome": None,
        "codice_fiscale": None,
        "data_dimissioni": None,
        "data_decorrenza": None,
        "motivo": None
    }
    
    # Pattern CF più robusto - cerca ovunque nel testo, anche senza word boundary
    cf_pattern = r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])'
    
    # Cerca codice fiscale nel testo (tutto maiuscolo)
    testo_upper = testo.upper()
    match = re.search(cf_pattern, testo_upper)
    if match:
        dati["codice_fiscale"] = match.group(1)
    
    # Se non trovato nel testo, cerca nei nomi degli allegati
    # I file spesso hanno nomi tipo: B00000xxx_CRLVLR88H14F839O_20241115.pdf
    if not dati["codice_fiscale"] and allegati:
        for allegato in allegati:
            allegato_upper = allegato.upper()
            # Cerca il CF anche tra underscore o altri separatori
            # Pattern: qualsiasi cosa + CF + qualsiasi cosa
            match = re.search(cf_pattern, allegato_upper)
            if match:
                # Verifica che sia un CF valido (non solo una sequenza casuale)
                cf_candidato = match.group(1)
                # Il CF deve avere la struttura corretta
                if is_valid_codice_fiscale_structure(cf_candidato):
                    dati["codice_fiscale"] = cf_candidato
                    break
    
    # Cerca data dimissioni
    # Pattern: "data dimissioni: 01/12/2024" o "dal 01/12/2024" o "decorrenza 01/12/2024"
    match = re.search(r'(?:data\s+dimission[ei]|dal|decorrenza|effetto\s+dal)[:\s]+(\d{2}/\d{2}/\d{4})', testo, re.I)
    if match:
        dati["data_dimissioni"] = match.group(1)
    
    # Cerca data nel formato YYYYMMDD nel filename allegato
    # Pattern: _20241115 o simile (anno + mese + giorno)
    if not dati["data_dimissioni"] and allegati:
        for allegato in allegati:
            # Cerca pattern YYYYMMDD (8 cifre che iniziano con 20)
            match = re.search(r'[_\-]?(20\d{6})', allegato)
            if match:
                data_str = match.group(1)
                try:
                    # Valida che sia una data reale
                    year = int(data_str[0:4])
                    month = int(data_str[4:6])
                    day = int(data_str[6:8])
                    if 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                        dati["data_dimissioni"] = f"{day:02d}/{month:02d}/{year}"
                        break
                except ValueError:
                    pass
    
    # Cerca data nel formato YYYYMMDD nel testo
    match = re.search(r'_(\d{8})\d*', testo)
    if match and not dati["data_dimissioni"]:
        data_str = match.group(1)
        try:
            year = int(data_str[0:4])
            month = int(data_str[4:6])
            day = int(data_str[6:8])
            if 2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                dati["data_dimissioni"] = f"{day:02d}/{month:02d}/{year}"
        except ValueError:
            pass
    
    # Cerca data nel formato ISO (YYYY-MM-DD)
    match = re.search(r'(\d{4}-\d{2}-\d{2})', testo)
    if match and not dati["data_dimissioni"]:
        data_iso = match.group(1)
        dati["data_dimissioni"] = f"{data_iso[8:10]}/{data_iso[5:7]}/{data_iso[0:4]}"
    
    return dati


def is_valid_codice_fiscale_structure(cf: str) -> bool:
    """
    Verifica che la struttura del codice fiscale sia valida.
    Non verifica il carattere di controllo, solo la struttura base.
    """
    if len(cf) != 16:
        return False
    
    # Primi 6 caratteri: lettere (cognome + nome)
    if not cf[0:6].isalpha():
        return False
    
    # Caratteri 7-8: cifre (anno)
    if not cf[6:8].isdigit():
        return False
    
    # Carattere 9: lettera (mese)
    if not cf[8].isalpha():
        return False
    
    # Caratteri 10-11: cifre (giorno)
    if not cf[9:11].isdigit():
        return False
    
    # Carattere 12: lettera (comune)
    if not cf[11].isalpha():
        return False
    
    # Caratteri 13-15: cifre (codice comune)
    if not cf[12:15].isdigit():
        return False
    
    # Carattere 16: lettera (controllo)
    if not cf[15].isalpha():
        return False
    
    return True


def normalizza_nome(nome: str) -> str:
    """Normalizza il nome per il confronto."""
    if not nome:
        return ""
    return " ".join(nome.upper().split())


@router.post("/cerca-email-dimissioni")
@handle_errors
async def cerca_email_dimissioni(
    cartella: str = Query("INBOX", description="Cartella email da cercare")
) -> Dict[str, Any]:
    """
    Cerca email di notifica dimissioni.
    Pattern: "Notifica richiesta recesso rapporto di lavoro"
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenziali email non configurate")
    
    db = Database.get_db()
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "email_trovate": 0,
        "dimissioni_estratte": [],
        "errori": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella)
        
        # Cerca email con pattern dimissioni
        search_criteria = '(OR SUBJECT "Notifica richiesta recesso" SUBJECT "dimissioni")'
        
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            mail.logout()
            return risultati
        
        message_ids = messages[0].split()
        risultati["email_trovate"] = len(message_ids)
        
        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                subject = decode_email_subject(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                
                # Estrai testo email
                email_text = subject
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                email_text += "\n" + payload.decode('utf-8', errors='replace')
                        except Exception as e:
                            logger.warning(f"Errore decodifica email: {e}")
                
                # PRIMA estrai i nomi degli allegati PDF
                allegati_nomi = []
                allegati_data = []
                for part in msg.walk():
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        filename = decode_email_subject(filename)
                        allegati_nomi.append(filename)
                        payload = part.get_payload(decode=True)
                        if payload:
                            allegati_data.append({
                                "filename": filename,
                                "size": len(payload),
                                "pdf_base64": base64.b64encode(payload).decode('utf-8')
                            })
                
                # POI estrai dati dimissioni passando anche i nomi degli allegati
                dati = estrai_dati_dimissioni(email_text, allegati_nomi)
                
                dimissione = {
                    "subject": subject,
                    "data_email": date_str,
                    "codice_fiscale": dati.get("codice_fiscale"),
                    "data_dimissioni": dati.get("data_dimissioni"),
                    "data_decorrenza": dati.get("data_decorrenza"),
                    "allegati": allegati_data
                }
                
                risultati["dimissioni_estratte"].append(dimissione)
                
                # Salva nel database
                doc = {
                    "tipo": "notifica_dimissioni",
                    "subject": subject,
                    "data_email": date_str,
                    "codice_fiscale": dati.get("codice_fiscale"),
                    "data_dimissioni": dati.get("data_dimissioni"),
                    "allegati_count": len(dimissione["allegati"]),
                    "data_inserimento": datetime.now(timezone.utc).isoformat() + "Z"
                }
                
                # Evita duplicati
                existing = await db[COLLECTION_DIMISSIONI].find_one({
                    "subject": subject,
                    "data_email": date_str
                })
                
                if not existing:
                    await db[COLLECTION_DIMISSIONI].insert_one(doc)
                
            except Exception as e:
                risultati["errori"].append(f"Errore parsing email: {str(e)}")
        
        mail.logout()
        
    except Exception as e:
        risultati["errori"].append(f"Errore connessione: {str(e)}")
    
    return risultati


@router.post("/associa-dimissioni-dipendenti")
@handle_errors
async def associa_dimissioni_dipendenti() -> Dict[str, Any]:
    """
    Associa le dimissioni trovate ai dipendenti e aggiorna la data_dimissione.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "dimissioni_analizzate": 0,
        "dipendenti_aggiornati": 0,
        "associazioni": [],
        "non_trovati": [],
        "errori": []
    }
    
    # Carica tutte le dimissioni
    dimissioni = await db[COLLECTION_DIMISSIONI].find({}).to_list(length=1000)
    risultati["dimissioni_analizzate"] = len(dimissioni)
    
    # Carica tutti i dipendenti
    dipendenti = await db["dipendenti"].find({}).to_list(length=1000)
    
    for dim in dimissioni:
        codice_fiscale = dim.get("codice_fiscale")
        data_dimissioni = dim.get("data_dimissioni")
        
        if not codice_fiscale or not data_dimissioni:
            continue
        
        # Cerca dipendente per codice fiscale
        dipendente = next(
            (d for d in dipendenti if d.get("codice_fiscale", "").upper() == codice_fiscale.upper()),
            None
        )
        
        if dipendente:
            # Converti data in formato ISO
            try:
                if "/" in data_dimissioni:
                    parts = data_dimissioni.split("/")
                    data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
                else:
                    data_iso = data_dimissioni
                
                # Aggiorna dipendente
                await db["dipendenti"].update_one(
                    {"_id": dipendente["_id"]},
                    {
                        "$set": {
                            "data_dimissione": data_iso,
                            "stato": "dimesso",
                            "data_modifica": datetime.now(timezone.utc).isoformat() + "Z"
                        }
                    }
                )
                
                risultati["dipendenti_aggiornati"] += 1
                risultati["associazioni"].append({
                    "codice_fiscale": codice_fiscale,
                    "dipendente": f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}",
                    "data_dimissione": data_iso
                })
            except Exception as e:
                risultati["errori"].append(f"Errore aggiornamento {codice_fiscale}: {str(e)}")
        else:
            risultati["non_trovati"].append(codice_fiscale)
    
    return risultati


@router.get("")
@handle_errors
async def get_dimissioni() -> List[Dict[str, Any]]:
    """Lista tutte le dimissioni trovate."""
    db = Database.get_db()
    
    cursor = db[COLLECTION_DIMISSIONI].find({})
    dimissioni = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        dimissioni.append(doc)
    
    return dimissioni


@router.get("/stats")
@handle_errors
async def get_stats_dimissioni() -> Dict[str, Any]:
    """Statistiche dimissioni."""
    db = Database.get_db()
    
    totale_dimissioni = await db[COLLECTION_DIMISSIONI].count_documents({})
    
    # Conta dipendenti dimessi
    dipendenti_dimessi = await db["dipendenti"].count_documents({"stato": "dimesso"})
    
    return {
        "notifiche_dimissioni": totale_dimissioni,
        "dipendenti_dimessi": dipendenti_dimessi
    }
