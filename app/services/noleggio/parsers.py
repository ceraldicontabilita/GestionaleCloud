"""
Funzioni di parsing per il modulo Noleggio Auto.
Estrae informazioni da fatture XML: targhe, verbali, categorie spese, etc.
"""
import re
from typing import Optional, Tuple, Dict, Any

from .constants import (
    FORNITORI_NOLEGGIO,
    MARCA_PATTERNS
)


def estrai_codice_cliente(invoice: dict, fornitore: str = "") -> Optional[str]:
    """
    Estrae il codice cliente/contratto in base al fornitore.
    Ogni fornitore ha un formato diverso.
    """
    supplier_vat = invoice.get("supplier_vat", "")
    
    # ALD: Contratto nella descrizione linea (numero 7-8 cifre)
    if supplier_vat == FORNITORI_NOLEGGIO["ALD"]:
        for linea in invoice.get("linee", []):
            desc = linea.get("descrizione", "")
            # Pattern: 7-8 cifre seguite da data
            match = re.search(r'\s(\d{7,8})\s+\d{4}-\d{2}', desc)
            if match:
                return match.group(1)
        return None
    
    # ARVAL: Codice cliente nel campo causali
    elif supplier_vat == FORNITORI_NOLEGGIO["ARVAL"]:
        causali = invoice.get("causali", [])
        for c in causali:
            match = re.search(r'Codice Cliente[_\s]*(\w+)', str(c))
            if match:
                return match.group(1)
        return None
    
    # Leasys e LeasePlan: Non hanno codice cliente in fattura
    return None


def estrai_numero_verbale(descrizione: str) -> Optional[str]:
    """
    Estrae il numero del verbale dalla descrizione.
    Pattern: "Verbale Nr: XXXXX" o "Verbale N. XXXXX"
    Supporta sia pattern A... che B... (es. A25111540620, B23123049750)
    """
    # Pattern per ALD/Leasys: "Verbale Nr: B23123049750" o "Verbale Nr: A25111540620"
    match = re.search(r'Verbale\s+(?:Nr|N\.?|Num\.?)[\s:]*([A-Z0-9/\-]+)', descrizione, re.I)
    if match:
        return match.group(1).strip()
    
    # Pattern alternativo: cerca direttamente codice A/B seguito da 10-11 cifre
    match = re.search(r'\b([AB]\d{10,11})\b', descrizione)
    if match:
        return match.group(1)
    
    return None


def estrai_data_verbale(descrizione: str) -> Optional[str]:
    """
    Estrae la data del verbale dalla descrizione.
    Pattern: "Data Verbale: DD/MM/YY"
    """
    match = re.search(r'Data\s+Verbale[\s:]*(\d{2}/\d{2}/\d{2,4})', descrizione, re.I)
    if match:
        return match.group(1).strip()
    return None


def estrai_numero_verbale_completo(descrizione: str) -> Optional[str]:
    """
    Estrae il numero verbale completo da qualsiasi formato.
    Supporta:
    - "VERBALE NR 20250017442"
    - "verbale n. 12345"
    - "Verbale: 20250017442"
    """
    # Pattern per numero verbale lungo (Leasys style)
    match = re.search(r'verbale[\s:]*n[r.]?\s*(\d{8,12})', descrizione, re.I)
    if match:
        return match.group(1).strip()
    # Pattern alternativo
    match = re.search(r'n[r.]?\s*verbale[\s:]*(\d{8,12})', descrizione, re.I)
    if match:
        return match.group(1).strip()
    return None


