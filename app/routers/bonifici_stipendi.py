"""
Router Bonifici Stipendi - Estrae bonifici dalla posta e li associa ai salari.

LOGICA:
1. Email "Info Bonifico YouBusiness Web" = importo PROVVISORIO (da validare)
2. Estratto Conto = CONFERMA definitiva (riconciliato)
3. Se email OK ma non in estratto conto = potrebbe essere fallito (mancanza fondi)

FLUSSO:
Email bonifico → stato "email_ricevuta" → Estratto conto match → stato "riconciliato"
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone
import imaplib
import email
from email.header import decode_header
import os
import re
import uuid
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bonifici-stipendi", tags=["Bonifici Stipendi"])

# Configurazione Email
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
EMAIL_ADDRESS = os.environ.get("GMAIL_EMAIL", "ceraldigroupsrl@gmail.com")
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Collection
COLLECTION_BONIFICI = "bonifici_stipendi"


def get_imap_connection():
    """Crea connessione IMAP a Gmail."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        return mail
    except Exception as e:
        logger.error(f"Errore connessione IMAP: {e}")
        return None


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
    except Exception as e:
        logger.warning(f"Errore decode header: {e}")
        return str(value)


def parse_bonifico_email(body: str) -> Dict[str, Any]:
    """
    Estrae dati dal corpo email bonifico.
    
    Formato tipico:
    P6325959 : CERALDI GROUP S.R.L.
    Autorizzata distinta di 1 bonifico per
    totale euro 1.408,00 su Banca 05034 a favore di: Carotenuto Antonella 
    (data:12-01-2026 ora:16:59)
    """
    result = {
        "importo": None,
        "beneficiario": None,
        "data_operazione": None,
        "ora_operazione": None,
        "banca": None,
        "num_bonifici": 1
    }
    
    # Importo: "totale euro 1.408,00" o "euro 1408.00"
    imp_match = re.search(r'(?:totale\s+)?euro\s+([\d.,]+)', body, re.IGNORECASE)
    if imp_match:
        importo_str = imp_match.group(1).replace('.', '').replace(',', '.')
        try:
            result["importo"] = float(importo_str)
        except ValueError:
            logger.warning(f"Impossibile convertire importo: {importo_str}")
    
    # Beneficiario: "a favore di: Nome Cognome"
    ben_match = re.search(r'a favore di[:\s]+([^\n\(]+)', body, re.IGNORECASE)
    if ben_match:
        result["beneficiario"] = ben_match.group(1).strip()
    
    # Data: "data:12-01-2026"
    data_match = re.search(r'data[:\s]+(\d{2}-\d{2}-\d{4})', body, re.IGNORECASE)
    if data_match:
        # Converti da DD-MM-YYYY a YYYY-MM-DD
        d, m, y = data_match.group(1).split('-')
        result["data_operazione"] = f"{y}-{m}-{d}"
    
    # Ora: "ora:16:59"
    ora_match = re.search(r'ora[:\s]+(\d{2}:\d{2})', body, re.IGNORECASE)
    if ora_match:
        result["ora_operazione"] = ora_match.group(1)
    
    # Banca: "su Banca 05034"
    banca_match = re.search(r'(?:su\s+)?[Bb]anca\s+(\d+)', body)
    if banca_match:
        result["banca"] = banca_match.group(1)
    
    # Numero bonifici: "distinta di 1 bonifico"
    num_match = re.search(r'distinta di\s+(\d+)\s+bonific', body, re.IGNORECASE)
    if num_match:
        result["num_bonifici"] = int(num_match.group(1))
    
    return result


def normalizza_nome_dipendente(nome: str) -> str:
    """Normalizza nome dipendente per matching."""
    if not nome:
        return ""
    # Rimuovi spazi extra, uppercase
    nome = ' '.join(nome.upper().split())
    # Rimuovi titoli comuni
    nome = re.sub(r'\b(SIG|SIG\.|DOTT|DOTT\.|ING|ING\.)\s*', '', nome)
    return nome.strip()


