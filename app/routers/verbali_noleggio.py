"""
Router Verbali Noleggio - Scarica verbali dalla posta e li associa alle fatture.

Cerca nelle cartelle email i verbali (pattern Bxxxxxxxxxx) e li associa
alle righe corrispondenti nelle fatture noleggio.
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
import base64

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/verbali-noleggio", tags=["Verbali Noleggio"])

# Configurazione Email
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", os.environ.get("GMAIL_EMAIL", "ceraldigroupsrl@gmail.com"))
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD"))

# Collection
COLLECTION_VERBALI = "verbali_noleggio"
COLLECTION_FATTURE_NOLEGGIO = "fatture_noleggio"


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
    except Exception:
        return str(value)


@router.get("/cartelle-verbali")
@handle_errors
async def lista_cartelle_verbali() -> Dict[str, Any]:
    """
    Lista tutte le cartelle email che contengono verbali noleggio.
    Pattern: Bxxxxxxxxxx (es. B23123049750)
    """
    mail = get_imap_connection()
    if not mail:
        raise HTTPException(status_code=500, detail="Connessione email fallita")
    
    try:
        status, folders = mail.list()
        
        verbali_cartelle = []
        pattern = re.compile(r'^B\d{10,11}$')
        
        for folder in folders:
            folder_str = folder.decode()
            if '"/"' in folder_str:
                name = folder_str.split('"/"')[-1].strip().strip('"')
                if pattern.match(name):
                    verbali_cartelle.append(name)
        
        mail.logout()
        
        return {
            "cartelle": sorted(verbali_cartelle),
            "count": len(verbali_cartelle)
        }
    except Exception as e:
        mail.logout()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scarica-tutti")
@handle_errors
async def scarica_tutti_verbali() -> Dict[str, Any]:
    """
    Scarica tutti i PDF dei verbali dalle cartelle email.
    Li salva nel database con il numero verbale come chiave.
    """
    db = Database.get_db()
    
    mail = get_imap_connection()
    if not mail:
        raise HTTPException(status_code=500, detail="Connessione email fallita")
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cartelle_analizzate": 0,
        "verbali_trovati": 0,
        "pdf_scaricati": 0,
        "gia_presenti": 0,
        "errori": []
    }
    
    try:
        # Lista cartelle verbali
        status, folders = mail.list()
        
        pattern = re.compile(r'^B\d{10,11}$')
        cartelle_verbali = []
        
        for folder in folders:
            folder_str = folder.decode()
            if '"/"' in folder_str:
                name = folder_str.split('"/"')[-1].strip().strip('"')
                if pattern.match(name):
                    cartelle_verbali.append(name)
        
        risultati["cartelle_analizzate"] = len(cartelle_verbali)
        
        for cartella in cartelle_verbali:
            numero_verbale = cartella  # Il nome cartella è il numero verbale
            
            # Verifica se già scaricato
            esistente = await db[COLLECTION_VERBALI].find_one({"numero_verbale": numero_verbale})
            if esistente and esistente.get("pdf_scaricato"):
                risultati["gia_presenti"] += 1
                continue
            
            try:
                status, _ = mail.select(f'"{cartella}"', readonly=True)
                if status != 'OK':
                    continue
                
                status, messages = mail.search(None, 'ALL')
                if status != 'OK':
                    continue
                
                msg_ids = messages[0].split()
                risultati["verbali_trovati"] += 1
                
                pdf_allegati = []
                subject_verbale = ""
                data_email = None
                mittente = ""
                
                for msg_id in msg_ids:
                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                    if status != 'OK':
                        continue
                    
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    # Info email
                    subject_verbale = decode_header_value(msg.get('Subject', ''))
                    mittente = msg.get('From', '')
                    date_str = msg.get('Date', '')
                    
                    # Cerca PDF allegati
                    if msg.is_multipart():
                        for part in msg.walk():
                            filename = part.get_filename()
                            if filename and '.pdf' in filename.lower():
                                # Scarica contenuto PDF
                                pdf_content = part.get_payload(decode=True)
                                if pdf_content:
                                    pdf_allegati.append({
                                        "filename": decode_header_value(filename),
                                        "content_base64": base64.b64encode(pdf_content).decode('utf-8'),
                                        "size": len(pdf_content)
                                    })
                
                # Salva in database
                verbale_doc = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": numero_verbale,
                    "cartella_email": cartella,
                    "subject": subject_verbale,
                    "mittente": mittente,
                    "pdf_allegati": pdf_allegati,
                    "pdf_scaricato": len(pdf_allegati) > 0,
                    "num_pdf": len(pdf_allegati),
                    "fattura_associata": None,
                    "riga_fattura_id": None,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLLECTION_VERBALI].update_one(
                    {"numero_verbale": numero_verbale},
                    {"$set": verbale_doc},
                    upsert=True
                )
                
                if pdf_allegati:
                    risultati["pdf_scaricati"] += len(pdf_allegati)
                
            except Exception as e:
                risultati["errori"].append(f"{cartella}: {str(e)}")
        
        mail.logout()
        return risultati
        
    except Exception as e:
        if mail:
            mail.logout()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verbali")
@handle_errors
async def lista_verbali(
    associato: bool = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Lista verbali scaricati."""
    db = Database.get_db()
    
    query = {}
    if associato is not None:
        if associato:
            query["fattura_associata"] = {"$ne": None}
        else:
            query["fattura_associata"] = None
    
    verbali = await db[COLLECTION_VERBALI].find(
        query, 
        {"_id": 0, "pdf_allegati": 0}  # Escludi PDF pesanti dalla lista
    ).sort("numero_verbale", -1).limit(limit).to_list(limit)
    
    return verbali


