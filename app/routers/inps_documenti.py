"""
Router INPS Documenti - Gestione Delibere FONSI, Dilazioni, Cassa Integrazione
Scarica email PEC e associa documenti ai periodi/dipendenti
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

from app.database import Database

router = APIRouter()

# Configurazione email
EMAIL = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")

COLLECTION_FONSI = "delibere_fonsi"
COLLECTION_DILAZIONI = "dilazioni_inps"
COLLECTION_CASSA_INTEGRAZIONE = "cassa_integrazione"


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


def estrai_periodo_fonsi(testo: str) -> Optional[Dict[str, str]]:
    """
    Estrae il periodo dalla delibera FONSI.
    Pattern: "periodo dal 01/12/2021 al 31/12/2021"
    """
    match = re.search(r'periodo\s+dal\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})', testo, re.I)
    if match:
        return {
            "data_inizio": match.group(1),
            "data_fine": match.group(2)
        }
    return None


def estrai_dati_cassa_integrazione(testo: str) -> Dict[str, Any]:
    """
    Estrae i dati dalla delibera cassa integrazione.
    """
    dati = {
        "numero_lavoratori": None,
        "ore_totali": None,
        "importo": None,
        "periodo": None
    }
    
    # Cerca numero lavoratori
    match = re.search(r'(\d+)\s*lavorator', testo, re.I)
    if match:
        dati["numero_lavoratori"] = int(match.group(1))
    
    # Cerca ore
    match = re.search(r'(\d+)\s*ore', testo, re.I)
    if match:
        dati["ore_totali"] = int(match.group(1))
    
    # Cerca importo (formato italiano: 5.696,68)
    match = re.search(r'€?\s*([\d.]+,\d{2})', testo)
    if match:
        importo_str = match.group(1).replace('.', '').replace(',', '.')
        dati["importo"] = float(importo_str)
    
    # Cerca periodo
    dati["periodo"] = estrai_periodo_fonsi(testo)
    
    return dati


def estrai_dati_dilazione(testo: str) -> Dict[str, Any]:
    """
    Estrae dati dalla email di dilazione INPS.
    Cerca: Sede INPS, matricola, importo rate
    """
    dati = {
        "sede_inps": None,
        "matricola": None,
        "numero_rate": None,
        "importo_rata": None,
        "codice_dilazione": None
    }
    
    # Cerca sede INPS
    match = re.search(r'Sede\s+(?:INPS\s+)?(\d{4})', testo, re.I)
    if match:
        dati["sede_inps"] = match.group(1)
    
    # Cerca matricola
    match = re.search(r'matricola\s+(\d{10})', testo, re.I)
    if match:
        dati["matricola"] = match.group(1)
    
    # Cerca numero rate
    match = re.search(r'(\d+)\s*rat[ea]', testo, re.I)
    if match:
        dati["numero_rate"] = int(match.group(1))
    
    return dati


@router.get("/cartelle-delibere")
async def get_cartelle_delibere() -> Dict[str, Any]:
    """
    Lista le cartelle email che potrebbero contenere delibere FONSI.
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenziali email non configurate")
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        
        # Lista tutte le cartelle
        status, folders = mail.list()
        cartelle = []
        
        if status == "OK":
            for folder in folders:
                folder_str = folder.decode()
                # Estrai nome cartella
                match = re.search(r'"([^"]+)"$', folder_str)
                if match:
                    nome = match.group(1)
                    # Filtra cartelle rilevanti
                    if any(kw in nome.lower() for kw in ['inps', 'fonsi', 'deliber', 'pec', 'certificata']):
                        cartelle.append(nome)
        
        mail.logout()
        
        return {
            "cartelle": cartelle,
            "totale": len(cartelle)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore connessione email: {str(e)}")


@router.post("/scarica-delibere-fonsi")
async def scarica_delibere_fonsi(
    cartella: str = Query("INBOX", description="Cartella email da cercare"),
    data_inizio: str = Query(None, description="Data inizio ricerca (YYYY-MM-DD)"),
    data_fine: str = Query(None, description="Data fine ricerca (YYYY-MM-DD)")
) -> Dict[str, Any]:
    """
    Scarica le delibere FONSI dalla posta certificata.
    Cerca: "POSTA CERTIFICATA: Delibere - Fonsi"
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenziali email non configurate")
    
    db = Database.get_db()
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "delibere_trovate": 0,
        "delibere_salvate": 0,
        "delibere": [],
        "errori": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella)
        
        # Costruisci query di ricerca
        search_criteria = '(SUBJECT "Delibere - Fonsi")'
        
        if data_inizio:
            # Formato IMAP: DD-Mon-YYYY
            try:
                dt = datetime.strptime(data_inizio, "%Y-%m-%d")
                search_criteria = f'(SINCE {dt.strftime("%d-%b-%Y")} {search_criteria[1:-1]})'
            except Exception:
                pass
        
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            mail.logout()
            return risultati
        
        message_ids = messages[0].split()
        risultati["delibere_trovate"] = len(message_ids)
        
        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                subject = decode_email_subject(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                
                # Estrai periodo dal subject
                periodo = estrai_periodo_fonsi(subject)
                
                delibera = {
                    "subject": subject,
                    "data_email": date_str,
                    "periodo": periodo,
                    "allegati": [],
                    "dati_cassa_integrazione": None
                }
                
                # Cerca allegati PDF
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        filename = decode_email_subject(filename)
                        payload = part.get_payload(decode=True)
                        
                        if payload:
                            pdf_base64 = base64.b64encode(payload).decode('utf-8')
                            
                            # Salva nel database
                            doc = {
                                "tipo": "delibera_fonsi",
                                "subject": subject,
                                "data_email": date_str,
                                "periodo": periodo,
                                "filename": filename,
                                "pdf_base64": pdf_base64,
                                "data_inserimento": datetime.now(timezone.utc).isoformat() + "Z"
                            }
                            
                            # Evita duplicati
                            existing = await db[COLLECTION_FONSI].find_one({
                                "subject": subject,
                                "filename": filename
                            })
                            
                            if not existing:
                                await db[COLLECTION_FONSI].insert_one(doc)
                                risultati["delibere_salvate"] += 1
                            
                            delibera["allegati"].append({
                                "filename": filename,
                                "size": len(payload)
                            })
                
                risultati["delibere"].append(delibera)
                
            except Exception as e:
                risultati["errori"].append(f"Errore parsing email: {str(e)}")
        
        mail.logout()
        
    except Exception as e:
        risultati["errori"].append(f"Errore connessione: {str(e)}")
    
    return risultati


@router.post("/scarica-dilazioni-inps")
async def scarica_dilazioni_inps(
    cartella: str = Query("INBOX", description="Cartella email"),
    sede_inps: str = Query("5100", description="Sede INPS da cercare"),
    matricola: str = Query("5124776507", description="Matricola da cercare")
) -> Dict[str, Any]:
    """
    Scarica le email di dilazione INPS.
    Cerca: "Sede INPS {sede}, matricola {matricola}, Dilazione amministrativa"
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(status_code=500, detail="Credenziali email non configurate")
    
    db = Database.get_db()
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "email_trovate": 0,
        "dilazioni_salvate": 0,
        "dilazioni": [],
        "errori": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella)
        
        # Cerca email con dilazione
        search_criteria = f'(OR (BODY "{sede_inps}") (BODY "{matricola}"))'
        
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            mail.logout()
            return risultati
        
        message_ids = messages[0].split()
        
        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                subject = decode_email_subject(msg.get("Subject", ""))
                
                # Filtra per dilazione
                if "dilazion" not in subject.lower() and "inps" not in subject.lower():
                    continue
                
                risultati["email_trovate"] += 1
                
                date_str = msg.get("Date", "")
                
                dilazione = {
                    "subject": subject,
                    "data_email": date_str,
                    "sede_inps": sede_inps,
                    "matricola": matricola,
                    "allegati": []
                }
                
                # Cerca allegati PDF
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        filename = decode_email_subject(filename)
                        payload = part.get_payload(decode=True)
                        
                        if payload:
                            pdf_base64 = base64.b64encode(payload).decode('utf-8')
                            
                            doc = {
                                "tipo": "dilazione_inps",
                                "subject": subject,
                                "data_email": date_str,
                                "sede_inps": sede_inps,
                                "matricola": matricola,
                                "filename": filename,
                                "pdf_base64": pdf_base64,
                                "data_inserimento": datetime.now(timezone.utc).isoformat() + "Z"
                            }
                            
                            existing = await db[COLLECTION_DILAZIONI].find_one({
                                "subject": subject,
                                "filename": filename
                            })
                            
                            if not existing:
                                await db[COLLECTION_DILAZIONI].insert_one(doc)
                                risultati["dilazioni_salvate"] += 1
                            
                            dilazione["allegati"].append({
                                "filename": filename,
                                "size": len(payload)
                            })
                
                risultati["dilazioni"].append(dilazione)
                
            except Exception as e:
                risultati["errori"].append(str(e))
        
        mail.logout()
        
    except Exception as e:
        risultati["errori"].append(str(e))
    
    return risultati


