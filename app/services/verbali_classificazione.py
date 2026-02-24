"""
Gestione Verbali dalla Posta - Classificazione Automatica

Questo modulo:
1. Legge i PDF dei verbali scaricati dalla posta
2. Estrae targa, data, importo usando OCR/regex
3. Classifica: aziendale vs privato
4. Mette in attesa fattura quelli aziendali
5. Associa automaticamente quando arriva la fattura
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.database import Database

logger = logging.getLogger(__name__)

# Collection per verbali non fatturati
COLLECTION_VERBALI_ATTESA = "verbali_attesa_fattura"
COLLECTION_VERBALI_PRIVATI = "verbali_privati"

# Pattern per estrazione dati da PDF
TARGA_PATTERN = r'\b([A-Z]{2}\s*\d{3}\s*[A-Z]{2})\b'
DATA_PATTERN = r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})'
IMPORTO_PATTERN = r'(?:€|EUR|euro)\s*([\d.,]+)|importo[:\s]*([\d.,]+)'
NUMERO_VERBALE_PATTERN = r'\b([A-Z]\d{10,12})\b|verbale\s*n[°.\s]*([A-Z0-9]+)'


def normalizza_targa(targa: str) -> str:
    """Normalizza targa rimuovendo spazi."""
    if not targa:
        return ""
    return re.sub(r'\s+', '', targa.upper())


def estrai_dati_da_testo(testo: str) -> Dict[str, Any]:
    """
    Estrae dati strutturati dal testo di un verbale.
    
    Returns:
        {
            "targhe": [...],
            "date": [...],
            "importi": [...],
            "numeri_verbale": [...]
        }
    """
    if not testo:
        return {"targhe": [], "date": [], "importi": [], "numeri_verbale": []}
    
    testo_upper = testo.upper()
    
    # Estrai targhe
    targhe = re.findall(TARGA_PATTERN, testo_upper)
    targhe = [normalizza_targa(t) for t in targhe]
    
    # Estrai date
    date = re.findall(DATA_PATTERN, testo)
    
    # Estrai importi
    importi_raw = re.findall(IMPORTO_PATTERN, testo, re.IGNORECASE)
    importi = []
    for match in importi_raw:
        for val in match:
            if val:
                # Converti formato italiano (1.234,56) in float
                val_clean = val.replace('.', '').replace(',', '.')
                try:
                    importi.append(float(val_clean))
                except:
                    pass
    
    # Estrai numeri verbale
    numeri = re.findall(NUMERO_VERBALE_PATTERN, testo_upper)
    numeri_verbale = []
    for match in numeri:
        for val in match:
            if val and len(val) > 5:
                numeri_verbale.append(val)
    
    return {
        "targhe": list(set(targhe)),
        "date": list(set(date)),
        "importi": list(set(importi)),
        "numeri_verbale": list(set(numeri_verbale))
    }


async def get_targhe_aziendali() -> set:
    """Restituisce l'elenco delle targhe dei veicoli aziendali."""
    db = Database.get_db()
    
    targhe = set()
    
    # Targhe dai veicoli salvati
    cursor = db["veicoli_noleggio"].find({}, {"targa": 1})
    async for v in cursor:
        if v.get("targa"):
            targhe.add(normalizza_targa(v["targa"]))
    
    # Targhe dai verbali già estratti dalle fatture (più veloce)
    cursor = db["verbali_noleggio_completi"].find({"targa": {"$ne": None}}, {"targa": 1})
    async for v in cursor:
        if v.get("targa"):
            targhe.add(normalizza_targa(v["targa"]))
    
    return targhe


