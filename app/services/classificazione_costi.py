"""
Classificazione Automatica Costi - Contabilità Italiana

Questo modulo implementa la classificazione automatica delle fatture ricevute
secondo le categorie del Conto Economico italiano (schema civilistico art. 2425 c.c.)
con le relative regole di deducibilità e detraibilità IVA.
"""

from typing import Dict, Any, List
import re

# ============================================================================
# CATEGORIE CONTO ECONOMICO (Schema Civilistico Art. 2425 c.c.)
# ============================================================================

CATEGORIE_CONTO_ECONOMICO = {
    # B) COSTI DELLA PRODUZIONE
    "B6_MATERIE_PRIME": {
        "codice": "B6",
        "nome": "Acquisti materie prime, sussidiarie e merci",
        "deducibilita": 1.0,  # 100%
        "detraibilita_iva": 1.0,  # 100%
        "note": "Deducibilità e detraibilità piena"
    },
    "B7_SERVIZI": {
        "codice": "B7",
        "nome": "Costi per servizi",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Categoria generica servizi"
    },
    "B7_CONSULENZE": {
        "codice": "B7a",
        "nome": "Consulenze professionali",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Commercialista, avvocato, consulenti"
    },
    "B7_UTENZE_ENERGIA": {
        "codice": "B7b",
        "nome": "Utenze - Energia elettrica e gas",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Deducibilità piena per uso aziendale"
    },
    "B7_UTENZE_ACQUA": {
        "codice": "B7c",
        "nome": "Utenze - Acqua",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Deducibilità piena"
    },
    "B7_TELEFONIA": {
        "codice": "B7d",
        "nome": "Spese telefoniche e internet",
        "deducibilita": 0.80,  # 80%
        "detraibilita_iva": 0.50,  # 50%
        "note": "Art. 102 TUIR - Deducibilità 80%, IVA 50%"
    },
    "B7_MANUTENZIONI": {
        "codice": "B7e",
        "nome": "Manutenzioni e riparazioni",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Limite 5% beni ammortizzabili"
    },
    "B7_ASSICURAZIONI": {
        "codice": "B7f",
        "nome": "Assicurazioni",
        "deducibilita": 1.0,
        "detraibilita_iva": 0.0,  # Esente IVA
        "note": "Esente IVA art. 10"
    },
    "B7_TRASPORTI": {
        "codice": "B7g",
        "nome": "Trasporti e spedizioni",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Deducibilità piena"
    },
    "B7_PUBBLICITA": {
        "codice": "B7h",
        "nome": "Pubblicità e promozione",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Deducibilità piena"
    },
    "B7_RAPPRESENTANZA": {
        "codice": "B7i",
        "nome": "Spese di rappresentanza",
        "deducibilita": 0.0,  # Limiti su ricavi
        "detraibilita_iva": 0.0,  # Indetraibile
        "note": "Limiti % su ricavi, IVA indetraibile",
        "limiti_ricavi": {
            "fino_10m": 0.015,  # 1.5% fino a 10M
            "10m_50m": 0.006,   # 0.6% da 10M a 50M
            "oltre_50m": 0.004  # 0.4% oltre 50M
        }
    },
    "B8_GODIMENTO_AFFITTI": {
        "codice": "B8a",
        "nome": "Affitti e locazioni immobili",
        "deducibilita": 1.0,
        "detraibilita_iva": 0.0,  # Spesso esente
        "note": "IVA spesso esente per immobili"
    },
    "B8_NOLEGGIO_AUTO": {
        "codice": "B8b",
        "nome": "Noleggio autovetture",
        "deducibilita": 0.20,  # 20% uso promiscuo
        "detraibilita_iva": 0.40,  # 40%
        "limite_annuo": 3615.20,  # €3.615,20 annui
        "note": "Art. 164 TUIR - Max €3.615,20/anno, 20% (70% se assegnata)",
        "deducibilita_assegnata": 0.70  # 70% se assegnata a dipendente
    },
    "B8_LEASING": {
        "codice": "B8c",
        "nome": "Canoni leasing",
        "deducibilita": 1.0,  # Varia per tipologia
        "detraibilita_iva": 1.0,
        "note": "Deducibilità in base a durata minima contratto"
    },
    "B9_PERSONALE_SALARI": {
        "codice": "B9a",
        "nome": "Salari e stipendi",
        "deducibilita": 1.0,
        "detraibilita_iva": None,  # No IVA
        "note": "Fuori campo IVA"
    },
    "B9_PERSONALE_ONERI": {
        "codice": "B9b",
        "nome": "Oneri sociali (INPS, INAIL)",
        "deducibilita": 1.0,
        "detraibilita_iva": None,
        "note": "Fuori campo IVA"
    },
    "B9_PERSONALE_TFR": {
        "codice": "B9c",
        "nome": "Trattamento fine rapporto",
        "deducibilita": 1.0,
        "detraibilita_iva": None,
        "note": "Fuori campo IVA"
    },
    "B10_AMMORTAMENTI": {
        "codice": "B10",
        "nome": "Ammortamenti e svalutazioni",
        "deducibilita": 1.0,  # Varia per categoria
        "detraibilita_iva": None,
        "note": "Quote ammortamento secondo coefficienti ministeriali"
    },
    "B14_ONERI_DIVERSI": {
        "codice": "B14",
        "nome": "Oneri diversi di gestione",
        "deducibilita": 1.0,
        "detraibilita_iva": 1.0,
        "note": "Categoria residuale"
    },
    
    # C) PROVENTI E ONERI FINANZIARI
    "C17_INTERESSI_PASSIVI": {
        "codice": "C17",
        "nome": "Interessi e oneri finanziari",
        "deducibilita": None,  # Limite ROL
        "detraibilita_iva": None,
        "note": "Limite ROL 30% - Art. 96 TUIR",
        "limite_rol": 0.30
    },
    "C17_INTERESSI_MUTUI": {
        "codice": "C17a",
        "nome": "Interessi passivi su mutui",
        "deducibilita": None,  # Limite ROL
        "detraibilita_iva": None,
        "note": "Soggetti a limite ROL"
    },
    "C17_COMMISSIONI_BANCARIE": {
        "codice": "C17b",
        "nome": "Commissioni e spese bancarie",
        "deducibilita": 1.0,
        "detraibilita_iva": 0.0,  # Esente
        "note": "Esente IVA art. 10"
    },
    
    # AUTO AZIENDALI - Regole specifiche
    "AUTO_CARBURANTE": {
        "codice": "B7_AUTO",
        "nome": "Carburante autovetture",
        "deducibilita": 0.20,  # 20%
        "detraibilita_iva": 0.40,  # 40%
        "note": "Art. 164 TUIR - 20% (70% se assegnata)",
        "deducibilita_assegnata": 0.70
    },
    "AUTO_MANUTENZIONE": {
        "codice": "B7_AUTO_MAN",
        "nome": "Manutenzione autovetture",
        "deducibilita": 0.20,
        "detraibilita_iva": 0.40,
        "note": "Stesse regole carburante"
    },
    "AUTO_ASSICURAZIONE": {
        "codice": "B7_AUTO_ASS",
        "nome": "Assicurazione autovetture",
        "deducibilita": 0.20,
        "detraibilita_iva": 0.0,  # Esente
        "note": "Esente IVA, deducibilità 20%"
    }
}

