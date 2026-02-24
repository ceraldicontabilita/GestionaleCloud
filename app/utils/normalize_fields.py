"""
Utility per la normalizzazione dei campi dei documenti.

Questo modulo gestisce la standardizzazione dei nomi dei campi
per garantire coerenza tra i vari moduli dell'applicazione.
"""

from typing import Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Converte un valore in float in modo sicuro.
    
    Args:
        value: Valore da convertire
        default: Valore di default se conversione fallisce
    
    Returns:
        float: Valore convertito o default
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Converte un valore in int in modo sicuro.
    
    Args:
        value: Valore da convertire
        default: Valore di default se conversione fallisce
    
    Returns:
        int: Valore convertito o default
    """
    if value is None:
        return default
    try:
        return int(float(value))  # float prima per gestire "10.0"
    except (ValueError, TypeError):
        return default


def normalize_invoice_fields(doc: dict) -> dict:
    """
    Normalizza i campi di una fattura per garantire coerenza.
    
    Gestisce le varianti comuni dei nomi dei campi:
    - Numero fattura: invoice_number, numero_documento, numero_fattura
    - P.IVA: supplier_vat, fornitore_partita_iva, partita_iva
    - Importo: total_amount, importo_totale, totale
    - Data: invoice_date, data_documento, data_fattura
    
    Args:
        doc: Documento fattura da normalizzare
    
    Returns:
        dict: Documento con campi normalizzati
    """
    if not doc:
        return {}
    
    # Estrai campi con fallback
    numero = (
        doc.get("numero_documento") or 
        doc.get("invoice_number") or 
        doc.get("numero_fattura") or 
        ""
    )
    
    partita_iva = (
        doc.get("fornitore_partita_iva") or 
        doc.get("supplier_vat") or 
        doc.get("partita_iva") or
        doc.get("vat_number") or
        ""
    )
    
    importo = safe_float(
        doc.get("importo_totale") or 
        doc.get("total_amount") or 
        doc.get("totale")
    )
    
    data = (
        doc.get("data_documento") or 
        doc.get("invoice_date") or 
        doc.get("data_fattura") or
        ""
    )
    
    # Campi da escludere (verranno sostituiti dai normalizzati)
    excluded_fields = {
        "invoice_number", "numero_fattura",
        "supplier_vat", "partita_iva", "vat_number",
        "total_amount", "totale",
        "invoice_date", "data_fattura"
    }
    
    # Costruisci documento normalizzato
    normalized = {
        "numero_documento": numero,
        "fornitore_partita_iva": partita_iva.upper().strip() if partita_iva else "",
        "importo_totale": importo,
        "data_documento": data,
    }
    
    # Aggiungi campi non normalizzati
    for key, value in doc.items():
        if key not in excluded_fields and key not in normalized:
            normalized[key] = value
    
    return normalized


def normalize_supplier_fields(doc: dict) -> dict:
    """
    Normalizza i campi di un fornitore.
    
    Args:
        doc: Documento fornitore da normalizzare
    
    Returns:
        dict: Documento con campi normalizzati
    """
    if not doc:
        return {}
    
    # Partita IVA
    partita_iva = (
        doc.get("partita_iva") or 
        doc.get("vat_number") or 
        doc.get("p_iva") or
        ""
    )
    
    # Ragione sociale
    ragione_sociale = (
        doc.get("ragione_sociale") or 
        doc.get("denominazione") or 
        doc.get("name") or
        doc.get("supplier_name") or
        ""
    )
    
    # Campi da escludere
    excluded_fields = {
        "vat_number", "p_iva",
        "denominazione", "name", "supplier_name"
    }
    
    normalized = {
        "partita_iva": partita_iva.upper().strip() if partita_iva else "",
        "ragione_sociale": ragione_sociale.strip() if ragione_sociale else "",
    }
    
    # Aggiungi campi non normalizzati
    for key, value in doc.items():
        if key not in excluded_fields and key not in normalized:
            normalized[key] = value
    
    return normalized


def normalize_date(date_value: Any) -> Optional[str]:
    """
    Normalizza una data in formato ISO (YYYY-MM-DD).
    
    Args:
        date_value: Data in vari formati possibili
    
    Returns:
        str: Data in formato YYYY-MM-DD o None
    """
    if not date_value:
        return None
    
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y-%m-%d")
    
    if isinstance(date_value, str):
        # Prova formati comuni
        formats = [
            "%Y-%m-%d",      # 2026-01-15
            "%d/%m/%Y",      # 15/01/2026
            "%d-%m-%Y",      # 15-01-2026
            "%Y/%m/%d",      # 2026/01/15
            "%d.%m.%Y",      # 15.01.2026
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_value.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # Se è già in formato ISO, restituisci così
        if len(date_value) >= 10 and date_value[4] == "-":
            return date_value[:10]
    
    return None


def normalize_amount(value: Any) -> float:
    """
    Normalizza un importo monetario.
    
    Gestisce:
    - Numeri con virgola italiana (1.234,56)
    - Numeri con punto decimale (1234.56)
    - Stringhe con simbolo valuta (€ 1.234,56)
    
    Args:
        value: Importo da normalizzare
    
    Returns:
        float: Importo normalizzato
    """
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        # Rimuovi simboli valuta e spazi
        cleaned = value.replace("€", "").replace("$", "").strip()
        
        # Gestisci formato italiano (1.234,56)
        if "," in cleaned and "." in cleaned:
            # Se virgola dopo punto, è formato italiano
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            # Altrimenti è formato USA (1,234.56)
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Solo virgola: potrebbe essere decimale italiano
            cleaned = cleaned.replace(",", ".")
        
        return safe_float(cleaned)
    
    return 0.0
