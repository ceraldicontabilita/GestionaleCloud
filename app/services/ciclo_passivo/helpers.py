"""
Funzioni helper per il modulo Ciclo Passivo.
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .constants import CATEGORIE_CENTRO_COSTO, FORNITORI_COLLECTION

logger = logging.getLogger(__name__)


def estrai_codice_lotto(descrizione: str) -> Optional[str]:
    """Estrae codice lotto dalla descrizione."""
    if not descrizione:
        return None
    
    patterns = [
        r'LOTTO[:\s]+([A-Z0-9\-]+)',
        r'LOT[:\s]+([A-Z0-9\-]+)',
        r'N\.?\s*LOTTO[:\s]+([A-Z0-9\-]+)',
        r'BATCH[:\s]+([A-Z0-9\-]+)',
        r'\b(L\d{2}[A-Z]\d{3,})\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione.upper())
        if match:
            return match.group(1).strip()
    return None


def estrai_scadenza(descrizione: str) -> Optional[str]:
    """Estrae data scadenza dalla descrizione."""
    if not descrizione:
        return None
    
    patterns = [
        r'SCAD[A-Z]*[:\s]+(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})',
        r'EXP[A-Z]*[:\s]+(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione.upper())
        if match:
            try:
                data_str = match.group(1)
                parts = data_str.replace('-', '/').split('/')
                if len(parts) == 3:
                    if len(parts[2]) == 2:
                        parts[2] = '20' + parts[2]
                    return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            except (ValueError, IndexError):
                pass
    return None


def detect_centro_costo(fornitore: Dict, descrizione_linea: str = "") -> str:
    """Determina il centro di costo in base al fornitore e alla descrizione."""
    # Controlla categoria fornitore
    categoria = (fornitore.get("categoria") or "").lower()
    for key, centro in CATEGORIE_CENTRO_COSTO.items():
        if key in categoria:
            return centro
    
    # Controlla ragione sociale fornitore
    ragione_sociale = (fornitore.get("ragione_sociale") or fornitore.get("denominazione") or "").lower()
    keywords_food = ["alimentari", "food", "cibo", "macelleria", "pescheria", "ortofrutta", "salumi"]
    keywords_bev = ["bevande", "vino", "birra", "spirits", "acqua minerale"]
    keywords_util = ["enel", "eni", "edison", "a2a", "iren", "hera", "telecom", "vodafone", "tim", "fastweb"]
    
    for kw in keywords_food:
        if kw in ragione_sociale or kw in descrizione_linea.lower():
            return "FOOD"
    for kw in keywords_bev:
        if kw in ragione_sociale or kw in descrizione_linea.lower():
            return "BEVERAGE"
    for kw in keywords_util:
        if kw in ragione_sociale:
            return "UTILITIES"
    
    return "GENERAL"


async def get_or_create_fornitore(db, parsed_data: Dict) -> Dict[str, Any]:
    """Recupera o crea fornitore dal database."""
    fornitore_xml = parsed_data.get("fornitore", {})
    partita_iva = (fornitore_xml.get("partita_iva") or parsed_data.get("supplier_vat") or "").strip().upper()
    
    if not partita_iva:
        return {"id": None, "nuovo": False, "error": "P.IVA mancante"}
    
    existing = await db[FORNITORI_COLLECTION].find_one({"partita_iva": partita_iva}, {"_id": 0})
    
    if existing:
        return {**existing, "nuovo": False}
    
    # Crea nuovo fornitore
    nuovo = {
        "id": str(uuid.uuid4()),
        "partita_iva": partita_iva,
        "codice_fiscale": fornitore_xml.get("codice_fiscale", partita_iva),
        "ragione_sociale": fornitore_xml.get("denominazione") or parsed_data.get("supplier_name", ""),
        "denominazione": fornitore_xml.get("denominazione") or parsed_data.get("supplier_name", ""),
        "indirizzo": fornitore_xml.get("indirizzo", ""),
        "cap": fornitore_xml.get("cap", ""),
        "comune": fornitore_xml.get("comune", ""),
        "provincia": fornitore_xml.get("provincia", ""),
        "nazione": fornitore_xml.get("nazione", "IT"),
        "categoria": "",
        "attivo": True,
        "source": "import_xml_integrato",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[FORNITORI_COLLECTION].insert_one(nuovo.copy())
    logger.info(f"Nuovo fornitore creato: {nuovo['ragione_sociale']}")
    return {**nuovo, "nuovo": True}