@router.get("/delibere-fonsi")
async def get_delibere_fonsi(
    anno: int = Query(None, description="Filtra per anno")
) -> List[Dict[str, Any]]:
    """Lista tutte le delibere FONSI salvate."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["periodo.data_inizio"] = {"$regex": f"/{anno}$"}
    
    cursor = db[COLLECTION_FONSI].find(query, {"pdf_base64": 0})
    delibere = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        delibere.append(doc)
    
    return delibere


@router.get("/dilazioni-inps")
async def get_dilazioni_inps() -> List[Dict[str, Any]]:
    """Lista tutte le dilazioni INPS salvate."""
    db = Database.get_db()
    
    cursor = db[COLLECTION_DILAZIONI].find({}, {"pdf_base64": 0})
    dilazioni = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        dilazioni.append(doc)
    
    return dilazioni


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Statistiche documenti INPS."""
    db = Database.get_db()
    
    totale_fonsi = await db[COLLECTION_FONSI].count_documents({})
    totale_dilazioni = await db[COLLECTION_DILAZIONI].count_documents({})
    totale_cassa = await db[COLLECTION_CASSA_INTEGRAZIONE].count_documents({})
    
    return {
        "delibere_fonsi": totale_fonsi,
        "dilazioni_inps": totale_dilazioni,
        "cassa_integrazione": totale_cassa
    }


