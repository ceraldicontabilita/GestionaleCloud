"""
FIX: Migliore categorizzazione movimenti bancari
Aggiunge rilevamento automatico per stipendi, F24, fornitori, etc.

DA INTEGRARE IN: app/routers/bank/estratto_conto.py
Aggiungi questa funzione e usala durante l'import.
"""

import re
from typing import Optional, Tuple


def categorizza_movimento_bancario(descrizione: str, importo: float) -> Tuple[str, str, Optional[str]]:
    """
    Categorizza automaticamente un movimento bancario basandosi sulla descrizione.
    
    Args:
        descrizione: Descrizione del movimento
        importo: Importo (positivo = entrata, negativo = uscita)
    
    Returns:
        Tuple[categoria, sottocategoria, tipo_documento]
        tipo_documento: 'stipendio', 'f24', 'fattura', 'corrispettivo', None
    """
    if not descrizione:
        return ("Altro", "", None)
    
    desc_upper = descrizione.upper()
    
    # ========== STIPENDI E PERSONALE ==========
    stipendio_keywords = [
        "STIPEND", "STIP.", "SALARI", "CEDOLIN", "BUSTA PAGA",
        "COMPENSO", "EMOLUMENT", "RETRIBUZ",
        "ADD.TOT", "ADDEBITO TOTALE",  # Bonifici multipli stipendi
        "VS.DISP", "VOSTRA DISPOSIZIONE",  # Pattern BPM per bonifici
    ]
    
    # Verifica se è uno stipendio
    is_stipendio = False
    for kw in stipendio_keywords:
        if kw in desc_upper:
            is_stipendio = True
            break
    
    # Pattern specifico: "FAVORE Nome Cognome - ADD.TOT"
    if "FAVORE" in desc_upper and ("ADD.TOT" in desc_upper or "STIPENDIO" in desc_upper.lower()):
        is_stipendio = True
    
    if is_stipendio:
        return ("Risorse Umane - Salari e stipendi", "Stipendi dipendenti", "stipendio")
    
    # ========== F24 E TRIBUTI ==========
    f24_keywords = [
        "F24", "I24", "AGENZIA ENTRATE", "AGENZIA DELLE ENTRATE",
        "INPS", "INAIL", "IRPEF", "IRES", "IRAP", "IVA",
        "TRIBUT", "IMPOSTE", "TASSE", "RITENUTE",
        "MOD.F24", "DELEGA F24"
    ]
    
    for kw in f24_keywords:
        if kw in desc_upper:
            return ("Tributi e imposte", "F24", "f24")
    
    # ========== FORNITORI ==========
    fornitore_keywords = [
        "FATTUR", "FT.", "FATT.", "NOTPROVIDE", "SALDO FT",
        "PAGAMENTO FORN", "BONIFICO A FAVORE"
    ]
    
    for kw in fornitore_keywords:
        if kw in desc_upper:
            return ("Fornitori", "Pagamento fatture", "fattura")
    
    # ========== UTENZE ==========
    utenze_keywords = [
        "ENEL", "ENI", "A2A", "EDISON", "SORGENIA", "HERA",
        "TELECOM", "TIM", "VODAFONE", "WIND", "FASTWEB",
        "GAS", "LUCE", "ENERGIA", "ELETTRIC", "TELEFON",
        "ACQUEDOTTO", "TARI", "IMU"
    ]
    
    for kw in utenze_keywords:
        if kw in desc_upper:
            return ("Utenze", "Bollette", None)
    
    # ========== AFFITTI E LOCAZIONI ==========
    if any(kw in desc_upper for kw in ["AFFITTO", "CANONE", "LOCAZIONE", "FITTO"]):
        return ("Affitti e locazioni", "Canoni di locazione", None)
    
    # ========== ASSICURAZIONI ==========
    if any(kw in desc_upper for kw in ["ASSICURAZ", "POLIZZA", "GENERALI", "ALLIANZ", "UNIPOL", "AXA"]):
        return ("Assicurazioni", "Premi assicurativi", None)
    
    # ========== BANCA ==========
    if any(kw in desc_upper for kw in ["COMMISSIONI", "SPESE BANCARIE", "COMPETENZE", "BOLLO"]):
        return ("Spese bancarie", "Commissioni e spese", None)
    
    # ========== INCASSI ==========
    if importo > 0:
        if any(kw in desc_upper for kw in ["INCASSO", "BONIFICO DA", "ACCREDITO", "VERSAMENTO"]):
            return ("Incassi", "Bonifici in entrata", None)
        if any(kw in desc_upper for kw in ["POS", "BANCOMAT", "NEXI", "SIA"]):
            return ("Incassi", "Incassi POS", "corrispettivo")
    
    # ========== DEFAULT ==========
    if importo > 0:
        return ("Entrate varie", "", None)
    else:
        return ("Uscite varie", "", None)


def fix_categoria_movimento(movimento: dict) -> dict:
    """
    Corregge la categoria di un movimento esistente.
    Da usare per aggiornare movimenti già importati.
    """
    descrizione = movimento.get("descrizione_originale") or movimento.get("descrizione", "")
    importo = movimento.get("importo", 0)
    
    # Determina segno
    dare = movimento.get("dare", 0)
    avere = movimento.get("avere", 0)
    if dare > 0:
        importo = -dare  # Uscita
    elif avere > 0:
        importo = avere  # Entrata
    
    categoria, sottocategoria, tipo_doc = categorizza_movimento_bancario(descrizione, importo)
    
    movimento["categoria"] = categoria
    movimento["sottocategoria"] = sottocategoria
    if tipo_doc:
        movimento["tipo_documento_rilevato"] = tipo_doc
    
    return movimento


# Esempio di utilizzo nell'import:
"""
# Durante l'import CSV in estratto_conto.py, dopo aver letto i dati:

categoria, sottocategoria, tipo_doc = categorizza_movimento_bancario(
    descrizione_originale, 
    -dare if dare > 0 else avere
)

record = {
    "data": data,
    "descrizione_originale": descrizione_originale,
    "dare": dare,
    "avere": avere,
    "categoria": categoria,  # USA QUESTA invece di quella dal CSV
    "sottocategoria": sottocategoria,
    "tipo_documento_rilevato": tipo_doc,
    ...
}
"""
