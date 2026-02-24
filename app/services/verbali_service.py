"""
Servizio Completo Gestione Verbali Noleggio Auto.

Questo modulo gestisce:
1. Estrazione verbali dalle fatture XML
2. Download documenti dalla posta
3. Associazione verbale ↔ auto ↔ dipendente ↔ contratto ↔ fattura ↔ pagamento
4. Riconciliazione con estratto conto
5. Gestione operazioni sospese
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.database import Database

logger = logging.getLogger(__name__)

# Collection MongoDB
COLLECTION_VERBALI = "verbali_noleggio_completi"
COLLECTION_SOSPESI = "operazioni_sospese"

# Pattern per numeri verbale
VERBALE_PATTERNS = [
    r'\b([A-Z]\d{10,12})\b',  # Es: A25111540620, B25121976344
    r'verbale\s*n[°.\s]*(\d+)',  # Es: verbale n. 12345
    r'n[°.\s]*verbale\s*(\d+)',
    r'sanzione\s*n[°.\s]*(\d+)',
    r'infrazione\s*n[°.\s]*(\d+)',
]

# Fornitori noleggio
FORNITORI_NOLEGGIO = {
    "01924961004": "ALD",
    "04911190488": "ARVAL",
    "06714021000": "Leasys",
    "02615080963": "LeasePlan"
}

# Pattern targa
TARGA_PATTERN = r'\b([A-Z]{2}\d{3}[A-Z]{2})\b'


def estrai_numero_verbale(descrizione: str) -> Optional[str]:
    """Estrae il numero del verbale dalla descrizione."""
    if not descrizione:
        return None
    
    for pattern in VERBALE_PATTERNS:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def estrai_data_verbale(descrizione: str) -> Optional[str]:
    """Estrae la data del verbale dalla descrizione."""
    # Pattern per date: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy
    date_patterns = [
        r'del\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})',
        r'data\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})',
        r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Normalizza a YYYY-MM-DD
            parts = re.split(r'[/.-]', date_str)
            if len(parts) == 3:
                day, month, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def estrai_targa(descrizione: str) -> Optional[str]:
    """Estrae la targa dalla descrizione."""
    match = re.search(TARGA_PATTERN, descrizione)
    return match.group(1) if match else None


async def scansiona_fatture_per_verbali(anno: Optional[int] = None) -> Dict[str, Any]:
    """
    Scansiona tutte le fatture dei fornitori noleggio per estrarre verbali.
    
    Returns:
        {
            "verbali_trovati": [...],
            "totale_fatture_analizzate": int,
            "totale_verbali": int,
            "per_anno": {...}
        }
    """
    db = Database.get_db()
    
    # Query per fatture fornitori noleggio
    query = {
        "supplier_vat": {"$in": list(FORNITORI_NOLEGGIO.keys())}
    }
    
    if anno:
        query["invoice_date"] = {"$regex": f"^{anno}"}
    
    cursor = db["invoices"].find(query)
    
    verbali_trovati = []
    fatture_analizzate = 0
    per_anno = {}
    
    async for fattura in cursor:
        fatture_analizzate += 1
        anno_fattura = fattura.get("invoice_date", "")[:4]
        
        if anno_fattura not in per_anno:
            per_anno[anno_fattura] = {"fatture": 0, "verbali": 0}
        per_anno[anno_fattura]["fatture"] += 1
        
        # Analizza linee fattura
        linee = fattura.get("linee", [])
        for linea in linee:
            desc = linea.get("descrizione", "") or linea.get("Descrizione", "")
            desc_lower = desc.lower()
            
            # Verifica se è una voce di verbale
            if any(kw in desc_lower for kw in ["verbale", "sanzione", "infrazione", "multa", "violazione"]):
                numero_verbale = estrai_numero_verbale(desc)
                if not numero_verbale:
                    # Prova a cercare in tutta la descrizione
                    for pattern in VERBALE_PATTERNS:
                        match = re.search(pattern, desc)
                        if match:
                            numero_verbale = match.group(1)
                            break
                
                targa = estrai_targa(desc)
                data_verbale = estrai_data_verbale(desc)
                
                # Estrai importo
                importo = float(linea.get("prezzo_totale") or linea.get("PrezzoTotale") or 
                               linea.get("prezzo_unitario") or linea.get("PrezzoUnitario") or 0)
                
                verbale = {
                    "numero_verbale": numero_verbale,
                    "targa": targa,
                    "data_verbale": data_verbale,
                    "importo": round(abs(importo), 2),
                    "descrizione": desc,
                    "fattura_id": str(fattura.get("_id", fattura.get("id"))),
                    "numero_fattura": fattura.get("invoice_number"),
                    "data_fattura": fattura.get("invoice_date"),
                    "fornitore": fattura.get("supplier_name"),
                    "fornitore_piva": fattura.get("supplier_vat"),
                    "anno": anno_fattura
                }
                
                verbali_trovati.append(verbale)
                per_anno[anno_fattura]["verbali"] += 1
    
    return {
        "verbali_trovati": verbali_trovati,
        "totale_fatture_analizzate": fatture_analizzate,
        "totale_verbali": len(verbali_trovati),
        "per_anno": per_anno
    }


async def salva_verbali_completi(verbali: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Salva i verbali nel database con tutte le associazioni.
    
    Returns:
        {"salvati": int, "duplicati": int, "errori": int}
    """
    db = Database.get_db()
    
    risultato = {"salvati": 0, "duplicati": 0, "errori": 0}
    
    for verbale in verbali:
        try:
            numero = verbale.get("numero_verbale")
            if not numero:
                # Genera un ID se non c'è numero verbale
                numero = f"UNKNOWN_{verbale.get('fattura_id', '')[:8]}_{uuid.uuid4().hex[:6]}"
            
            # Controlla se esiste già
            existing = await db[COLLECTION_VERBALI].find_one({"numero_verbale": numero})
            if existing:
                risultato["duplicati"] += 1
                continue
            
            # Cerca info veicolo
            veicolo_info = {}
            if verbale.get("targa"):
                veicolo = await db["veicoli_noleggio"].find_one({"targa": verbale["targa"]})
                if veicolo:
                    veicolo_info = {
                        "driver": veicolo.get("driver"),
                        "driver_id": veicolo.get("driver_id"),
                        "contratto": veicolo.get("contratto"),
                        "codice_cliente": veicolo.get("codice_cliente"),
                        "fornitore_noleggio": veicolo.get("fornitore_noleggio")
                    }
            
            # Crea record completo
            record = {
                "id": str(uuid.uuid4()),
                "numero_verbale": numero,
                "targa": verbale.get("targa"),
                "data_verbale": verbale.get("data_verbale"),
                "importo": verbale.get("importo", 0),
                "descrizione": verbale.get("descrizione"),
                
                # Associazioni fattura
                "fattura_id": verbale.get("fattura_id"),
                "numero_fattura": verbale.get("numero_fattura"),
                "data_fattura": verbale.get("data_fattura"),
                "fornitore": verbale.get("fornitore"),
                "fornitore_piva": verbale.get("fornitore_piva"),
                
                # Associazioni veicolo
                "driver": veicolo_info.get("driver"),
                "driver_id": veicolo_info.get("driver_id"),
                "contratto": veicolo_info.get("contratto"),
                "codice_cliente": veicolo_info.get("codice_cliente"),
                
                # PDF e documenti (da scaricare dalla posta)
                "pdf_url": None,
                "pdf_downloaded": False,
                "documenti_associati": [],
                
                # Stato pagamento
                "stato_pagamento": "da_verificare",  # da_verificare, pagato, sospeso
                "riconciliato": False,
                "movimento_banca_id": None,
                "movimento_carta_id": None,
                "data_pagamento": None,
                
                # Metadata
                "anno": verbale.get("anno"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLLECTION_VERBALI].insert_one(record)
            risultato["salvati"] += 1
            
        except Exception as e:
            logger.error(f"Errore salvataggio verbale: {e}")
            risultato["errori"] += 1
    
    return risultato


async def cerca_verbale_in_estratto_conto(numero_verbale: str, importo: float) -> Optional[Dict]:
    """
    Cerca un verbale nell'estratto conto (banca o carta).
    
    Returns:
        Movimento trovato o None
    """
    db = Database.get_db()
    
    # Cerca in prima_nota_banca
    movimento = await db["prima_nota_banca"].find_one({
        "$or": [
            {"causale": {"$regex": numero_verbale, "$options": "i"}},
            {"descrizione": {"$regex": numero_verbale, "$options": "i"}},
            {"riferimento": {"$regex": numero_verbale, "$options": "i"}}
        ]
    })
    
    if movimento:
        return {"tipo": "banca", "movimento": movimento}
    
    # Cerca per importo simile (tolleranza ±0.50€)
    tolleranza = 0.50
    movimento = await db["prima_nota_banca"].find_one({
        "importo": {"$gte": importo - tolleranza, "$lte": importo + tolleranza},
        "tipo": "uscita"
    })
    
    if movimento:
        return {"tipo": "banca", "movimento": movimento, "match_tipo": "importo"}
    
    return None


async def riconcilia_verbali() -> Dict[str, Any]:
    """
    Tenta di riconciliare tutti i verbali con l'estratto conto.
    
    Returns:
        {"riconciliati": int, "sospesi": int, "totale": int}
    """
    db = Database.get_db()
    
    risultato = {"riconciliati": 0, "sospesi": 0, "totale": 0}
    
    # Trova verbali non ancora riconciliati
    cursor = db[COLLECTION_VERBALI].find({
        "riconciliato": False,
        "stato_pagamento": {"$ne": "pagato"}
    })
    
    async for verbale in cursor:
        risultato["totale"] += 1
        
        numero = verbale.get("numero_verbale")
        importo = verbale.get("importo", 0)
        
        # Cerca nel conto
        match = await cerca_verbale_in_estratto_conto(numero, importo)
        
        if match:
            # Aggiorna verbale come riconciliato
            await db[COLLECTION_VERBALI].update_one(
                {"id": verbale["id"]},
                {"$set": {
                    "stato_pagamento": "pagato",
                    "riconciliato": True,
                    "movimento_banca_id": str(match["movimento"].get("_id", match["movimento"].get("id"))),
                    "data_pagamento": match["movimento"].get("data"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultato["riconciliati"] += 1
        else:
            # Marca come sospeso
            await db[COLLECTION_VERBALI].update_one(
                {"id": verbale["id"]},
                {"$set": {
                    "stato_pagamento": "sospeso",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Aggiungi a operazioni sospese
            await db[COLLECTION_SOSPESI].update_one(
                {"riferimento": numero},
                {"$set": {
                    "tipo": "verbale",
                    "riferimento": numero,
                    "importo": importo,
                    "descrizione": verbale.get("descrizione"),
                    "targa": verbale.get("targa"),
                    "verbale_id": verbale["id"],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            risultato["sospesi"] += 1
    
    return risultato


async def get_operazioni_sospese() -> List[Dict[str, Any]]:
    """Restituisce tutte le operazioni sospese (verbali non trovati nell'estratto)."""
    db = Database.get_db()
    
    cursor = db[COLLECTION_SOSPESI].find(
        {"risolto": {"$ne": True}},
        {"_id": 0}
    ).sort("created_at", -1)
    
    return await cursor.to_list(500)


async def risolvi_operazione_sospesa(riferimento: str, movimento_id: str) -> bool:
    """
    Risolve un'operazione sospesa associandola a un movimento bancario.
    
    Args:
        riferimento: Numero verbale o riferimento
        movimento_id: ID del movimento bancario trovato
    
    Returns:
        True se risolto con successo
    """
    db = Database.get_db()
    
    # Trova l'operazione sospesa
    sospeso = await db[COLLECTION_SOSPESI].find_one({"riferimento": riferimento})
    if not sospeso:
        return False
    
    # Aggiorna il verbale
    if sospeso.get("verbale_id"):
        await db[COLLECTION_VERBALI].update_one(
            {"id": sospeso["verbale_id"]},
            {"$set": {
                "stato_pagamento": "pagato",
                "riconciliato": True,
                "movimento_banca_id": movimento_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    # Marca come risolto
    await db[COLLECTION_SOSPESI].update_one(
        {"riferimento": riferimento},
        {"$set": {
            "risolto": True,
            "movimento_id": movimento_id,
            "risolto_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return True


async def scansiona_e_salva_tutti_verbali() -> Dict[str, Any]:
    """
    Funzione principale che scansiona TUTTE le fatture e salva i verbali.
    Da eseguire per la migrazione iniziale.
    """
    risultato_totale = {
        "anni_elaborati": [],
        "totale_fatture": 0,
        "totale_verbali_trovati": 0,
        "totale_verbali_salvati": 0,
        "duplicati": 0,
        "errori": 0
    }
    
    # Scansiona per ogni anno
    for anno in range(2022, 2027):
        logger.info(f"Scansione anno {anno}...")
        
        scan_result = await scansiona_fatture_per_verbali(anno)
        
        if scan_result["totale_verbali"] > 0:
            save_result = await salva_verbali_completi(scan_result["verbali_trovati"])
            
            risultato_totale["anni_elaborati"].append(anno)
            risultato_totale["totale_fatture"] += scan_result["totale_fatture_analizzate"]
            risultato_totale["totale_verbali_trovati"] += scan_result["totale_verbali"]
            risultato_totale["totale_verbali_salvati"] += save_result["salvati"]
            risultato_totale["duplicati"] += save_result["duplicati"]
            risultato_totale["errori"] += save_result["errori"]
    
    # Tenta riconciliazione
    riconc = await riconcilia_verbali()
    risultato_totale["riconciliazione"] = riconc
    
    return risultato_totale