@router.get("/verbale/{numero_verbale}")
@handle_errors
async def get_verbale(numero_verbale: str) -> Dict[str, Any]:
    """Dettaglio verbale con PDF."""
    db = Database.get_db()
    
    verbale = await db[COLLECTION_VERBALI].find_one(
        {"numero_verbale": numero_verbale},
        {"_id": 0}
    )
    
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    
    return verbale


@router.post("/associa-fatture")
@handle_errors
async def associa_verbali_a_fatture() -> Dict[str, Any]:
    """
    Cerca nelle fatture noleggio i verbali e li associa automaticamente.
    
    Logica:
    1. Per ogni verbale scaricato
    2. Cerca nelle fatture noleggio (campo 'linee') una riga con quel numero verbale
    3. Se trovata, associa
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verbali_analizzati": 0,
        "associazioni_trovate": 0,
        "non_trovati": [],
        "errori": []
    }
    
    # Carica tutti i verbali non ancora associati
    verbali = await db[COLLECTION_VERBALI].find(
        {"fattura_associata": None},
        {"_id": 0, "pdf_allegati": 0}
    ).to_list(1000)
    
    risultati["verbali_analizzati"] = len(verbali)
    
    # Carica TUTTE le fatture noleggio (ALD, Leasys, Arval, etc.)
    fatture = await db.invoices.find({
        "supplier_name": {"$regex": "ald|leasys|arval|ayvens|locauto|leaseplan|noleggio", "$options": "i"}
    }, {"_id": 0}).to_list(50000)
    
    # Crea indice: numero_verbale -> fattura
    verbale_fattura_idx = {}
    for fattura in fatture:
        linee = fattura.get("linee", [])
        for linea in linee:
            desc = linea.get("descrizione", "")
            # Cerca pattern verbale Bxxxxxxxxxx
            matches = re.findall(r'B\d{10,11}', desc, re.IGNORECASE)
            for num_verb in matches:
                verbale_fattura_idx[num_verb.upper()] = {
                    "fattura_id": fattura.get("id"),
                    "invoice_number": fattura.get("invoice_number"),
                    "supplier_name": fattura.get("supplier_name"),
                    "invoice_date": fattura.get("invoice_date"),
                    "total_amount": fattura.get("total_amount"),
                    "linea_descrizione": desc,
                    "linea_importo": linea.get("prezzo_totale") or linea.get("importo")
                }
    
    logger.info(f"Trovate {len(verbale_fattura_idx)} fatture con verbali")
    
    for verbale in verbali:
        numero = verbale.get("numero_verbale", "").upper()
        
        if numero in verbale_fattura_idx:
            fattura_info = verbale_fattura_idx[numero]
            
            try:
                await db[COLLECTION_VERBALI].update_one(
                    {"numero_verbale": verbale["numero_verbale"]},
                    {"$set": {
                        "fattura_associata": fattura_info["fattura_id"],
                        "invoice_number": fattura_info["invoice_number"],
                        "supplier_name": fattura_info["supplier_name"],
                        "invoice_date": fattura_info["invoice_date"],
                        "importo_fattura": fattura_info["total_amount"],
                        "linea_descrizione": fattura_info["linea_descrizione"],
                        "linea_importo": fattura_info["linea_importo"],
                        "associato_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Aggiorna anche la fattura con riferimento al verbale PDF
                await db.invoices.update_one(
                    {"id": fattura_info["fattura_id"]},
                    {"$set": {
                        f"verbale_pdf.{numero}": {
                            "verbale_id": verbale.get("id"),
                            "pdf_scaricato": True,
                            "scaricato_at": datetime.now(timezone.utc).isoformat()
                        }
                    }}
                )
                
                risultati["associazioni_trovate"] += 1
            except Exception as e:
                risultati["errori"].append(f"{numero}: {str(e)}")
        else:
            risultati["non_trovati"].append(numero)
    
    return risultati


@router.get("/pdf/{numero_verbale}")
@handle_errors
async def get_pdf_verbale(numero_verbale: str, indice: int = 0) -> Dict[str, Any]:
    """
    Ottiene il PDF del verbale in base64.
    indice: quale PDF se ce ne sono più di uno (default primo)
    """
    db = Database.get_db()
    
    verbale = await db[COLLECTION_VERBALI].find_one(
        {"numero_verbale": numero_verbale},
        {"_id": 0}
    )
    
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    
    pdf_allegati = verbale.get("pdf_allegati", [])
    
    if not pdf_allegati or indice >= len(pdf_allegati):
        raise HTTPException(status_code=404, detail="PDF non trovato")
    
    pdf = pdf_allegati[indice]
    
    return {
        "numero_verbale": numero_verbale,
        "filename": pdf.get("filename"),
        "content_base64": pdf.get("content_base64"),
        "size": pdf.get("size")
    }


@router.get("/stats")
@handle_errors
async def stats_verbali() -> Dict[str, Any]:
    """Statistiche verbali."""
    db = Database.get_db()
    
    totale = await db[COLLECTION_VERBALI].count_documents({})
    con_pdf = await db[COLLECTION_VERBALI].count_documents({"pdf_scaricato": True})
    associati = await db[COLLECTION_VERBALI].count_documents({"fattura_associata": {"$ne": None}})
    
    return {
        "totale_verbali": totale,
        "con_pdf": con_pdf,
        "associati_a_fatture": associati,
        "non_associati": totale - associati
    }


@router.post("/scansiona-fatture")
@handle_errors
async def scansiona_fatture_per_verbali_endpoint() -> Dict[str, Any]:
    """
    Scansiona TUTTE le fatture dei fornitori noleggio dal 2022 al 2026
    ed estrae tutti i verbali con associazioni complete.
    """
    from app.services.verbali_service import scansiona_e_salva_tutti_verbali
    
    try:
        risultato = await scansiona_e_salva_tutti_verbali()
        return {
            "success": True,
            "message": "Scansione completata",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore scansione verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verbali-completi")
@handle_errors
async def get_verbali_completi(
    anno: int = None,
    targa: str = None,
    stato_pagamento: str = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Restituisce i verbali con tutte le associazioni.
    
    Filtri opzionali:
    - anno: Anno del verbale
    - targa: Filtra per targa veicolo
    - stato_pagamento: da_verificare, pagato, sospeso
    """
    from app.services.verbali_service import COLLECTION_VERBALI
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = str(anno)
    if targa:
        query["targa"] = targa.upper()
    if stato_pagamento:
        query["stato_pagamento"] = stato_pagamento
    
    cursor = db[COLLECTION_VERBALI].find(query, {"_id": 0}).sort("data_fattura", -1).limit(limit)
    verbali = await cursor.to_list(limit)
    
    # Statistiche
    totale = await db[COLLECTION_VERBALI].count_documents(query if query else {})
    pagati = await db[COLLECTION_VERBALI].count_documents({"stato_pagamento": "pagato"})
    sospesi = await db[COLLECTION_VERBALI].count_documents({"stato_pagamento": "sospeso"})
    da_verificare = await db[COLLECTION_VERBALI].count_documents({"stato_pagamento": "da_verificare"})
    
    return {
        "verbali": verbali,
        "count": len(verbali),
        "totale": totale,
        "statistiche": {
            "pagati": pagati,
            "sospesi": sospesi,
            "da_verificare": da_verificare
        }
    }


