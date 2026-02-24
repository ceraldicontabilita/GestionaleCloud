"""
Validatori per il modulo Fornitori.
"""
from typing import Dict, Any, List

from .constants import CAMPI_OBBLIGATORI_P0, CAMPI_CONSIGLIATI


def clean_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove _id da un documento MongoDB per la serializzazione JSON."""
    if doc and "_id" in doc:
        del doc["_id"]
    return doc


def valida_fornitore(fornitore: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida un fornitore e restituisce i problemi trovati.
    
    Returns:
        {
            "valido": bool,
            "problemi_p0": [...],  # Problemi critici
            "problemi_p1": [...],  # Problemi secondari
            "completezza": float   # Percentuale completezza 0-100
        }
    """
    problemi_p0: List[str] = []
    problemi_p1: List[str] = []
    
    # Controllo campi obbligatori P0
    if not fornitore.get("partita_iva"):
        problemi_p0.append("Partita IVA mancante")
    
    denominazione = fornitore.get("denominazione") or fornitore.get("ragione_sociale") or ""
    if not denominazione:
        problemi_p0.append("Denominazione/Ragione Sociale mancante")
    
    if not fornitore.get("metodo_pagamento"):
        problemi_p0.append("Metodo di pagamento non impostato")
    
    # Per bonifico, serve IBAN
    if fornitore.get("metodo_pagamento") == "bonifico":
        if not fornitore.get("iban"):
            problemi_p0.append("IBAN mancante (richiesto per bonifico)")
    
    # Controllo campi consigliati P1
    if not fornitore.get("email") and not fornitore.get("pec"):
        problemi_p1.append("Email/PEC mancante")
    
    if not fornitore.get("telefono"):
        problemi_p1.append("Telefono mancante")
    
    if not fornitore.get("indirizzo"):
        problemi_p1.append("Indirizzo mancante")
    
    # Calcola completezza
    campi_totali = CAMPI_OBBLIGATORI_P0 + CAMPI_CONSIGLIATI
    campi_compilati = sum(1 for c in campi_totali if fornitore.get(c))
    completezza = round((campi_compilati / len(campi_totali)) * 100, 1)
    
    return {
        "valido": len(problemi_p0) == 0,
        "problemi_p0": problemi_p0,
        "problemi_p1": problemi_p1,
        "completezza": completezza
    }


def normalizza_piva(piva: str) -> str:
    """Normalizza una partita IVA rimuovendo spazi e caratteri speciali."""
    if not piva:
        return ""
    return "".join(c for c in piva if c.isalnum()).upper()


def valida_iban(iban: str) -> bool:
    """Valida formato base IBAN italiano."""
    if not iban:
        return False
    iban_clean = "".join(c for c in iban if c.isalnum()).upper()
    # IBAN italiano: IT + 2 check digits + 1 CIN + 5 ABI + 5 CAB + 12 conto
    return len(iban_clean) == 27 and iban_clean.startswith("IT")


def estrai_denominazione(fornitore: Dict[str, Any]) -> str:
    """Estrae la denominazione da un fornitore, cercando in vari campi."""
    return (
        fornitore.get("denominazione") or 
        fornitore.get("ragione_sociale") or
        fornitore.get("supplier_name") or
        fornitore.get("nome") or
        ""
    ).strip()
