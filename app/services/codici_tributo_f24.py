"""
Dizionario completo dei codici tributo F24
Fonte: Agenzia delle Entrate + INPS + Ricerca web 2025

LOGICA CORRETTA:
- Se importo è in colonna DEBITO → è un VERSAMENTO (si paga)
- Se importo è in colonna CREDITO → è una COMPENSAZIONE (si scala)
- Il saldo può essere:
  * + (positivo) = DEBITO da versare
  * - (negativo) = CREDITO che riduce il totale
"""
from typing import Dict, Any, List

CODICI_TRIBUTO_F24 = {
    # ==================== ERARIO - IRPEF ====================
    "1001": {
        "descrizione": "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive",
        "tipo": "misto",
        "sezione": "ERARIO",
        "scadenza": "16 del mese successivo"
    },
    "1002": {
        "descrizione": "Ritenute su emolumenti arretrati",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1012": {
        "descrizione": "Ritenute su indennità per cessazione di rapporto di lavoro",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1040": {
        "descrizione": "Ritenute su redditi di lavoro autonomo: compensi per l'esercizio di arti e professioni",
        "tipo": "misto",
        "sezione": "ERARIO",
        "scadenza": "16 del mese successivo"
    },
    "1627": {
        "descrizione": "Ritenute su lavoro autonomo, provvigioni, redditi diversi",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1631": {
        "descrizione": "Credito d'imposta per ritenute IRPEF",
        "tipo": "credito",
        "sezione": "ERARIO"
    },
    "1704": {
        "descrizione": "Credito IVA utilizzato in compensazione / Ritenute su redditi di capitale",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1713": {
        "descrizione": "Saldo imposte sostitutive su TFR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    "1714": {
        "descrizione": "Acconto imposte sostitutive su TFR",
        "tipo": "misto",
        "sezione": "ERARIO"
    },
    
    # ==================== ERARIO - IVA ====================
    "6001": {
        "descrizione": "IVA - Versamento mensile gennaio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 febbraio"
    },
    "6002": {
        "descrizione": "IVA - Versamento mensile febbraio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 marzo"
    },
    "6003": {
        "descrizione": "IVA - Versamento mensile marzo",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 aprile"
    },
    "6004": {
        "descrizione": "IVA - Versamento mensile aprile",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 maggio"
    },
    "6005": {
        "descrizione": "IVA - Versamento mensile maggio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 giugno"
    },
    "6006": {
        "descrizione": "IVA - Versamento mensile giugno",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 luglio"
    },
    "6007": {
        "descrizione": "IVA - Versamento mensile luglio",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 agosto"
    },
    "6008": {
        "descrizione": "IVA - Versamento mensile agosto",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 settembre"
    },
    "6009": {
        "descrizione": "IVA - Versamento mensile settembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 ottobre"
    },
    "6010": {
        "descrizione": "IVA - Versamento mensile ottobre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 novembre"
    },
    "6011": {
        "descrizione": "IVA - Versamento mensile novembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 dicembre"
    },
    "6012": {
        "descrizione": "IVA - Versamento mensile dicembre",
        "tipo": "debito",
        "sezione": "ERARIO",
        "scadenza": "16 gennaio anno successivo"
    },
    "6099": {
        "descrizione": "IVA - Versamento annuale",
        "tipo": "debito",
        "sezione": "ERARIO"
    },
    
    # ==================== INPS ====================
    "5100": {
        "descrizione": "Contributi previdenziali INPS lavoratori dipendenti",
        "tipo": "misto",
        "sezione": "INPS",
        "causali": ["DM10", "CXX", "M100"],
        "scadenza": "16 del mese successivo"
    },
    "RC01": {
        "descrizione": "Contributi INPS artigiani",
        "tipo": "debito",
        "sezione": "INPS"
    },
    "CP01": {
        "descrizione": "Contributi INPS commercianti",
        "tipo": "debito",
        "sezione": "INPS"
    },
    "PXX": {
        "descrizione": "Contributi INPS gestione separata",
        "tipo": "debito",
        "sezione": "INPS"
    },
    
    # ==================== REGIONI ====================
    "3800": {
        "descrizione": "Imposta regionale sulle attività produttive - saldo",
        "tipo": "misto",
        "sezione": "REGIONI"
    },
    "3801": {
        "descrizione": "Imposta regionale sulle attività produttive - acconto prima rata",
        "tipo": "debito",
        "sezione": "REGIONI"
    },
    "3802": {
        "descrizione": "Addizionale regionale IRPEF - sostituti d'imposta",
        "tipo": "misto",
        "sezione": "REGIONI",
        "scadenza": "16 del mese successivo"
    },
    "3796": {
        "descrizione": "Addizionale regionale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "REGIONI"
    },
    "3812": {
        "descrizione": "IRAP acconto seconda rata o unica soluzione",
        "tipo": "debito",
        "sezione": "REGIONI"
    },
    "3813": {
        "descrizione": "IRAP saldo",
        "tipo": "misto",
        "sezione": "REGIONI"
    },
    
    # ==================== IMU / TASI / ADDIZIONALE COMUNALE ====================
    "3847": {
        "descrizione": "Addizionale comunale IRPEF - acconto",
        "tipo": "misto",
        "sezione": "IMU",
        "scadenza": "16 del mese successivo"
    },
    "3848": {
        "descrizione": "Addizionale comunale IRPEF - saldo",
        "tipo": "misto",
        "sezione": "IMU",
        "scadenza": "16 del mese successivo"
    },
    "3797": {
        "descrizione": "Addizionale comunale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "IMU"
    },
    "3916": {
        "descrizione": "IMU - imposta municipale propria per fabbricati gruppo D - STATO",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3918": {
        "descrizione": "IMU - imposta municipale propria per altri fabbricati - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3914": {
        "descrizione": "IMU - imposta municipale propria per terreni - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3925": {
        "descrizione": "IMU - imposta municipale propria per immobili ad uso produttivo classificati D - STATO",
        "tipo": "debito",
        "sezione": "IMU"
    },
    "3930": {
        "descrizione": "IMU - imposta municipale propria per immobili ad uso produttivo classificati D - COMUNE",
        "tipo": "debito",
        "sezione": "IMU"
    },
    
    # ==================== INAIL ====================
    "8001": {
        "descrizione": "Regolarizzazione premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8002": {
        "descrizione": "Prima rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8003": {
        "descrizione": "Seconda rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
    "8004": {
        "descrizione": "Terza rata premio INAIL",
        "tipo": "debito",
        "sezione": "INAIL"
    },
}


def get_codice_info(codice: str) -> Dict[str, Any]:
    """
    Restituisce le informazioni complete di un codice tributo.
    
    Args:
        codice: Il codice tributo da cercare
        
    Returns:
        Dict con descrizione, tipo, sezione e altre info
    """
    return CODICI_TRIBUTO_F24.get(codice.upper(), {
        "descrizione": f"Codice tributo {codice}",
        "tipo": "unknown",
        "sezione": "UNKNOWN"
    })


def get_descrizione_tributo(codice: str) -> str:
    """
    Restituisce la descrizione di un codice tributo.
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Descrizione del codice tributo
    """
    info = get_codice_info(codice)
    return info.get("descrizione", f"Codice {codice}")


def get_tipo_tributo(codice: str) -> str:
    """
    Restituisce il tipo di un codice tributo (debito/credito/misto).
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Tipo del tributo
    """
    info = get_codice_info(codice)
    return info.get("tipo", "unknown")


def get_sezione_tributo(codice: str) -> str:
    """
    Restituisce la sezione F24 di un codice tributo.
    
    Args:
        codice: Il codice tributo
        
    Returns:
        Sezione F24 (ERARIO, INPS, REGIONI, IMU, INAIL)
    """
    info = get_codice_info(codice)
    return info.get("sezione", "UNKNOWN")


def get_codici_by_sezione(sezione: str) -> List[str]:
    """
    Restituisce tutti i codici tributo di una sezione.
    
    Args:
        sezione: Nome sezione (ERARIO, INPS, REGIONI, IMU, INAIL)
        
    Returns:
        Lista di codici tributo
    """
    return [
        codice for codice, info in CODICI_TRIBUTO_F24.items()
        if info.get("sezione", "").upper() == sezione.upper()
    ]


def cerca_codice_tributo(query: str) -> List[Dict[str, Any]]:
    """
    Cerca codici tributo per descrizione o codice.
    
    Args:
        query: Stringa di ricerca
        
    Returns:
        Lista di codici tributo che corrispondono
    """
    query_lower = query.lower()
    results = []
    
    for codice, info in CODICI_TRIBUTO_F24.items():
        if (query_lower in codice.lower() or 
            query_lower in info.get("descrizione", "").lower()):
            results.append({
                "codice": codice,
                **info
            })
    
    return results


def get_all_codici() -> List[Dict[str, Any]]:
    """
    Restituisce tutti i codici tributo.
    
    Returns:
        Lista di tutti i codici tributo con info
    """
    return [
        {"codice": codice, **info}
        for codice, info in CODICI_TRIBUTO_F24.items()
    ]
