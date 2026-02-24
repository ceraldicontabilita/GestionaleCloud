"""
Database Codici Tributo F24
Elenco completo codici tributo fiscali e contributivi con scadenze
"""

# ============================================
# CODICI TRIBUTO FISCALI (ERARIO) - COMMERCIALISTA
# ============================================

CODICI_TRIBUTO_ERARIO = {
    # IRPEF - Ritenute lavoro dipendente
    "1001": {
        "descrizione": "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive",
        "categoria": "IRPEF",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    "1002": {
        "descrizione": "Ritenute su emolumenti arretrati",
        "categoria": "IRPEF",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    "1012": {
        "descrizione": "Ritenute su indennità per cessazione rapporto lavoro",
        "categoria": "IRPEF",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "occasionale"
    },
    
    # IRPEF - Ritenute lavoro autonomo
    "1040": {
        "descrizione": "Ritenute su redditi di lavoro autonomo",
        "categoria": "IRPEF",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    "1038": {
        "descrizione": "Ritenute su interessi e altri redditi di capitale",
        "categoria": "IRPEF",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    
    # IRPEF - Autotassazione (dichiarazione)
    "4001": {
        "descrizione": "IRPEF saldo",
        "categoria": "IRPEF",
        "tipo": "autotassazione",
        "scadenza": "30 giugno (o 31 luglio con maggiorazione 0.40%)",
        "periodicita": "annuale"
    },
    "4033": {
        "descrizione": "IRPEF acconto prima rata",
        "categoria": "IRPEF",
        "tipo": "autotassazione",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "4034": {
        "descrizione": "IRPEF acconto seconda rata o unica soluzione",
        "categoria": "IRPEF",
        "tipo": "autotassazione",
        "scadenza": "30 novembre",
        "periodicita": "annuale"
    },
    
    # IVA - Versamenti periodici
    "6001": {"descrizione": "IVA mensile - Gennaio", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 febbraio", "periodicita": "mensile"},
    "6002": {"descrizione": "IVA mensile - Febbraio", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 marzo", "periodicita": "mensile"},
    "6003": {"descrizione": "IVA mensile - Marzo", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 aprile", "periodicita": "mensile"},
    "6004": {"descrizione": "IVA mensile - Aprile", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 maggio", "periodicita": "mensile"},
    "6005": {"descrizione": "IVA mensile - Maggio", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 giugno", "periodicita": "mensile"},
    "6006": {"descrizione": "IVA mensile - Giugno", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 luglio", "periodicita": "mensile"},
    "6007": {"descrizione": "IVA mensile - Luglio", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 agosto (20 agosto)", "periodicita": "mensile"},
    "6008": {"descrizione": "IVA mensile - Agosto", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 settembre", "periodicita": "mensile"},
    "6009": {"descrizione": "IVA mensile - Settembre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 ottobre", "periodicita": "mensile"},
    "6010": {"descrizione": "IVA mensile - Ottobre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 novembre", "periodicita": "mensile"},
    "6011": {"descrizione": "IVA mensile - Novembre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 dicembre", "periodicita": "mensile"},
    "6012": {"descrizione": "IVA mensile - Dicembre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 gennaio anno successivo", "periodicita": "mensile"},
    "6013": {"descrizione": "IVA acconto", "categoria": "IVA", "tipo": "acconto", "scadenza": "27 dicembre", "periodicita": "annuale"},
    "6099": {"descrizione": "IVA annuale", "categoria": "IVA", "tipo": "saldo", "scadenza": "16 marzo", "periodicita": "annuale"},
    
    # IVA Trimestrale
    "6031": {"descrizione": "IVA I trimestre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 maggio", "periodicita": "trimestrale"},
    "6032": {"descrizione": "IVA II trimestre", "categoria": "IVA", "tipo": "periodico", "scadenza": "20 agosto", "periodicita": "trimestrale"},
    "6033": {"descrizione": "IVA III trimestre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 novembre", "periodicita": "trimestrale"},
    "6034": {"descrizione": "IVA IV trimestre", "categoria": "IVA", "tipo": "periodico", "scadenza": "16 febbraio anno successivo", "periodicita": "trimestrale"},
    
    # Addizionali IRPEF
    "3801": {
        "descrizione": "Addizionale regionale IRPEF - sostituto d'imposta",
        "categoria": "Addizionale",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    "3802": {
        "descrizione": "Addizionale regionale IRPEF",
        "categoria": "Addizionale",
        "tipo": "autotassazione",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "3843": {
        "descrizione": "Addizionale comunale IRPEF - acconto",
        "categoria": "Addizionale",
        "tipo": "autotassazione",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "3844": {
        "descrizione": "Addizionale comunale IRPEF - saldo",
        "categoria": "Addizionale",
        "tipo": "autotassazione",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    
    # Tributi locali addizionali (sostituto)
    "1671": {
        "descrizione": "Addizionale comunale IRPEF - sostituto d'imposta",
        "categoria": "Addizionale",
        "tipo": "ritenuta",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile"
    },
    
    # Crediti
    "1627": {
        "descrizione": "Eccedenze di versamenti di ritenute da lavoro dipendente",
        "categoria": "Credito",
        "tipo": "credito",
        "scadenza": "Compensazione",
        "periodicita": "variabile"
    },
    "1628": {
        "descrizione": "Eccedenze di versamenti di ritenute da lavoro autonomo",
        "categoria": "Credito",
        "tipo": "credito",
        "scadenza": "Compensazione",
        "periodicita": "variabile"
    },
    "1631": {
        "descrizione": "Credito d'imposta art. 3 DL 73/2021",
        "categoria": "Credito",
        "tipo": "credito",
        "scadenza": "Compensazione",
        "periodicita": "variabile"
    },
    
    # IRES
    "2001": {
        "descrizione": "IRES saldo",
        "categoria": "IRES",
        "tipo": "saldo",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "2002": {
        "descrizione": "IRES acconto prima rata",
        "categoria": "IRES",
        "tipo": "acconto",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "2003": {
        "descrizione": "IRES acconto seconda rata o unica soluzione",
        "categoria": "IRES",
        "tipo": "acconto",
        "scadenza": "30 novembre",
        "periodicita": "annuale"
    },
    # Nuovi codici 2025 Legge di Bilancio
    "2007": {
        "descrizione": "Maggior acconto I rata IRES - art. 1, c. 20, L. 207/2024",
        "categoria": "IRES",
        "tipo": "acconto",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "2008": {
        "descrizione": "Maggior acconto II rata o unica soluzione IRES - art. 1, c. 20, L. 207/2024",
        "categoria": "IRES",
        "tipo": "acconto",
        "scadenza": "30 novembre",
        "periodicita": "annuale"
    },
    
    # IRAP
    "3800": {
        "descrizione": "IRAP saldo",
        "categoria": "IRAP",
        "tipo": "saldo",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "3812": {
        "descrizione": "IRAP acconto prima rata",
        "categoria": "IRAP",
        "tipo": "acconto",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "3813": {
        "descrizione": "IRAP acconto seconda rata o unica soluzione",
        "categoria": "IRAP",
        "tipo": "acconto",
        "scadenza": "30 novembre",
        "periodicita": "annuale"
    },
    # Nuovi codici 2025 IRAP
    "3881": {
        "descrizione": "Maggior acconto I rata IRAP - art. 1, c. 20, L. 207/2024",
        "categoria": "IRAP",
        "tipo": "acconto",
        "scadenza": "30 giugno",
        "periodicita": "annuale"
    },
    "3882": {
        "descrizione": "Maggior acconto II rata o unica soluzione IRAP - art. 1, c. 20, L. 207/2024",
        "categoria": "IRAP",
        "tipo": "acconto",
        "scadenza": "30 novembre",
        "periodicita": "annuale"
    },
    
    # Ravvedimento operoso
    "8901": {"descrizione": "Sanzione pecuniaria IRPEF", "categoria": "Ravvedimento", "tipo": "sanzione", "scadenza": "Variabile", "periodicita": "ravvedimento"},
    "8902": {"descrizione": "Interessi sul ravvedimento IRPEF", "categoria": "Ravvedimento", "tipo": "interessi", "scadenza": "Variabile", "periodicita": "ravvedimento"},
    "8904": {"descrizione": "Sanzione pecuniaria IVA", "categoria": "Ravvedimento", "tipo": "sanzione", "scadenza": "Variabile", "periodicita": "ravvedimento"},
    "8906": {"descrizione": "Sanzione pecuniaria sostituti d'imposta", "categoria": "Ravvedimento", "tipo": "sanzione", "scadenza": "Variabile", "periodicita": "ravvedimento"},
    "8907": {"descrizione": "Interessi ravvedimento sostituti d'imposta", "categoria": "Ravvedimento", "tipo": "interessi", "scadenza": "Variabile", "periodicita": "ravvedimento"},
    
    # IMU
    "3914": {"descrizione": "IMU terreni", "categoria": "IMU", "tipo": "locale", "scadenza": "16 giugno (acconto), 16 dicembre (saldo)", "periodicita": "semestrale"},
    "3916": {"descrizione": "IMU aree fabbricabili", "categoria": "IMU", "tipo": "locale", "scadenza": "16 giugno (acconto), 16 dicembre (saldo)", "periodicita": "semestrale"},
    "3918": {"descrizione": "IMU altri fabbricati", "categoria": "IMU", "tipo": "locale", "scadenza": "16 giugno (acconto), 16 dicembre (saldo)", "periodicita": "semestrale"},
    "3925": {"descrizione": "IMU immobili gruppo D - Stato", "categoria": "IMU", "tipo": "locale", "scadenza": "16 giugno (acconto), 16 dicembre (saldo)", "periodicita": "semestrale"},
    "3930": {"descrizione": "IMU immobili gruppo D - Comune", "categoria": "IMU", "tipo": "locale", "scadenza": "16 giugno (acconto), 16 dicembre (saldo)", "periodicita": "semestrale"},
}


# ============================================
# CODICI TRIBUTO CONTRIBUTIVI (INPS/INAIL) - CONSULENTE LAVORO
# ============================================

CODICI_TRIBUTO_INPS = {
    "DM10": {
        "descrizione": "Contributi previdenziali dipendenti - Denuncia Mensile",
        "categoria": "INPS",
        "tipo": "contributi_dipendenti",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile",
        "note": "Versamento contributi dipendenti + quota datore lavoro"
    },
    "DMRA": {
        "descrizione": "Contributi arretrati dipendenti",
        "categoria": "INPS",
        "tipo": "contributi_dipendenti",
        "scadenza": "Variabile",
        "periodicita": "occasionale",
        "note": "Per regolarizzazioni e ravvedimenti"
    },
    "CXX": {
        "descrizione": "Contributi Gestione Separata - collaboratori senza altra copertura",
        "categoria": "INPS",
        "tipo": "gestione_separata",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile",
        "note": "Aliquota piena per co.co.co senza altra previdenza"
    },
    "C10": {
        "descrizione": "Contributi Gestione Separata - collaboratori con altra copertura",
        "categoria": "INPS",
        "tipo": "gestione_separata",
        "scadenza": "16 del mese successivo",
        "periodicita": "mensile",
        "note": "Aliquota ridotta per chi ha altra previdenza obbligatoria"
    },
    "RC01": {
        "descrizione": "Contributi artigiani/commercianti - rata trimestrale",
        "categoria": "INPS",
        "tipo": "artigiani_commercianti",
        "scadenza": "16 maggio, 20 agosto, 16 novembre, 16 febbraio",
        "periodicita": "trimestrale",
        "note": "Contributi fissi sul minimale"
    },
    "AF": {
        "descrizione": "Contributi artigiani - fissi",
        "categoria": "INPS",
        "tipo": "artigiani_commercianti",
        "scadenza": "Trimestrale",
        "periodicita": "trimestrale"
    },
    "CF": {
        "descrizione": "Contributi commercianti - fissi",
        "categoria": "INPS",
        "tipo": "artigiani_commercianti",
        "scadenza": "Trimestrale",
        "periodicita": "trimestrale"
    },
    "AP": {
        "descrizione": "Contributi artigiani - eccedenza minimale",
        "categoria": "INPS",
        "tipo": "artigiani_commercianti",
        "scadenza": "30 giugno / 30 novembre",
        "periodicita": "annuale"
    },
    "CP": {
        "descrizione": "Contributi commercianti - eccedenza minimale",
        "categoria": "INPS",
        "tipo": "artigiani_commercianti",
        "scadenza": "30 giugno / 30 novembre",
        "periodicita": "annuale"
    },
}

CODICI_TRIBUTO_INAIL = {
    "INAIL": {
        "descrizione": "Premio assicurazione INAIL",
        "categoria": "INAIL",
        "tipo": "premio",
        "scadenza": "16 febbraio (o rate: 16/02, 16/05, 16/08, 16/11)",
        "periodicita": "annuale/trimestrale",
        "note": "Autoliquidazione INAIL - può essere rateizzato"
    }
}


# ============================================
# SCADENZARIO MENSILE F24
# ============================================

SCADENZARIO_F24 = {
    "16": {
        "descrizione": "Scadenza ordinaria versamenti F24",
        "tributi": [
            "Ritenute IRPEF dipendenti e autonomi (1001, 1040)",
            "Addizionali regionali e comunali (3801, 1671)",
            "IVA mensile",
            "Contributi INPS dipendenti (DM10)",
            "Contributi Gestione Separata (CXX, C10)"
        ]
    },
    "20_agosto": {
        "descrizione": "Scadenza agosto (spostata dal 16)",
        "tributi": [
            "IVA II trimestre",
            "Tutti i versamenti normalmente al 16 agosto"
        ]
    },
    "27_dicembre": {
        "descrizione": "Acconto IVA",
        "tributi": ["IVA acconto (6013)"]
    },
    "30_giugno": {
        "descrizione": "Saldo e acconti dichiarativi",
        "tributi": [
            "IRPEF saldo e primo acconto",
            "IRAP saldo e primo acconto",
            "Addizionali saldo",
            "Diritto camerale"
        ]
    },
    "30_novembre": {
        "descrizione": "Secondo acconto",
        "tributi": [
            "IRPEF secondo acconto",
            "IRAP secondo acconto"
        ]
    }
}


# ============================================
# FUNZIONI DI UTILITÀ
# ============================================

def get_info_codice_tributo(codice: str) -> dict:
    """Restituisce le informazioni complete su un codice tributo."""
    # Cerca in tutte le categorie
    if codice in CODICI_TRIBUTO_ERARIO:
        info = CODICI_TRIBUTO_ERARIO[codice].copy()
        info["fonte"] = "commercialista"
        info["sezione_f24"] = "erario"
        return info
    
    if codice in CODICI_TRIBUTO_INPS:
        info = CODICI_TRIBUTO_INPS[codice].copy()
        info["fonte"] = "consulente_lavoro"
        info["sezione_f24"] = "inps"
        return info
    
    if codice in CODICI_TRIBUTO_INAIL:
        info = CODICI_TRIBUTO_INAIL[codice].copy()
        info["fonte"] = "consulente_lavoro"
        info["sezione_f24"] = "inail"
        return info
    
    return {
        "descrizione": f"Codice {codice} - Non in database",
        "categoria": "Sconosciuto",
        "tipo": "sconosciuto",
        "scadenza": "Verificare",
        "periodicita": "sconosciuta",
        "fonte": "sconosciuto",
        "sezione_f24": "sconosciuta"
    }


def is_codice_ravvedimento(codice: str) -> bool:
    """Verifica se un codice tributo è relativo a ravvedimento operoso."""
    codici_ravvedimento = ['8901', '8902', '8903', '8904', '8906', '8907', '8911', '8913', '8918', '8926', '8929']
    return codice in codici_ravvedimento


def get_codici_per_categoria(categoria: str) -> dict:
    """Restituisce tutti i codici di una categoria."""
    risultato = {}
    
    for codice, info in CODICI_TRIBUTO_ERARIO.items():
        if info.get("categoria", "").lower() == categoria.lower():
            risultato[codice] = info
    
    for codice, info in CODICI_TRIBUTO_INPS.items():
        if info.get("categoria", "").lower() == categoria.lower():
            risultato[codice] = info
    
    return risultato


def get_codici_per_fonte(fonte: str) -> dict:
    """
    Restituisce i codici in base alla fonte:
    - 'commercialista': codici fiscali (IRPEF, IVA, IRAP, etc.)
    - 'consulente_lavoro': codici contributivi (INPS, INAIL)
    """
    if fonte == "commercialista":
        return CODICI_TRIBUTO_ERARIO
    elif fonte == "consulente_lavoro":
        return {**CODICI_TRIBUTO_INPS, **CODICI_TRIBUTO_INAIL}
    else:
        return {}


def classifica_f24_per_mittente(email_mittente: str) -> str:
    """
    Classifica il tipo di F24 in base al mittente email.
    """
    email = email_mittente.lower()
    
    # Commercialista - F24 fiscali
    if "marotta" in email or "commercialista" in email:
        return "fiscale"
    
    # Consulente lavoro - F24 contributivi
    if "ferrantini" in email or "consulente" in email or "lavoro" in email:
        return "contributivo"
    
    return "generico"