def categorizza_spesa(descrizione: str, importo: float, is_nota_credito: bool = False) -> Tuple[str, float, Dict[str, Any]]:
    """
    Categorizza una spesa in base alla descrizione.
    Returns: (categoria, importo_con_segno, metadata)
    
    IMPORTANTE: L'ordine dei controlli è cruciale per evitare falsi positivi.
    
    Categorie:
    - verbali: Multe e sanzioni
    - riparazioni: Sinistri e danni
    - bollo: Tasse automobilistiche
    - pedaggio: Gestione pedaggi e telepass
    - costi_extra: Penalità varie
    - canoni: Locazione, servizi, conguagli (default)
    """
    desc_lower = descrizione.lower()
    importo_finale = abs(importo)
    metadata: Dict[str, Any] = {}
    
    # Se è nota credito, il segno è negativo
    if is_nota_credito or "nota credito" in desc_lower or "nota di credito" in desc_lower:
        importo_finale = -abs(importo)
    
    # STEP 1: VERBALI - Multe e sanzioni (alta priorità)
    verbali_keywords = [
        "verbale nr", "verbale n.", "verbale:", "multa", "sanzione", 
        "contravvenzione", "infrazione", "codice strada",
        "riaddebito verbale", "rifatturazione verbale"
    ]
    if any(kw in desc_lower for kw in verbali_keywords):
        num_verbale = estrai_numero_verbale(descrizione) or estrai_numero_verbale_completo(descrizione)
        data_verbale = estrai_data_verbale(descrizione)
        if num_verbale:
            metadata["numero_verbale"] = num_verbale
            metadata["descrizione_ricerca"] = f"Verbale {num_verbale}"
        if data_verbale:
            metadata["data_verbale"] = data_verbale
        return ("verbali", importo_finale, metadata)
    
    # STEP 2: RIPARAZIONI - Sinistri e danni
    riparazioni_keywords = [
        "sinistro", "rca passivo", "ard passivo", "danni al veicolo",
        "carrozzeria", "riparaz", "ripristino", "paraurti", "parafango", 
        "cofano", "portiera", "specchietto", "retrovisore", "fanale", 
        "faro", "parabrezza", "vetro", "ammortizzatore", "montante",
        "sedili", "rifatturazione 015", "danni"
    ]
    if any(kw in desc_lower for kw in riparazioni_keywords):
        return ("riparazioni", importo_finale, metadata)
    
    # STEP 3: BOLLO - Tasse automobilistiche
    bollo_keywords = [
        "bollo", "tassa automobilistic", "tasse auto", "tassa di propriet",
        "addebito bollo", "imposta provincial", "ipt", "superbollo",
        "rifatturazione (002) tasse",
        "riaddebito tassa automobilistic", "tassa regionale", "tassa automobilistica regionale"
    ]
    if any(kw in desc_lower for kw in bollo_keywords):
        # Escludi il bollo fiscale sulle fatture (€2)
        if "imposta di bollo" in desc_lower and importo <= 2.1:
            return ("canoni", importo_finale, metadata)
        metadata["descrizione_ricerca"] = "Bollo Auto"
        return ("bollo", importo_finale, metadata)
    
    # STEP 4: PEDAGGIO - Gestione pedaggi e telepass
    pedaggio_keywords = ["pedaggio", "telepass", "autostrad", "spese gestione multe", "rifatturazione 011"]
    if any(kw in desc_lower for kw in pedaggio_keywords):
        return ("pedaggio", importo_finale, metadata)
    
    # STEP 5: COSTI EXTRA - Penalità varie
    costi_extra_keywords = [
        "penale stato d'uso", "doppie chiavi", "penalità", "penale",
        "commissione", "mora", "ritardo", "rifatturazione 008"
    ]
    if any(kw in desc_lower for kw in costi_extra_keywords):
        if "sinistro" not in desc_lower:
            return ("costi_extra", importo_finale, metadata)
    
    # STEP 6: CANONI - Default per tutto il resto
    return ("canoni", importo_finale, metadata)


def estrai_modello_marca(descrizione: str, targa: str) -> Tuple[str, str]:
    """
    Estrae marca e modello dalla descrizione.
    Returns: (marca, modello)
    """
    marca = ""
    modello = ""
    
    for pattern, marca_nome in MARCA_PATTERNS:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            marca = marca_nome
            modello = match.group(1) if match.lastindex else match.group(0)
            modello = modello.strip()
            # Pulisci modello
            modello = re.sub(r'\s+', ' ', modello)
            if marca == "Mazda" and "MAZDA" in modello.upper():
                modello = modello.upper().replace("MAZDA ", "")
            break
    
    # Se non trovato con pattern specifici, estrai generico
    if not modello and targa:
        modello_match = re.search(
            rf'{targa}\s+(.+?)(?:\s+Canone|\s+Rifatturazione|\s+Serviz|\s+Locazione|\s*$)',
            descrizione, re.IGNORECASE
        )
        if modello_match:
            modello = modello_match.group(1).strip()
            modello = re.sub(r'\s+', ' ', modello)
    
    return (marca, modello.title() if modello else "")


def estrai_targa(descrizione: str) -> Optional[str]:
    """
    Estrae la targa italiana dalla descrizione.
    Formato: XX000XX (es. FY123AB)
    """
    from .constants import TARGA_PATTERN
    match = re.search(TARGA_PATTERN, descrizione)
    if match:
        return match.group(1)
    return None


def is_fattura_bollo(linee: list) -> bool:
    """
    Verifica se una fattura è relativa a bollo/tassa proprietà.
    """
    for linea in linee:
        desc = (linea.get("descrizione") or "").lower()
        if any(kw in desc for kw in ["tassa di propriet", "bollo", "addebito bollo", "tassa automobilistic"]):
            return True
    return False


def is_nota_credito(invoice: dict) -> bool:
    """
    Verifica se un documento è una Nota di Credito.
    """
    tipo_doc = invoice.get("tipo_documento", "").lower()
    return (
        "nota" in tipo_doc or 
        tipo_doc == "td04" or 
        invoice.get("total_amount", 0) < 0
    )
