"""
Router ADR - Gestione Definizione Agevolata (Rottamazione)
Organizza cartelle per codice fiscale con elenco cartelle esattoriali
"""

import os
import re
import base64
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import Database

router = APIRouter()

# Configurazione
EMAIL = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")

COLLECTION_ADR = "adr_definizione_agevolata"


class CartellaPagamento(BaseModel):
    codice_cartella: str  # Es: 07120220089305113000
    importo_originale: Optional[float] = None
    importo_agevolato: Optional[float] = None
    data_notifica: Optional[str] = None
    ente_creditore: Optional[str] = None
    stato: str = "da_pagare"  # da_pagare, pagato, rateizzato
    note: Optional[str] = None


class SoggettoADR(BaseModel):
    codice_fiscale: str
    denominazione: str
    cartelle: List[CartellaPagamento] = []
    totale_originale: float = 0
    totale_agevolato: float = 0
    numero_rate: Optional[int] = None
    piano_rate: List[Dict[str, Any]] = []


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


def estrai_codice_cartella(testo: str) -> List[str]:
    """
    Estrae codici cartella dal testo.
    Pattern: 20 cifre (es: 07120220089305113000)
    """
    # Pattern cartella esattoriale: 20 cifre
    return re.findall(r'\b(\d{20})\b', testo)