# ============================================================================
# PATTERN DI RICONOSCIMENTO FORNITORI
# ============================================================================

PATTERN_FORNITORI = {
    "B7_UTENZE_ENERGIA": [
        r"enel", r"eni\s", r"edison", r"a2a", r"sorgenia", r"hera", 
        r"iren", r"acea", r"energia", r"luce\s+e\s+gas", r"e\.on"
    ],
    "B7_UTENZE_ACQUA": [
        r"acqua", r"abc.*napoli", r"acquedotto", r"idric"
    ],
    "B7_TELEFONIA": [
        r"tim\s", r"telecom", r"vodafone", r"wind", r"tre\s", r"fastweb",
        r"iliad", r"tiscali", r"telefon"
    ],
    "B8_NOLEGGIO_AUTO": [
        r"arval", r"leasys", r"ald\s+automotive", r"alphabet", r"hertz",
        r"avis", r"europcar", r"noleggio", r"rent.*car", r"car.*rent"
    ],
    "AUTO_CARBURANTE": [
        r"esso", r"q8", r"tamoil", r"ip\s+", r"eni\s+station", r"total",
        r"shell", r"benzina", r"carburant", r"diesel", r"gasolio"
    ],
    "B7_ASSICURAZIONI": [
        r"generali", r"allianz", r"unipol", r"axa", r"zurich", r"reale\s+mutua",
        r"cattolica", r"assicuraz", r"insurance", r"broker"
    ],
    "C17_COMMISSIONI_BANCARIE": [
        r"banca", r"banco", r"unicredit", r"intesa", r"bnl", r"mps",
        r"credit.*agricole", r"deutsche", r"commissione", r"spese.*conto"
    ],
    "B7_CONSULENZE": [
        r"studio\s+(legale|commerc|notaio|tecnico)", r"avvocato", r"notaio",
        r"commercialista", r"consulen", r"advisor", r"revisore"
    ],
    "B7_MANUTENZIONI": [
        r"manutenzione", r"riparaz", r"service", r"assistenza\s+tecnica",
        r"impianti", r"elettricista", r"idraulico"
    ],
    "B7_TRASPORTI": [
        r"corriere", r"spediz", r"trasport", r"dhl", r"ups", r"fedex",
        r"brt", r"gls", r"poste\s+italian", r"sda"
    ],
    "B7_PUBBLICITA": [
        r"pubblicit", r"marketing", r"agenzia.*comunic", r"stampa", 
        r"tipograf", r"grafic", r"web.*agency", r"social\s+media"
    ],
    "B8_GODIMENTO_AFFITTI": [
        r"affitto", r"locazione", r"immobil", r"condominio", r"canone"
    ]
}