@router.post("/scarica-da-email")
@handle_errors
async def scarica_bonifici_da_email(
    cerca_tutte_cartelle: bool = False,
    anni_indietro: int = 5
) -> Dict[str, Any]:
    """
    Scarica tutti i bonifici stipendi dalle email.
    
    Args:
        cerca_tutte_cartelle: Se True, cerca in tutte le cartelle
        anni_indietro: Quanti anni indietro cercare
    """
    # ── Guard legacy email ───────────────────────────────────────────────
    # Endpoint disattivato di default. Per riattivarlo (transizione) impostare
    # ENABLE_GMAIL_SYNC=true in backend/.env. Regola CLAUDE.md: solo upload manuale.
    from app.config import settings as _settings_legacy
    if not _settings_legacy.ENABLE_GMAIL_SYNC:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=410,
            detail={
                "errore": "canale_legacy_disattivato",
                "messaggio": "Canale legacy: scarico bonifici stipendi da email. Usare upload manuale.",
                "flag_per_riattivare": "ENABLE_GMAIL_SYNC",
            },
        )

    db = Database.get_db()
    
    mail = get_imap_connection()
    if not mail:
        raise HTTPException(status_code=500, detail="Connessione email fallita")
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email_analizzate": 0,
        "bonifici_estratti": 0,
        "gia_presenti": 0,
        "dipendenti_trovati": [],
        "errori": []
    }
    
    try:
        cartelle_da_cercare = ["INBOX"]
        
        if cerca_tutte_cartelle:
            # Aggiungi altre cartelle
            status, folders = mail.list()
            for folder in folders:
                folder_str = folder.decode()
                if '"/"' in folder_str:
                    name = folder_str.split('"/"')[-1].strip().strip('"')
                    if any(k in name.lower() for k in ['bonifici', 'stipendi', 'paghe', 'sent', 'inviata']):
                        cartelle_da_cercare.append(name)
        
        for cartella in cartelle_da_cercare:
            try:
                status, _ = mail.select(f'"{cartella}"', readonly=True)
                if status != 'OK':
                    continue
                
                # Cerca email bonifici
                status, messages = mail.search(None, '(SUBJECT "Info Bonifico YouBusiness")')
                if status != 'OK':
                    continue
                
                msg_ids = messages[0].split()
                
                for msg_id in msg_ids:
                    risultati["email_analizzate"] += 1
                    
                    try:
                        status, msg_data = mail.fetch(msg_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        # Estrai corpo
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ct = part.get_content_type()
                                if ct == "text/plain":
                                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        if not body:
                            continue
                        
                        # Parse dati bonifico
                        dati = parse_bonifico_email(body)
                        
                        if not dati["importo"] or not dati["beneficiario"]:
                            continue
                        
                        # Crea ID univoco basato su data + beneficiario + importo
                        bonifico_key = f"{dati['data_operazione']}_{dati['beneficiario']}_{dati['importo']}"
                        
                        # Verifica se già presente
                        esistente = await db[COLLECTION_BONIFICI].find_one({"bonifico_key": bonifico_key})
                        if esistente:
                            risultati["gia_presenti"] += 1
                            continue
                        
                        # Salva bonifico
                        bonifico_doc = {
                            "id": str(uuid.uuid4()),
                            "bonifico_key": bonifico_key,
                            "beneficiario": dati["beneficiario"],
                            "beneficiario_normalizzato": normalizza_nome_dipendente(dati["beneficiario"]),
                            "importo": dati["importo"],
                            "data_operazione": dati["data_operazione"],
                            "ora_operazione": dati["ora_operazione"],
                            "banca": dati["banca"],
                            "email_date": msg.get("Date", ""),
                            "email_subject": decode_header_value(msg.get("Subject", "")),
                            "cartella": cartella,
                            "body_raw": body[:500],  # Solo primi 500 char per debug
                            
                            # Stati
                            "stato": "email_ricevuta",  # email_ricevuta → riconciliato
                            "validato_estratto_conto": False,
                            "movimento_ec_id": None,
                            "dipendente_id": None,
                            "salario_aggiornato": False,
                            
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        
                        await db[COLLECTION_BONIFICI].insert_one(bonifico_doc)
                        risultati["bonifici_estratti"] += 1
                        
                        if dati["beneficiario"] not in risultati["dipendenti_trovati"]:
                            risultati["dipendenti_trovati"].append(dati["beneficiario"])
                        
                    except Exception as e:
                        risultati["errori"].append(str(e)[:100])
                        
            except Exception as e:
                risultati["errori"].append(f"Cartella {cartella}: {str(e)[:50]}")
        
        mail.logout()
        return risultati
        
    except Exception as e:
        if mail:
            mail.logout()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/associa-dipendenti")
@handle_errors
async def associa_bonifici_a_dipendenti() -> Dict[str, Any]:
    """
    Associa i bonifici ai dipendenti nel database.
    Aggiorna il campo importo_bonifico in prima_nota_salari.
    
    ATTENZIONE: NON rende definitivo, solo aggiorna importo provvisorio.
    La validazione avviene solo con estratto conto.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bonifici_analizzati": 0,
        "dipendenti_associati": 0,
        "salari_aggiornati": 0,
        "non_trovati": [],
        "errori": []
    }
    
    # Carica bonifici non ancora associati a dipendenti
    bonifici = await db[COLLECTION_BONIFICI].find({
        "dipendente_id": None,
        # Solo quelli che sembrano dipendenti (non fornitori)
        "beneficiario": {"$not": {"$regex": "S\\.?R\\.?L|S\\.?P\\.?A|S\\.?N\\.?C|SAS|COMUNE|AGENZIA", "$options": "i"}}
    }, {"_id": 0}).to_list(10000)
    
    risultati["bonifici_analizzati"] = len(bonifici)
    
    # Carica dipendenti da employees (collezione principale)
    dipendenti = await db.employees.find({}, {"_id": 0}).to_list(1000)
    
    # Crea indice dipendenti per nome normalizzato
    dip_idx = {}
    for d in dipendenti:
        # Prova diversi campi nome
        cognome = d.get('cognome', d.get('surname', ''))
        nome = d.get('nome', d.get('name', d.get('first_name', '')))
        
        nome_completo = f"{cognome} {nome}".strip()
        nome_norm = normalizza_nome_dipendente(nome_completo)
        if nome_norm:
            dip_idx[nome_norm] = d
        
        # Aggiungi anche inversione nome/cognome
        nome_inv = f"{nome} {cognome}".strip()
        nome_inv_norm = normalizza_nome_dipendente(nome_inv)
        if nome_inv_norm:
            dip_idx[nome_inv_norm] = d
    
    # Aggiungi anche nomi da prima_nota_salari
    salari_nomi = await db.prima_nota_salari.distinct("dipendente_nome")
    for nome in salari_nomi:
        if nome:
            nome_norm = normalizza_nome_dipendente(nome)
            if nome_norm and nome_norm not in dip_idx:
                dip_idx[nome_norm] = {"dipendente_nome": nome, "id": nome}
    
    logger.info(f"Indice dipendenti: {len(dip_idx)} nomi")
    
    for bonifico in bonifici:
        ben_norm = bonifico.get("beneficiario_normalizzato", "")
        
        # Cerca match esatto
        dipendente = dip_idx.get(ben_norm)
        
        # Se non trovato, cerca match parziale
        if not dipendente:
            for nome_dip, d in dip_idx.items():
                # Match se contiene cognome
                parti_ben = ben_norm.split()
                parti_dip = nome_dip.split()
                if len(parti_ben) >= 1 and len(parti_dip) >= 1:
                    # Confronta cognome (primo elemento)
                    if parti_ben[0] == parti_dip[0] or parti_ben[-1] == parti_dip[0]:
                        dipendente = d
                        break
        
        if dipendente:
            try:
                dip_id = dipendente.get("id") or dipendente.get("_id") or str(uuid.uuid4())
                dip_nome = dipendente.get("dipendente_nome") or f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
                
                # Aggiorna bonifico con dipendente
                await db[COLLECTION_BONIFICI].update_one(
                    {"id": bonifico["id"]},
                    {"$set": {
                        "dipendente_id": str(dip_id),
                        "dipendente_nome": dip_nome,
                        "dipendente_cf": dipendente.get("codice_fiscale", dipendente.get("fiscal_code")),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                risultati["dipendenti_associati"] += 1
                
                # Aggiorna prima_nota_salari con importo provvisorio
                data_op = bonifico.get("data_operazione", "")
                if data_op:
                    anno = int(data_op[:4])
                    mese = int(data_op[5:7])
                    
                    # Cerca riga salario esistente per nome normalizzato
                    salario = await db.prima_nota_salari.find_one({
                        "$or": [
                            {"dipendente_id": str(dip_id)},
                            {"dipendente_nome": {"$regex": ben_norm.split()[0], "$options": "i"}}
                        ],
                        "anno": anno,
                        "mese": mese
                    })
                    
                    if salario:
                        # Aggiorna con importo da email (PROVVISORIO)
                        await db.prima_nota_salari.update_one(
                            {"id": salario["id"]},
                            {"$set": {
                                "importo_bonifico_email": bonifico["importo"],
                                "bonifico_email_id": bonifico["id"],
                                "bonifico_stato": "email_ricevuta",
                                "bonifico_da_validare": True,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["salari_aggiornati"] += 1
                
            except Exception as e:
                risultati["errori"].append(f"{bonifico['beneficiario']}: {str(e)[:50]}")
        else:
            # Aggiungi solo se sembra un nome persona
            ben = bonifico.get("beneficiario", "")
            if not any(k in ben.upper() for k in ["SRL", "SPA", "SNC", "SAS", "COMUNE", "AGENZIA", "REPOWER", "KIMBO", "EDENRED"]):
                if ben not in risultati["non_trovati"]:
                    risultati["non_trovati"].append(ben)
    
    return risultati


@router.post("/riconcilia-con-estratto-conto")
@handle_errors
async def riconcilia_con_estratto_conto() -> Dict[str, Any]:
    """
    Confronta bonifici email con estratto conto.
    
    SOLO quando trova match in estratto conto → valida e rende DEFINITIVO.
    Se email OK ma non in EC → rimane "da_validare" (possibile fallimento).
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bonifici_analizzati": 0,
        "riconciliati": 0,
        "non_trovati_in_ec": 0,
        "possibili_falliti": [],
        "errori": []
    }
    
    # Carica bonifici da validare
    bonifici = await db[COLLECTION_BONIFICI].find({
        "validato_estratto_conto": False,
        "stato": "email_ricevuta"
    }, {"_id": 0}).to_list(10000)
    
    risultati["bonifici_analizzati"] = len(bonifici)
    
    for bonifico in bonifici:
        importo = bonifico.get("importo", 0)
        beneficiario = bonifico.get("beneficiario", "")
        data_op = bonifico.get("data_operazione", "")
        
        if not importo:
            continue
        
        # Cerca in estratto conto
        # Match per importo (negativo perché uscita) e nome beneficiario
        query = {
            "importo": {"$gte": -importo - 5, "$lte": -importo + 5},  # Tolleranza ±5€
        }
        
        if data_op:
            # Cerca nella stessa settimana
            query["data"] = {"$regex": data_op[:7]}  # Stesso mese
        
        movimenti = await db.estratto_conto_movimenti.find(query, {"_id": 0}).to_list(100)
        
        # Filtra per nome beneficiario
        movimento_match = None
        ben_norm = normalizza_nome_dipendente(beneficiario)
        
        for mov in movimenti:
            desc = (mov.get("descrizione_originale") or mov.get("descrizione") or "").upper()
            # Cerca nome nel movimento
            if ben_norm and any(part in desc for part in ben_norm.split()):
                movimento_match = mov
                break
        
        if movimento_match:
            try:
                # RICONCILIATO! Valida definitivamente
                await db[COLLECTION_BONIFICI].update_one(
                    {"id": bonifico["id"]},
                    {"$set": {
                        "stato": "riconciliato",
                        "validato_estratto_conto": True,
                        "movimento_ec_id": movimento_match.get("id"),
                        "movimento_ec_data": movimento_match.get("data"),
                        "movimento_ec_importo": movimento_match.get("importo"),
                        "riconciliato_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Aggiorna estratto conto
                await db.estratto_conto_movimenti.update_one(
                    {"id": movimento_match["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "tipo_riconciliazione": "stipendio",
                        "bonifico_stipendio_id": bonifico["id"],
                        "dipendente": beneficiario
                    }}
                )
                
                # Aggiorna prima_nota_salari come DEFINITIVO
                if bonifico.get("dipendente_id"):
                    data_op = bonifico.get("data_operazione", "")
                    if data_op:
                        await db.prima_nota_salari.update_many(
                            {
                                "dipendente_id": bonifico["dipendente_id"],
                                "bonifico_email_id": bonifico["id"]
                            },
                            {"$set": {
                                "importo_bonifico": bonifico["importo"],  # Ora DEFINITIVO
                                "bonifico_stato": "riconciliato",
                                "bonifico_da_validare": False,
                                "movimento_ec_id": movimento_match.get("id"),
                                "riconciliato_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                
                risultati["riconciliati"] += 1
                
            except Exception as e:
                risultati["errori"].append(str(e)[:100])
        else:
            risultati["non_trovati_in_ec"] += 1
            # Potrebbe essere fallito per mancanza fondi
            risultati["possibili_falliti"].append({
                "beneficiario": beneficiario,
                "importo": importo,
                "data": data_op,
                "nota": "Email ricevuta ma non trovato in estratto conto"
            })
    
    return risultati


@router.get("/bonifici")
@handle_errors
async def lista_bonifici(
    stato: str = None,
    dipendente: str = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Lista bonifici."""
    db = Database.get_db()
    
    query = {}
    if stato:
        query["stato"] = stato
    if dipendente:
        query["beneficiario"] = {"$regex": dipendente, "$options": "i"}
    
    bonifici = await db[COLLECTION_BONIFICI].find(
        query, {"_id": 0, "body_raw": 0}
    ).sort("data_operazione", -1).limit(limit).to_list(limit)
    
    return bonifici


@router.get("/stats")
@handle_errors
async def stats_bonifici() -> Dict[str, Any]:
    """Statistiche bonifici."""
    db = Database.get_db()
    
    totale = await db[COLLECTION_BONIFICI].count_documents({})
    email_ricevuta = await db[COLLECTION_BONIFICI].count_documents({"stato": "email_ricevuta"})
    riconciliati = await db[COLLECTION_BONIFICI].count_documents({"stato": "riconciliato"})
    con_dipendente = await db[COLLECTION_BONIFICI].count_documents({"dipendente_id": {"$ne": None}})
    
    # Totale importi
    pipeline = [
        {"$match": {"stato": "riconciliato"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]
    agg = await db[COLLECTION_BONIFICI].aggregate(pipeline).to_list(1)
    totale_riconciliato = agg[0]["totale"] if agg else 0
    
    return {
        "totale_bonifici": totale,
        "email_ricevuta": email_ricevuta,
        "riconciliati": riconciliati,
        "da_validare": email_ricevuta,
        "con_dipendente": con_dipendente,
        "totale_importo_riconciliato": round(totale_riconciliato, 2)
    }