def estrai_codice_fiscale(testo: str) -> Optional[str]:
    """Estrae codice fiscale o P.IVA dal testo."""
    # Codice fiscale persona fisica (16 caratteri alfanumerici)
    match = re.search(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', testo.upper())
    if match:
        return match.group(1)
    
    # P.IVA (11 cifre)
    match = re.search(r'\b(\d{11})\b', testo)
    if match:
        return match.group(1)
    
    return None


@router.get("/soggetti")
async def get_soggetti_adr() -> List[Dict[str, Any]]:
    """Lista tutti i soggetti con definizione agevolata."""
    db = Database.get_db()
    
    cursor = db[COLLECTION_ADR].find({}, {"pdf_allegati": 0})
    soggetti = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        soggetti.append(doc)
    
    return soggetti


@router.get("/soggetti/{codice_fiscale}")
async def get_soggetto_dettaglio(codice_fiscale: str) -> Dict[str, Any]:
    """Dettaglio soggetto con tutte le cartelle."""
    db = Database.get_db()
    
    soggetto = await db[COLLECTION_ADR].find_one({"codice_fiscale": codice_fiscale.upper()})
    
    if not soggetto:
        raise HTTPException(status_code=404, detail="Soggetto non trovato")
    
    soggetto["_id"] = str(soggetto["_id"])
    return soggetto


@router.post("/soggetti")
async def crea_soggetto_adr(soggetto: SoggettoADR) -> Dict[str, Any]:
    """Crea un nuovo soggetto con definizione agevolata."""
    db = Database.get_db()
    
    # Verifica se esiste già
    existing = await db[COLLECTION_ADR].find_one({"codice_fiscale": soggetto.codice_fiscale.upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Soggetto già esistente")
    
    doc = {
        "codice_fiscale": soggetto.codice_fiscale.upper(),
        "denominazione": soggetto.denominazione,
        "cartelle": [c.dict() for c in soggetto.cartelle],
        "totale_originale": soggetto.totale_originale,
        "totale_agevolato": soggetto.totale_agevolato,
        "numero_rate": soggetto.numero_rate,
        "piano_rate": soggetto.piano_rate,
        "pdf_allegati": [],
        "data_inserimento": datetime.now(timezone.utc).isoformat() + "Z",
        "data_modifica": datetime.now(timezone.utc).isoformat() + "Z"
    }
    
    result = await db[COLLECTION_ADR].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    
    return doc


@router.post("/soggetti/{codice_fiscale}/cartelle")
async def aggiungi_cartella(
    codice_fiscale: str,
    cartella: CartellaPagamento
) -> Dict[str, Any]:
    """Aggiunge una cartella a un soggetto."""
    db = Database.get_db()
    
    result = await db[COLLECTION_ADR].update_one(
        {"codice_fiscale": codice_fiscale.upper()},
        {
            "$push": {"cartelle": cartella.dict()},
            "$set": {"data_modifica": datetime.now(timezone.utc).isoformat() + "Z"}
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Soggetto non trovato")
    
    return {"success": True, "cartella_aggiunta": cartella.codice_cartella}


@router.post("/scarica-da-email")
async def scarica_adr_da_email(
    cartella_email: str = Query("INBOX", description="Cartella email da cercare")
) -> Dict[str, Any]:
    """
    Scarica documenti ADR/Definizione Agevolata dalla posta.
    Cerca: comunicazioni Agenzia Entrate Riscossione, rottamazione, definizione agevolata
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenziali email non configurate")
    
    db = Database.get_db()
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "email_trovate": 0,
        "documenti_salvati": 0,
        "cartelle_estratte": [],
        "soggetti_trovati": [],
        "errori": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella_email)
        
        # Cerca email relative a ADR/rottamazione
        keywords = [
            'Agenzia delle entrate-Riscossione',
            'definizione agevolata',
            'rottamazione',
            'AdER',
            'cartella di pagamento'
        ]
        
        all_message_ids = set()
        for kw in keywords:
            status, messages = mail.search(None, f'(OR SUBJECT "{kw}" BODY "{kw}")')
            if status == "OK" and messages[0]:
                all_message_ids.update(messages[0].split())
        
        risultati["email_trovate"] = len(all_message_ids)
        
        for msg_id in all_message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                subject = decode_email_subject(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                
                # Estrai testo email per parsing
                email_text = subject
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            email_text += "\n" + part.get_payload(decode=True).decode('utf-8', errors='replace')
                        except Exception as e:
                            logger.warning(f"Errore decodifica email part: {e}")
                
                # Estrai codici cartella e codice fiscale
                codici_cartella = estrai_codice_cartella(email_text)
                codice_fiscale = estrai_codice_fiscale(email_text)
                
                if codici_cartella:
                    risultati["cartelle_estratte"].extend(codici_cartella)
                
                if codice_fiscale and codice_fiscale not in risultati["soggetti_trovati"]:
                    risultati["soggetti_trovati"].append(codice_fiscale)
                
                # Salva allegati PDF
                for part in msg.walk():
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        filename = decode_email_subject(filename)
                        payload = part.get_payload(decode=True)
                        
                        if payload and codice_fiscale:
                            pdf_base64 = base64.b64encode(payload).decode('utf-8')
                            
                            # Aggiorna o crea soggetto
                            await db[COLLECTION_ADR].update_one(
                                {"codice_fiscale": codice_fiscale},
                                {
                                    "$setOnInsert": {
                                        "codice_fiscale": codice_fiscale,
                                        "denominazione": "",
                                        "cartelle": [],
                                        "totale_originale": 0,
                                        "totale_agevolato": 0,
                                        "piano_rate": [],
                                        "data_inserimento": datetime.now(timezone.utc).isoformat() + "Z"
                                    },
                                    "$push": {
                                        "pdf_allegati": {
                                            "filename": filename,
                                            "subject": subject,
                                            "data_email": date_str,
                                            "pdf_base64": pdf_base64,
                                            "cartelle_contenute": codici_cartella
                                        }
                                    },
                                    "$addToSet": {
                                        "cartelle": {
                                            "$each": [{"codice_cartella": c, "stato": "da_verificare"} for c in codici_cartella]
                                        }
                                    },
                                    "$set": {"data_modifica": datetime.now(timezone.utc).isoformat() + "Z"}
                                },
                                upsert=True
                            )
                            risultati["documenti_salvati"] += 1
                
            except Exception as e:
                risultati["errori"].append(str(e))
        
        mail.logout()
        
        # Deduplica
        risultati["cartelle_estratte"] = list(set(risultati["cartelle_estratte"]))
        
    except Exception as e:
        risultati["errori"].append(str(e))
    
    return risultati


@router.get("/stats")
async def get_stats_adr() -> Dict[str, Any]:
    """Statistiche ADR."""
    db = Database.get_db()
    
    totale_soggetti = await db[COLLECTION_ADR].count_documents({})
    
    # Conta cartelle totali
    pipeline = [
        {"$project": {"num_cartelle": {"$size": {"$ifNull": ["$cartelle", []]}}}},
        {"$group": {"_id": None, "totale": {"$sum": "$num_cartelle"}}}
    ]
    
    result = await db[COLLECTION_ADR].aggregate(pipeline).to_list(length=1)
    totale_cartelle = result[0]["totale"] if result else 0
    
    return {
        "soggetti": totale_soggetti,
        "cartelle_totali": totale_cartelle
    }


@router.post("/auto-ripara")
async def auto_ripara_adr() -> Dict[str, Any]:
    """
    Auto-riparazione dati ADR.
    - Verifica coerenza cartelle
    - Ricalcola totali
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "soggetti_verificati": 0,
        "problemi_trovati": 0,
        "correzioni": []
    }
    
    cursor = db[COLLECTION_ADR].find({})
    async for soggetto in cursor:
        risultati["soggetti_verificati"] += 1
        
        # Ricalcola totali
        totale_orig = 0
        totale_agev = 0
        
        for cartella in soggetto.get("cartelle", []):
            if cartella.get("importo_originale"):
                totale_orig += cartella["importo_originale"]
            if cartella.get("importo_agevolato"):
                totale_agev += cartella["importo_agevolato"]
        
        # Aggiorna se diverso
        if totale_orig != soggetto.get("totale_originale", 0) or totale_agev != soggetto.get("totale_agevolato", 0):
            await db[COLLECTION_ADR].update_one(
                {"_id": soggetto["_id"]},
                {"$set": {
                    "totale_originale": totale_orig,
                    "totale_agevolato": totale_agev,
                    "data_modifica": datetime.now(timezone.utc).isoformat() + "Z"
                }}
            )
            risultati["problemi_trovati"] += 1
            risultati["correzioni"].append(f"Ricalcolati totali per {soggetto.get('codice_fiscale')}")
    
    return risultati