async def classifica_verbale_posta(verbale: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classifica un verbale scaricato dalla posta.
    
    Determina se è:
    - Aziendale (targa nei veicoli gestiti)
    - Privato (targa non aziendale)
    - Sconosciuto (nessuna targa trovata)
    
    Returns:
        Verbale arricchito con classificazione
    """
    db = Database.get_db()
    
    # Prendi le targhe aziendali
    targhe_aziendali = await get_targhe_aziendali()
    
    # Estrai dati dal verbale (nome file, contenuto, etc.)
    numero = verbale.get("numero_verbale", "")
    pdf_allegati = verbale.get("pdf_allegati", [])
    
    # Cerca targa nei metadati o nel nome file
    targa_trovata = None
    dati_estratti = {"targhe": [], "date": [], "importi": [], "numeri_verbale": []}
    
    # Cerca nel nome della cartella/file
    for pdf in pdf_allegati:
        filename = pdf.get("filename", "")
        dati = estrai_dati_da_testo(filename)
        dati_estratti["targhe"].extend(dati["targhe"])
        dati_estratti["importi"].extend(dati["importi"])
    
    # Cerca nel numero verbale stesso
    dati = estrai_dati_da_testo(numero)
    dati_estratti["numeri_verbale"].extend(dati["numeri_verbale"])
    
    # Determina classificazione
    classificazione = "sconosciuto"
    targa_associata = None
    
    for targa in dati_estratti["targhe"]:
        targa_norm = normalizza_targa(targa)
        if targa_norm in targhe_aziendali:
            classificazione = "aziendale"
            targa_associata = targa_norm
            break
        else:
            # Targa trovata ma non aziendale
            classificazione = "privato"
            targa_associata = targa_norm
    
    # Se non ho trovato targa ma ho il numero verbale, cerco nelle fatture
    if classificazione == "sconosciuto" and numero:
        fattura = await db["invoices"].find_one({
            "linee.descrizione": {"$regex": numero, "$options": "i"}
        })
        if fattura:
            # Trovato in fattura - è aziendale
            classificazione = "aziendale"
            # Estrai targa dalla fattura
            for linea in fattura.get("linee", []):
                match = re.search(TARGA_PATTERN, linea.get("descrizione", "").upper())
                if match:
                    targa_associata = normalizza_targa(match.group(1))
                    break
    
    return {
        **verbale,
        "classificazione": classificazione,
        "targa_associata": targa_associata,
        "dati_estratti": dati_estratti,
        "classificato_at": datetime.now(timezone.utc).isoformat()
    }


async def processa_verbali_posta() -> Dict[str, Any]:
    """
    Processa tutti i verbali dalla posta e li classifica.
    
    Returns:
        Statistiche di classificazione
    """
    db = Database.get_db()
    
    risultato = {
        "totale_processati": 0,
        "aziendali": 0,
        "privati": 0,
        "sconosciuti": 0,
        "errori": 0
    }
    
    # Prendi tutti i verbali dalla posta
    verbali = await db["verbali_noleggio"].find({}).to_list(1000)
    
    for verbale in verbali:
        try:
            # Classifica
            classificato = await classifica_verbale_posta(verbale)
            risultato["totale_processati"] += 1
            
            classificazione = classificato.get("classificazione")
            
            if classificazione == "aziendale":
                # Salva in verbali_attesa_fattura
                record = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": classificato.get("numero_verbale"),
                    "targa": classificato.get("targa_associata"),
                    "pdf_allegati": classificato.get("pdf_allegati", []),
                    "dati_estratti": classificato.get("dati_estratti"),
                    "email_id": classificato.get("email_id"),
                    "stato": "in_attesa_fattura",
                    "fattura_associata": None,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLLECTION_VERBALI_ATTESA].update_one(
                    {"numero_verbale": record["numero_verbale"]},
                    {"$set": record},
                    upsert=True
                )
                risultato["aziendali"] += 1
                
            elif classificazione == "privato":
                # Salva in verbali_privati
                record = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": classificato.get("numero_verbale"),
                    "targa": classificato.get("targa_associata"),
                    "pdf_allegati": classificato.get("pdf_allegati", []),
                    "dati_estratti": classificato.get("dati_estratti"),
                    "note": "Verbale privato - targa non aziendale",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLLECTION_VERBALI_PRIVATI].update_one(
                    {"numero_verbale": record["numero_verbale"]},
                    {"$set": record},
                    upsert=True
                )
                risultato["privati"] += 1
                
            else:
                # Sconosciuto - metti comunque in attesa per verifica manuale
                record = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": classificato.get("numero_verbale"),
                    "targa": None,
                    "pdf_allegati": classificato.get("pdf_allegati", []),
                    "dati_estratti": classificato.get("dati_estratti"),
                    "stato": "da_verificare",
                    "note": "Targa non identificata - verifica manuale necessaria",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLLECTION_VERBALI_ATTESA].update_one(
                    {"numero_verbale": record["numero_verbale"]},
                    {"$set": record},
                    upsert=True
                )
                risultato["sconosciuti"] += 1
                
        except Exception as e:
            logger.error(f"Errore classificazione verbale: {e}")
            risultato["errori"] += 1
    
    logger.info(f"Classificazione completata: {risultato}")
    return risultato


async def cerca_e_associa_fattura(numero_verbale: str) -> Optional[Dict[str, Any]]:
    """
    Cerca una fattura che contiene il numero verbale e associa.
    
    Chiamare quando arriva una nuova fattura per verificare
    se ci sono verbali in attesa da associare.
    """
    db = Database.get_db()
    
    # Cerca verbale in attesa
    verbale = await db[COLLECTION_VERBALI_ATTESA].find_one({
        "numero_verbale": numero_verbale,
        "stato": "in_attesa_fattura"
    })
    
    if not verbale:
        return None
    
    # Cerca fattura
    fattura = await db["invoices"].find_one({
        "linee.descrizione": {"$regex": numero_verbale, "$options": "i"}
    })
    
    if not fattura:
        return None
    
    # Associa
    await db[COLLECTION_VERBALI_ATTESA].update_one(
        {"numero_verbale": numero_verbale},
        {"$set": {
            "stato": "fatturato",
            "fattura_associata": {
                "id": str(fattura.get("_id", fattura.get("id"))),
                "numero": fattura.get("invoice_number"),
                "data": fattura.get("invoice_date")
            },
            "associato_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Aggiorna anche verbali_noleggio_completi se esiste
    await db["verbali_noleggio_completi"].update_one(
        {"numero_verbale": numero_verbale},
        {"$set": {
            "pdf_allegati": verbale.get("pdf_allegati", []),
            "pdf_downloaded": True
        }}
    )
    
    return {
        "numero_verbale": numero_verbale,
        "fattura_numero": fattura.get("invoice_number"),
        "fattura_data": fattura.get("invoice_date")
    }


async def verifica_nuove_fatture_per_verbali() -> Dict[str, Any]:
    """
    Verifica se ci sono nuove fatture che matchano verbali in attesa.
    Da chiamare periodicamente o dopo import fatture.
    """
    db = Database.get_db()
    
    risultato = {
        "verbali_verificati": 0,
        "nuove_associazioni": 0,
        "associazioni": []
    }
    
    # Prendi verbali in attesa
    cursor = db[COLLECTION_VERBALI_ATTESA].find({"stato": "in_attesa_fattura"})
    
    async for verbale in cursor:
        risultato["verbali_verificati"] += 1
        numero = verbale.get("numero_verbale")
        
        associazione = await cerca_e_associa_fattura(numero)
        if associazione:
            risultato["nuove_associazioni"] += 1
            risultato["associazioni"].append(associazione)
    
    return risultato


async def get_verbali_attesa() -> List[Dict[str, Any]]:
    """Restituisce tutti i verbali in attesa di fattura."""
    db = Database.get_db()
    # Usa documenti_email con stato in_attesa_fattura
    cursor = db["documenti_email"].find(
        {"tipo_cartella": "verbale_noleggio", "stato": "in_attesa_fattura"},
        {"_id": 0, "allegati": 0, "content_base64": 0}
    ).sort("created_at", -1)
    return await cursor.to_list(500)


async def get_verbali_privati() -> List[Dict[str, Any]]:
    """Restituisce tutti i verbali classificati come privati."""
    db = Database.get_db()
    # Per ora non abbiamo classificazione privati - ritorna lista vuota
    cursor = db["documenti_email"].find(
        {"tipo_cartella": "verbale_noleggio", "stato": "privato"},
        {"_id": 0, "allegati": 0}
    ).sort("created_at", -1)
    return await cursor.to_list(500)


async def riclassifica_verbale(numero_verbale: str, nuova_classificazione: str, targa: str = None) -> bool:
    """
    Riclassifica manualmente un verbale.
    
    Args:
        numero_verbale: Numero del verbale
        nuova_classificazione: "aziendale" o "privato"
        targa: Targa da associare (opzionale)
    """
    db = Database.get_db()
    
    # Cerca il verbale
    verbale = await db[COLLECTION_VERBALI_ATTESA].find_one({"numero_verbale": numero_verbale})
    if not verbale:
        verbale = await db[COLLECTION_VERBALI_PRIVATI].find_one({"numero_verbale": numero_verbale})
    
    if not verbale:
        return False
    
    # Rimuovi dalla collection attuale
    await db[COLLECTION_VERBALI_ATTESA].delete_one({"numero_verbale": numero_verbale})
    await db[COLLECTION_VERBALI_PRIVATI].delete_one({"numero_verbale": numero_verbale})
    
    # Aggiungi alla nuova collection
    verbale["targa"] = targa or verbale.get("targa")
    verbale["classificazione"] = nuova_classificazione
    verbale["riclassificato_at"] = datetime.now(timezone.utc).isoformat()
    
    if nuova_classificazione == "aziendale":
        verbale["stato"] = "in_attesa_fattura"
        await db[COLLECTION_VERBALI_ATTESA].insert_one(verbale)
    else:
        await db[COLLECTION_VERBALI_PRIVATI].insert_one(verbale)
    
    return True