# =============================================================================
# CERTIFICATI MEDICI (Malattia Dipendenti)
# =============================================================================

COLLECTION_CERTIFICATI_MEDICI = "certificati_medici"


def estrai_dati_certificato_medico(testo: str, subject: str) -> Dict[str, Any]:
    """
    Estrae dati da un certificato medico INPS.
    Cerca: numero protocollo, codice fiscale, date malattia
    """
    dati = {
        "protocollo": None,
        "codice_fiscale": None,
        "data_inizio": None,
        "data_fine": None,
        "dipendente_nome": None
    }
    
    # Estrai numero protocollo (formato tipico: 12345678)
    prot_match = re.search(r'protocollo[:\s]*(\d{6,12})', testo, re.I)
    if prot_match:
        dati["protocollo"] = prot_match.group(1)
    else:
        # Prova nel subject
        prot_match = re.search(r'(\d{8,12})', subject)
        if prot_match:
            dati["protocollo"] = prot_match.group(1)
    
    # Estrai codice fiscale
    cf_match = re.search(r'[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]', testo, re.I)
    if cf_match:
        dati["codice_fiscale"] = cf_match.group(0).upper()
    
    # Estrai date
    date_match = re.findall(r'(\d{2}/\d{2}/\d{4})', testo)
    if len(date_match) >= 2:
        dati["data_inizio"] = date_match[0]
        dati["data_fine"] = date_match[1]
    elif len(date_match) == 1:
        dati["data_inizio"] = date_match[0]
        dati["data_fine"] = date_match[0]
    
    return dati


