"""
Servizio Popolamento Automatico Tracciabilità HACCP

Quando viene caricata una fattura XML:
1. Estrae gli articoli alimentari dalle linee
2. Crea automaticamente record di tracciabilità
3. Collega fornitore, lotto, date, categoria HACCP
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging
import re

from app.database import Database

logger = logging.getLogger(__name__)


# Categorie alimentari che richiedono tracciabilità
CATEGORIE_ALIMENTARI_TRACCIABILI = {
    "carni_fresche", "pesce_fresco", "latticini", "uova",
    "frutta_verdura", "surgelati", "salumi_insaccati",
    "prodotti_forno"  # Solo freschi
}

# Mappatura rischio per categoria
RISCHIO_CATEGORIA = {
    "carni_fresche": "alto",
    "pesce_fresco": "alto",
    "latticini": "alto",
    "uova": "alto",
    "salumi_insaccati": "alto",
    "frutta_verdura": "medio",
    "surgelati": "medio",
    "prodotti_forno": "medio"
}

# Temperatura conservazione
TEMPERATURA_CATEGORIA = {
    "carni_fresche": "0-4°C",
    "pesce_fresco": "0-2°C",
    "latticini": "0-4°C",
    "uova": "4-8°C",
    "salumi_insaccati": "0-4°C",
    "frutta_verdura": "4-8°C",
    "surgelati": "≤-18°C",
    "prodotti_forno": "ambiente"
}


def estrai_lotto_da_descrizione(descrizione: str) -> Optional[str]:
    """Tenta di estrarre un numero di lotto dalla descrizione."""
    patterns = [
        r"lotto\s*[:\s]*([A-Z0-9\-]+)",
        r"lot[:\s]*([A-Z0-9\-]+)",
        r"L\s*\.?\s*([0-9]{6,})",
        r"batch[:\s]*([A-Z0-9\-]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def estrai_scadenza_da_descrizione(descrizione: str) -> Optional[str]:
    """Tenta di estrarre una data di scadenza dalla descrizione."""
    patterns = [
        r"scad[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{2,4})",
        r"exp[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{2,4})",
        r"(\d{2}[/\-]\d{2}[/\-]\d{4})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


async def get_categoria_articolo(db, descrizione: str) -> Dict[str, Any]:
    """
    Ottiene la categoria HACCP di un articolo dal dizionario.
    Se non esiste, lo categorizza con pattern matching base.
    """
    # Cerca nel dizionario
    articolo = await db.dizionario_articoli.find_one(
        {"descrizione": descrizione},
        {"categoria_haccp": 1, "conto": 1, "confidenza": 1, "_id": 0}
    )
    
    if articolo and articolo.get("confidenza", 0) > 0:
        return articolo
    
    # Fallback: pattern matching base
    desc_lower = descrizione.lower()
    
    # Pattern semplici per categorie principali
    if any(p in desc_lower for p in ["uova", "uovo", "cat.a", "gallina"]):
        return {"categoria_haccp": "uova", "conto": "05.01.05", "confidenza": 0.7}
    if any(p in desc_lower for p in ["latte", "mozzarella", "formaggio", "panna", "burro", "ricotta"]):
        return {"categoria_haccp": "latticini", "conto": "05.01.05", "confidenza": 0.7}
    if any(p in desc_lower for p in ["carne", "pollo", "manzo", "maiale", "vitello"]):
        return {"categoria_haccp": "carni_fresche", "conto": "05.01.05", "confidenza": 0.7}
    if any(p in desc_lower for p in ["prosciutto", "salame", "mortadella", "wurstel", "pancetta"]):
        return {"categoria_haccp": "salumi_insaccati", "conto": "05.01.05", "confidenza": 0.7}
    if any(p in desc_lower for p in ["pesce", "tonno", "salmone", "gamberi", "calamari"]):
        return {"categoria_haccp": "pesce_fresco", "conto": "05.01.05", "confidenza": 0.7}
    if any(p in desc_lower for p in ["surgelat", "congelat", "frozen"]):
        return {"categoria_haccp": "surgelati", "conto": "05.01.10", "confidenza": 0.7}
    if any(p in desc_lower for p in ["insalata", "pomodor", "verdur", "frutta", "mela", "arancia"]):
        return {"categoria_haccp": "frutta_verdura", "conto": "05.01.05", "confidenza": 0.6}
    if any(p in desc_lower for p in ["croissant", "cornetto", "brioche", "krapfen"]):
        return {"categoria_haccp": "prodotti_forno", "conto": "05.01.11", "confidenza": 0.7}
    
    # Default: non alimentare (non tracciabile)
    return {"categoria_haccp": "non_alimentare", "conto": "05.01.01", "confidenza": 0.3}


async def popola_tracciabilita_da_fattura(
    fattura: Dict[str, Any],
    linee: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Popola automaticamente la tracciabilità HACCP da una fattura importata.
    
    Args:
        fattura: Dati della fattura (deve contenere supplier_name, invoice_date, etc.)
        linee: Lista delle linee fattura (se None, usa fattura["linee"])
    
    Returns:
        Statistiche: articoli processati, tracciabilità create
    """
    db = Database.get_db()
    
    if linee is None:
        linee = fattura.get("linee", [])
    
    if not linee:
        return {"processed": 0, "created": 0, "skipped": 0}
    
    fornitore = fattura.get("supplier_name", "Fornitore Sconosciuto")
    fornitore_piva = fattura.get("supplier_vat", "")
    data_fattura = fattura.get("invoice_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    fattura_id = fattura.get("id", "")
    numero_fattura = fattura.get("invoice_number", "")
    
    created = 0
    skipped = 0
    
    for linea in linee:
        descrizione = linea.get("descrizione", "")
        if not descrizione:
            skipped += 1
            continue
        
        # Ottieni categoria
        cat_info = await get_categoria_articolo(db, descrizione)
        categoria = cat_info.get("categoria_haccp", "non_alimentare")
        
        # Salta se non è una categoria alimentare tracciabile
        if categoria not in CATEGORIE_ALIMENTARI_TRACCIABILI:
            skipped += 1
            continue
        
        # Estrai info aggiuntive dalla descrizione
        lotto = estrai_lotto_da_descrizione(descrizione)
        scadenza = estrai_scadenza_da_descrizione(descrizione)
        
        # Ottieni quantità
        quantita = linea.get("quantita", 1)
        try:
            quantita = float(str(quantita).replace(",", "."))
        except:
            quantita = 1.0
        
        unita_misura = linea.get("unita_misura", "PZ")
        
        # Crea record tracciabilità
        tracciabilita_record = {
            "id": str(uuid4()),
            "prodotto": descrizione[:100],  # Limita lunghezza
            "descrizione_completa": descrizione,
            "categoria_haccp": categoria,
            "rischio": RISCHIO_CATEGORIA.get(categoria, "basso"),
            "temperatura_conservazione": TEMPERATURA_CATEGORIA.get(categoria, "ambiente"),
            
            # Dati fornitore
            "fornitore": fornitore,
            "fornitore_piva": fornitore_piva,
            
            # Dati consegna
            "data_consegna": data_fattura,
            "data_fattura": data_fattura,
            "numero_fattura": numero_fattura,
            "fattura_id": fattura_id,
            
            # Quantità
            "quantita": quantita,
            "unita_misura": unita_misura,
            
            # Tracciabilità
            "lotto": lotto or f"AUTO-{data_fattura.replace('-', '')}",
            "scadenza": scadenza,
            
            # Controlli da compilare manualmente
            "temperatura_arrivo": None,
            "conforme": None,
            "note_conformita": None,
            
            # Metadata
            "source": "auto_fattura_xml",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "verificato": False
        }
        
        # Verifica duplicato (stesso prodotto, stesso lotto, stesso fornitore, stessa data)
        existing = await db.tracciabilita.find_one({
            "prodotto": tracciabilita_record["prodotto"],
            "fornitore": fornitore,
            "data_consegna": data_fattura,
            "lotto": tracciabilita_record["lotto"]
        })
        
        if existing:
            # Aggiorna quantità invece di duplicare
            await db.tracciabilita.update_one(
                {"id": existing["id"]},
                {"$inc": {"quantita": quantita}}
            )
            skipped += 1
            continue
        
        # Inserisci nuovo record
        await db.tracciabilita.insert_one(tracciabilita_record.copy())
        created += 1
    
    logger.info(f"Tracciabilità: {created} creati, {skipped} saltati da fattura {numero_fattura}")
    
    return {
        "processed": len(linee),
        "created": created,
        "skipped": skipped,
        "fornitore": fornitore,
        "data": data_fattura
    }


async def get_tracciabilita_per_categoria(categoria: str = None, data_da: str = None, data_a: str = None) -> List[Dict[str, Any]]:
    """
    Recupera i record di tracciabilità con filtri.
    """
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["categoria_haccp"] = categoria
    if data_da:
        query["data_consegna"] = {"$gte": data_da}
    if data_a:
        if "data_consegna" in query:
            query["data_consegna"]["$lte"] = data_a
        else:
            query["data_consegna"] = {"$lte": data_a}
    
    records = await db.tracciabilita.find(query, {"_id": 0}).sort("data_consegna", -1).to_list(500)
    return records