@router.get("/operazioni-sospese")
@handle_errors
async def get_operazioni_sospese_endpoint() -> Dict[str, Any]:
    """
    Restituisce tutte le operazioni sospese (verbali non trovati nell'estratto conto).
    """
    from app.services.verbali_service import get_operazioni_sospese
    
    sospese = await get_operazioni_sospese()
    
    return {
        "operazioni": sospese,
        "count": len(sospese),
        "nota": "Queste operazioni non sono state trovate nell'estratto conto. Cerca manualmente nei documenti bancari."
    }


@router.post("/riconcilia")
@handle_errors
async def riconcilia_verbali_endpoint() -> Dict[str, Any]:
    """
    Tenta di riconciliare tutti i verbali con l'estratto conto.
    """
    from app.services.verbali_service import riconcilia_verbali
    
    try:
        risultato = await riconcilia_verbali()
        return {
            "success": True,
            "message": "Riconciliazione completata",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risolvi-sospeso")
@handle_errors
async def risolvi_sospeso_endpoint(
    riferimento: str,
    movimento_id: str
) -> Dict[str, Any]:
    """
    Risolve un'operazione sospesa associandola manualmente a un movimento bancario.
    """
    from app.services.verbali_service import risolvi_operazione_sospesa
    
    success = await risolvi_operazione_sospesa(riferimento, movimento_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Operazione sospesa non trovata")
    
    return {
        "success": True,
        "message": f"Operazione {riferimento} risolta e associata al movimento {movimento_id}"
    }


@router.get("/dettaglio/{numero_verbale}")
@handle_errors
async def get_dettaglio_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Restituisce il dettaglio completo di un verbale con tutti i documenti associati.
    """
    from app.services.verbali_service import COLLECTION_VERBALI
    db = Database.get_db()
    
    # Cerca nel nuovo sistema
    verbale = await db[COLLECTION_VERBALI].find_one(
        {"numero_verbale": numero_verbale},
        {"_id": 0}
    )
    
    if not verbale:
        # Cerca nel vecchio sistema
        verbale = await db["verbali_noleggio"].find_one(
            {"numero_verbale": numero_verbale},
            {"_id": 0}
        )
    
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    
    # Carica info aggiuntive
    risultato = {**verbale}
    
    # Carica info veicolo se presente
    if verbale.get("targa"):
        veicolo = await db["veicoli_noleggio"].find_one(
            {"targa": verbale["targa"]},
            {"_id": 0}
        )
        risultato["veicolo_info"] = veicolo
    
    # Carica fattura se presente
    if verbale.get("fattura_id"):
        fattura = await db["invoices"].find_one(
            {"id": verbale["fattura_id"]},
            {"_id": 0, "linee": 0}  # Escludi linee per non appesantire
        )
        risultato["fattura_info"] = fattura
    
    # Carica movimento bancario se riconciliato
    if verbale.get("movimento_banca_id"):
        movimento = await db["prima_nota_banca"].find_one(
            {"id": verbale["movimento_banca_id"]},
            {"_id": 0}
        )
        risultato["movimento_info"] = movimento
    
    # Carica PDF se disponibili
    pdf_list = verbale.get("pdf_allegati", [])
    if pdf_list:
        risultato["pdf_disponibili"] = [
            {"filename": p.get("filename"), "size": p.get("size"), "indice": i}
            for i, p in enumerate(pdf_list)
        ]
    
    return risultato



@router.get("/tutti-verbali")
@handle_errors
async def get_tutti_verbali(
    anno: int = None,
    include_senza_fattura: bool = True
) -> Dict[str, Any]:
    """
    Restituisce TUTTI i verbali da entrambe le collection:
    - verbali_noleggio_completi (estratti dalle fatture)
    - verbali_noleggio (scaricati dalla posta)
    
    Unifica i dati e identifica:
    - Verbali con fattura e PDF
    - Verbali con fattura ma senza PDF
    - Verbali con PDF ma senza fattura (da verificare)
    """
    db = Database.get_db()
    
    # 1. Prendi verbali estratti dalle fatture
    query_completi = {}
    if anno:
        query_completi["anno"] = str(anno)
    
    verbali_completi = await db["verbali_noleggio_completi"].find(query_completi, {"_id": 0}).to_list(1000)
    
    # 2. Prendi verbali scaricati dalla posta
    verbali_posta = await db["verbali_noleggio"].find({}, {"_id": 0}).to_list(1000)
    
    # Crea dizionario per lookup veloce
    posta_by_numero = {v.get("numero_verbale"): v for v in verbali_posta if v.get("numero_verbale")}
    completi_by_numero = {v.get("numero_verbale"): v for v in verbali_completi if v.get("numero_verbale")}
    
    # 3. Unifica
    risultato = {
        "con_fattura_e_pdf": [],
        "con_fattura_senza_pdf": [],
        "con_pdf_senza_fattura": [],
        "statistiche": {
            "totale_verbali_fattura": len(verbali_completi),
            "totale_verbali_posta": len(verbali_posta),
            "con_pdf": 0,
            "senza_pdf": 0,
            "importo_totale": 0
        }
    }
    
    # Processa verbali dalle fatture
    for v in verbali_completi:
        numero = v.get("numero_verbale")
        v_posta = posta_by_numero.get(numero)
        
        # Aggiungi PDF dalla posta se disponibile
        if v_posta and v_posta.get("pdf_allegati"):
            v["pdf_allegati"] = v_posta.get("pdf_allegati", [])
            v["pdf_downloaded"] = True
            risultato["con_fattura_e_pdf"].append(v)
            risultato["statistiche"]["con_pdf"] += 1
        else:
            risultato["con_fattura_senza_pdf"].append(v)
            risultato["statistiche"]["senza_pdf"] += 1
        
        risultato["statistiche"]["importo_totale"] += float(v.get("importo", 0))
    
    # Processa verbali dalla posta che NON sono nelle fatture
    if include_senza_fattura:
        for numero, v_posta in posta_by_numero.items():
            if numero not in completi_by_numero:
                risultato["con_pdf_senza_fattura"].append({
                    "numero_verbale": numero,
                    "pdf_allegati": v_posta.get("pdf_allegati", []),
                    "email_id": v_posta.get("email_id"),
                    "data_download": v_posta.get("data_download"),
                    "note": "Verbale scaricato dalla posta ma non presente nelle fatture"
                })
    
    return risultato


@router.post("/unifica-verbali")
@handle_errors
async def unifica_verbali() -> Dict[str, Any]:
    """
    Unifica i PDF scaricati dalla posta con i verbali estratti dalle fatture.
    Aggiorna verbali_noleggio_completi con i PDF da verbali_noleggio.
    """
    db = Database.get_db()
    
    # Prendi verbali con PDF dalla posta
    verbali_posta = await db["verbali_noleggio"].find(
        {"pdf_allegati": {"$exists": True, "$ne": []}}
    ).to_list(1000)
    
    aggiornati = 0
    non_trovati = []
    
    for v_posta in verbali_posta:
        numero = v_posta.get("numero_verbale")
        if not numero:
            continue
        


@router.post("/classifica-verbali-posta")
@handle_errors
async def classifica_verbali_posta_endpoint() -> Dict[str, Any]:
    """
    Classifica tutti i verbali scaricati dalla posta.
    
    Per ogni verbale determina se è:
    - AZIENDALE: targa presente nei veicoli gestiti → in attesa fattura
    - PRIVATO: targa non aziendale → archiviato separatamente
    - SCONOSCIUTO: nessuna targa trovata → da verificare manualmente
    """
    from app.services.verbali_classificazione import processa_verbali_posta
    
    try:
        risultato = await processa_verbali_posta()
        return {
            "success": True,
            "message": "Classificazione completata",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore classificazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verbali-attesa-fattura")
@handle_errors
async def get_verbali_attesa_endpoint() -> Dict[str, Any]:
    """
    Restituisce i verbali aziendali in attesa di fattura.
    
    Questi verbali sono stati ricevuti via email ma non ancora
    fatturati dal fornitore noleggio.
    """
    from app.services.verbali_classificazione import get_verbali_attesa
    
    verbali = await get_verbali_attesa()
    
    # Raggruppa per stato
    in_attesa = [v for v in verbali if v.get("stato") == "in_attesa_fattura"]
    da_verificare = [v for v in verbali if v.get("stato") == "da_verificare"]
    fatturati = [v for v in verbali if v.get("stato") == "fatturato"]
    
    return {
        "in_attesa_fattura": in_attesa,
        "da_verificare": da_verificare,
        "fatturati": fatturati,
        "totale": len(verbali),
        "statistiche": {
            "in_attesa": len(in_attesa),
            "da_verificare": len(da_verificare),
            "fatturati": len(fatturati)
        }
    }


@router.get("/verbali-privati")
@handle_errors
async def get_verbali_privati_endpoint() -> Dict[str, Any]:
    """
    Restituisce i verbali classificati come privati (non aziendali).
    
    Questi verbali hanno targhe non presenti nei veicoli gestiti.
    """
    from app.services.verbali_classificazione import get_verbali_privati
    
    verbali = await get_verbali_privati()
    
    return {
        "verbali": verbali,
        "totale": len(verbali),
        "nota": "Verbali con targhe non aziendali"
    }


@router.post("/verifica-nuove-fatture")
@handle_errors
async def verifica_nuove_fatture_endpoint() -> Dict[str, Any]:
    """
    Verifica se ci sono nuove fatture che matchano verbali in attesa.
    
    Da chiamare dopo ogni import di fatture per associare
    automaticamente i verbali alle fatture corrispondenti.
    """
    from app.services.verbali_classificazione import verifica_nuove_fatture_per_verbali
    
    try:
        risultato = await verifica_nuove_fatture_per_verbali()
        return {
            "success": True,
            "message": f"Trovate {risultato['nuove_associazioni']} nuove associazioni",
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore verifica fatture: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/riclassifica-verbale")
@handle_errors
async def riclassifica_verbale_endpoint(
    numero_verbale: str,
    classificazione: str,
    targa: str = None
) -> Dict[str, Any]:
    """
    Riclassifica manualmente un verbale.
    
    Args:
        numero_verbale: Numero del verbale da riclassificare
        classificazione: "aziendale" o "privato"
        targa: Targa da associare (opzionale)
    """
    from app.services.verbali_classificazione import riclassifica_verbale
    
    if classificazione not in ["aziendale", "privato"]:
        raise HTTPException(status_code=400, detail="Classificazione deve essere 'aziendale' o 'privato'")
    
    success = await riclassifica_verbale(numero_verbale, classificazione, targa)
    
    if not success:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    
    return {
        "success": True,
        "message": f"Verbale {numero_verbale} riclassificato come {classificazione}"
    }