def classifica_fornitore(supplier_name: str, descrizione: str = "") -> str:
    """
    Classifica automaticamente un fornitore in base al nome.
    
    Args:
        supplier_name: Nome del fornitore
        descrizione: Descrizione aggiuntiva dalla fattura
        
    Returns:
        Codice categoria (es. "B7_UTENZE_ENERGIA")
    """
    if not supplier_name:
        return "B14_ONERI_DIVERSI"
    
    testo = f"{supplier_name} {descrizione}".lower()
    
    for categoria, patterns in PATTERN_FORNITORI.items():
        for pattern in patterns:
            if re.search(pattern, testo, re.IGNORECASE):
                return categoria
    
    # Default: merci se non riconosciuto
    return "B6_MATERIE_PRIME"


def calcola_deducibilita(categoria: str, importo: float, auto_assegnata: bool = False) -> Dict[str, Any]:
    """
    Calcola l'importo deducibile e l'IVA detraibile per una categoria.
    
    Args:
        categoria: Codice categoria
        importo: Importo totale (imponibile)
        auto_assegnata: Se True, usa percentuali per auto assegnata a dipendente
        
    Returns:
        Dict con importo_deducibile, iva_detraibile, percentuali
    """
    config = CATEGORIE_CONTO_ECONOMICO.get(categoria, CATEGORIE_CONTO_ECONOMICO["B14_ONERI_DIVERSI"])
    
    # Gestione auto aziendali
    if categoria in ["B8_NOLEGGIO_AUTO", "AUTO_CARBURANTE", "AUTO_MANUTENZIONE"]:
        deducibilita = config.get("deducibilita_assegnata", 0.70) if auto_assegnata else config["deducibilita"]
        
        # Limite annuo per noleggio
        if categoria == "B8_NOLEGGIO_AUTO":
            limite = config.get("limite_annuo", 3615.20)
            importo_limitato = min(importo, limite)
            importo_deducibile = importo_limitato * deducibilita
        else:
            importo_deducibile = importo * deducibilita
    else:
        deducibilita = config["deducibilita"] or 1.0
        importo_deducibile = importo * deducibilita
    
    # IVA detraibile
    detraibilita_iva = config.get("detraibilita_iva")
    if detraibilita_iva is not None:
        iva_detraibile_pct = detraibilita_iva
    else:
        iva_detraibile_pct = 0.0
    
    return {
        "categoria": categoria,
        "nome_categoria": config["nome"],
        "codice_bilancio": config["codice"],
        "importo_originale": round(importo, 2),
        "importo_deducibile": round(importo_deducibile, 2),
        "percentuale_deducibilita": deducibilita,
        "percentuale_detraibilita_iva": iva_detraibile_pct,
        "note": config.get("note", "")
    }


def get_voci_conto_economico() -> List[Dict[str, Any]]:
    """Restituisce tutte le voci del Conto Economico con le relative regole."""
    return [
        {
            "codice": v["codice"],
            "nome": v["nome"],
            "deducibilita": v["deducibilita"],
            "detraibilita_iva": v.get("detraibilita_iva"),
            "note": v.get("note", "")
        }
        for k, v in CATEGORIE_CONTO_ECONOMICO.items()
    ]