@router.post("/scansiona-certificati-medici")
async def scansiona_certificati_medici(
    cartella: str = Query("INBOX", description="Cartella email da scansionare"),
    limite: int = Query(50, description="Numero massimo email da processare")
) -> Dict[str, Any]:
    """
    Scansiona la posta in cerca di certificati medici INPS.
    Estrae: numero protocollo, codice fiscale, date malattia.
    Associa automaticamente al dipendente se trova match.
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(400, "Credenziali email non configurate")
    
    db = Database.get_db()
    
    # Carica dipendenti per match
    dipendenti = await db["dipendenti"].find(
        {},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "codice_fiscale": 1, "nome_completo": 1}
    ).to_list(500)
    
    cf_to_emp = {}
    for d in dipendenti:
        cf = d.get("codice_fiscale", "").upper()
        if cf:
            cf_to_emp[cf] = d
    
    results = {
        "trovati": 0,
        "salvati": 0,
        "associati": 0,
        "errori": [],
        "certificati": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella)
        
        # Cerca email con keywords
        keywords = ["certificato medico", "malattia", "INPS", "protocollo"]
        all_ids = set()
        
        for kw in keywords:
            try:
                status, messages = mail.search(None, f'(SUBJECT "{kw}")')
                if status == "OK" and messages[0]:
                    all_ids.update(messages[0].split())
            except Exception:
                pass
            
            try:
                status, messages = mail.search(None, f'(BODY "{kw}")')
                if status == "OK" and messages[0]:
                    all_ids.update(messages[0].split())
            except Exception:
                pass
        
        email_ids = list(all_ids)[-limite:]
        
        for eid in email_ids:
            try:
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                subject = decode_email_subject(msg["Subject"])
                from_addr = msg["From"]
                date_str = msg["Date"]
                
                # Estrai testo
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode("utf-8", errors="replace")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                
                # Verifica se è un certificato medico
                testo_completo = f"{subject} {body}".lower()
                if not any(kw in testo_completo for kw in ["certificato", "malattia", "protocollo"]):
                    continue
                
                results["trovati"] += 1
                
                # Estrai dati
                dati = estrai_dati_certificato_medico(body, subject)
                
                if not dati["protocollo"]:
                    results["errori"].append(f"No protocollo: {subject[:50]}")
                    continue
                
                # Verifica se già esiste
                existing = await db[COLLECTION_CERTIFICATI_MEDICI].find_one(
                    {"protocollo": dati["protocollo"]}
                )
                if existing:
                    continue
                
                # Associa dipendente
                employee_id = None
                employee_nome = None
                if dati["codice_fiscale"] and dati["codice_fiscale"] in cf_to_emp:
                    emp = cf_to_emp[dati["codice_fiscale"]]
                    employee_id = emp.get("id")
                    employee_nome = emp.get("nome_completo") or f'{emp.get("nome", "")} {emp.get("cognome", "")}'.strip()
                    results["associati"] += 1
                
                # Estrai allegato PDF se presente
                pdf_base64 = None
                pdf_filename = None
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        fn = part.get_filename()
                        if ct == "application/pdf" or (fn and fn.lower().endswith(".pdf")):
                            payload = part.get_payload(decode=True)
                            if payload:
                                pdf_base64 = base64.b64encode(payload).decode("utf-8")
                                pdf_filename = fn or "certificato.pdf"
                                break
                
                # Salva
                certificato = {
                    "protocollo": dati["protocollo"],
                    "codice_fiscale": dati["codice_fiscale"],
                    "data_inizio_malattia": dati["data_inizio"],
                    "data_fine_malattia": dati["data_fine"],
                    "employee_id": employee_id,
                    "employee_nome": employee_nome,
                    "email_subject": subject,
                    "email_from": from_addr,
                    "email_date": date_str,
                    "pdf_filename": pdf_filename,
                    "pdf_base64": pdf_base64,
                    "created_at": datetime.now().isoformat()
                }
                
                await db[COLLECTION_CERTIFICATI_MEDICI].insert_one(certificato)
                results["salvati"] += 1
                
                # Aggiungi al risultato (senza pdf per response)
                cert_result = {k: v for k, v in certificato.items() if k != "pdf_base64"}
                results["certificati"].append(cert_result)
                
                # Se associato, aggiorna anche le note presenze
                if employee_id and dati["data_inizio"]:
                    try:
                        # Converte data italiana a ISO
                        d, m, y = dati["data_inizio"].split("/")
                        data_iso = f"{y}-{m}-{d}"
                        
                        await db["attendance_note_presenze"].update_one(
                            {"employee_id": employee_id, "data": data_iso},
                            {"$set": {
                                "protocollo_malattia": dati["protocollo"],
                                "updated_at": datetime.now().isoformat()
                            }},
                            upsert=True
                        )
                    except Exception:
                        pass
                
            except Exception as e:
                results["errori"].append(str(e)[:100])
        
        mail.logout()
        
    except Exception as e:
        raise HTTPException(500, f"Errore connessione email: {str(e)}")
    
    return {
        "success": True,
        **results
    }


@router.get("/certificati-medici")
async def get_certificati_medici(
    anno: int = Query(None),
    employee_id: str = Query(None)
) -> Dict[str, Any]:
    """Lista certificati medici salvati."""
    db = Database.get_db()
    
    filtro = {}
    if employee_id:
        filtro["employee_id"] = employee_id
    
    cursor = db[COLLECTION_CERTIFICATI_MEDICI].find(
        filtro,
        {"pdf_base64": 0, "_id": 0}
    ).sort("created_at", -1)
    
    certificati = await cursor.to_list(500)
    
    # Filtra per anno se specificato
    if anno:
        certificati = [c for c in certificati 
                      if c.get("data_inizio_malattia", "").endswith(str(anno))]
    
    return {
        "success": True,
        "totale": len(certificati),
        "certificati": certificati
    }


@router.get("/certificati-medici/{protocollo}/pdf")
async def get_certificato_pdf(protocollo: str):
    """Scarica il PDF di un certificato medico."""
    from fastapi.responses import Response
    
    db = Database.get_db()
    
    cert = await db[COLLECTION_CERTIFICATI_MEDICI].find_one({"protocollo": protocollo})
    if not cert or not cert.get("pdf_base64"):
        raise HTTPException(404, "Certificato o PDF non trovato")
    
    pdf_data = base64.b64decode(cert["pdf_base64"])
    filename = cert.get("pdf_filename", f"certificato_{protocollo}.pdf")
    
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
