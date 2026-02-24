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

CODICI_TRIBUTO_F24 = {
    # ==================== ERARIO - IRPEF ====================
    "1001": {
        "descrizione": "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive",
        "tipo": "misto",
        "sezione": "ERARIO"
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
    
    # ==================== INPS ====================
    "5100": {
        "descrizione": "Contributi previdenziali INPS lavoratori dipendenti",
        "tipo": "misto",
        "sezione": "INPS",
        "causali": ["DM10", "CXX", "M100"]
    },
    
    # ==================== REGIONI ====================
    "3802": {
        "descrizione": "Addizionale regionale IRPEF - sostituti d'imposta",
        "tipo": "misto",
        "sezione": "REGIONI"
    },
    "3796": {
        "descrizione": "Addizionale regionale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "REGIONI"
    },
    
    # ==================== IMU ====================
    "3847": {
        "descrizione": "Addizionale comunale IRPEF - acconto",
        "tipo": "misto",
        "sezione": "IMU"
    },
    "3848": {
        "descrizione": "Addizionale comunale IRPEF - saldo",
        "tipo": "misto",
        "sezione": "IMU"
    },
    "3797": {
        "descrizione": "Addizionale comunale IRPEF rimborsata",
        "tipo": "credito",
        "sezione": "IMU"
    },
}

def get_codice_info(codice: str) -> dict:
    return CODICI_TRIBUTO_F24.get(codice.upper(), {
        "descrizione": f"Codice {codice}",
        "tipo": "unknown",
        "sezione": "UNKNOWN"
    })


def get_descrizione_tributo(codice: str) -> str:
    """
    Restituisce la descrizione di un codice tributo.
    Alias per compatibilità con vecchio codice.
    """
    info = get_codice_info(codice)
    return info.get("descrizione", f"Codice {codice}")
