"""
Gestione Magazzino Bar/Pasticceria - Categorie Merceologiche

Questo modulo implementa:
1. Categorizzazione automatica prodotti dalle linee fattura XML
2. Carico magazzino con estrazione quantità e unità di misura
3. Scarico per produzione (distinta base / ricette)
4. Gestione lotti e tracciabilità
"""

from typing import Dict, Any, List, Tuple
import re
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CATEGORIE MERCEOLOGICHE BAR/PASTICCERIA
# ============================================================================

CATEGORIE_MERCEOLOGICHE = {
    # === BEVANDE ===
    "CAFFE": {
        "codice": "BEV-CAF",
        "nome": "Caffè e derivati",
        "sottocategorie": ["grani", "macinato", "cialde", "capsule", "decaffeinato"],
        "unita_default": "KG",
        "centro_costo": "1.1_CAFFE_BEVANDE_CALDE",
        "keywords": ["caffè", "caffe", "coffee", "kimbo", "lavazza", "illy", "borbone", 
                    "arabica", "robusta", "espresso", "moka", "cialda", "capsula"]
    },
    "VINO_ROSSO": {
        "codice": "BEV-VRS",
        "nome": "Vini rossi",
        "sottocategorie": ["fermo", "frizzante"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["vino rosso", "rosso doc", "chianti", "barolo", "brunello", 
                    "montepulciano", "primitivo", "nero d'avola", "merlot", "cabernet"]
    },
    "VINO_BIANCO": {
        "codice": "BEV-VBI",
        "nome": "Vini bianchi",
        "sottocategorie": ["fermo", "frizzante"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["vino bianco", "bianco doc", "chardonnay", "pinot grigio", 
                    "vermentino", "greco", "falanghina", "fiano", "trebbiano"]
    },
    "SPUMANTE": {
        "codice": "BEV-SPU",
        "nome": "Spumanti e Prosecco",
        "sottocategorie": ["prosecco", "champagne", "cava", "franciacorta"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["spumante", "prosecco", "champagne", "franciacorta", 
                    "brut", "extra dry", "millesimato", "cava", "asti"]
    },
    "BIRRA": {
        "codice": "BEV-BIR",
        "nome": "Birre",
        "sottocategorie": ["industriale", "artigianale", "alla_spina", "analcolica"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["birra", "beer", "lager", "pilsner", "ale", "ipa", 
                    "peroni", "moretti", "heineken", "corona", "nastro azzurro"]
    },
    "LIQUORI": {
        "codice": "BEV-LIQ",
        "nome": "Liquori e distillati",
        "sottocategorie": ["amaro", "grappa", "whisky", "rum", "vodka", "gin", "cognac"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["amaro", "grappa", "whisky", "whiskey", "rum", "vodka", "gin",
                    "cognac", "brandy", "limoncello", "sambuca", "mirto", "montenegro",
                    "averna", "lucano", "jagermeister"]
    },
    "APERITIVI": {
        "codice": "BEV-APE",
        "nome": "Aperitivi",
        "sottocategorie": ["bitter", "vermouth", "ready_to_drink"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["aperol", "campari", "spritz", "vermouth", "martini", 
                    "cinzano", "bitter", "select", "cynar", "crodino"]
    },
    "BEVANDE_ANALCOLICHE": {
        "codice": "BEV-ANA",
        "nome": "Bevande analcoliche",
        "sottocategorie": ["acqua", "gassate", "succhi", "the", "energy"],
        "unita_default": "LT",
        "centro_costo": "1.2_BEVANDE_FREDDE_ALCOLICI",
        "keywords": ["acqua", "coca cola", "pepsi", "fanta", "sprite", "schweppes",
                    "aranciata", "chinotto", "limonata", "succo", "the freddo",
                    "red bull", "monster", "san pellegrino", "ferrarelle"]
    },
    
    # === MATERIE PRIME PASTICCERIA ===
    "FARINE": {
        "codice": "MP-FAR",
        "nome": "Farine e amidi",
        "sottocategorie": ["00", "0", "manitoba", "integrale", "amido"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["farina", "flour", "manitoba", "semola", "amido", "maizena",
                    "fecola", "frumento", "grano"]
    },
    "ZUCCHERI": {
        "codice": "MP-ZUC",
        "nome": "Zuccheri e dolcificanti",
        "sottocategorie": ["semolato", "a_velo", "canna", "miele", "sciroppi"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["zucchero", "sugar", "miele", "sciroppo", "glucosio",
                    "fruttosio", "destrosio", "zucchero a velo", "zucchero di canna"]
    },
    "UOVA": {
        "codice": "MP-UOV",
        "nome": "Uova e ovoprodotti",
        "sottocategorie": ["intere", "tuorli", "albumi", "pastorizzate"],
        "unita_default": "PZ",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["uova", "uovo", "eggs", "tuorlo", "albume", "ovoprodott"]
    },
    "LATTICINI": {
        "codice": "MP-LAT",
        "nome": "Latticini",
        "sottocategorie": ["burro", "panna", "latte", "mascarpone", "ricotta"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["burro", "butter", "panna", "cream", "latte", "milk",
                    "mascarpone", "ricotta", "yogurt", "philadelphia"]
    },
    "CACAO_CIOCCOLATO": {
        "codice": "MP-CAC",
        "nome": "Cacao e cioccolato",
        "sottocategorie": ["polvere", "fondente", "latte", "bianco", "gocce"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["cacao", "cioccolato", "chocolate", "fondente", "gianduia",
                    "praline", "copertura", "gocce cioccolato"]
    },
    "FRUTTA_SECCA": {
        "codice": "MP-FRS",
        "nome": "Frutta secca",
        "sottocategorie": ["mandorle", "nocciole", "pistacchi", "noci", "farina"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["mandorle", "nocciole", "pistacchio", "noci", "pinoli",
                    "anacardi", "arachidi", "pasta di mandorle", "granella"]
    },
    "LIEVITI_AROMI": {
        "codice": "MP-LIE",
        "nome": "Lieviti e aromi",
        "sottocategorie": ["lievito_birra", "chimico", "vaniglia", "estratti"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["lievito", "yeast", "vaniglia", "vanilla", "aroma", "estratto",
                    "bicarbonato", "cremor tartaro", "lievito madre"]
    },
    "FRUTTA_CONSERVATA": {
        "codice": "MP-FRC",
        "nome": "Frutta conservata",
        "sottocategorie": ["marmellata", "confettura", "canditi", "sciroppata"],
        "unita_default": "KG",
        "centro_costo": "1.3_MATERIE_PRIME_PASTICCERIA",
        "keywords": ["marmellata", "confettura", "canditi", "frutta sciroppata",
                    "uvetta", "albicocche secche", "datteri", "fichi secchi"]
    },
    
    # === SEMILAVORATI ===
    "BASI_PASTE": {
        "codice": "SL-BAS",
        "nome": "Basi e paste",
        "sottocategorie": ["frolla", "sfoglia", "brisee", "bigne"],
        "unita_default": "KG",
        "centro_costo": "1.4_PRODOTTI_SEMIFINITI",
        "keywords": ["pasta frolla", "pasta sfoglia", "brisée", "brisee",
                    "pasta bignè", "pan di spagna", "base torta"]
    },
    "CREME_FARCITURE": {
        "codice": "SL-CRE",
        "nome": "Creme e farciture",
        "sottocategorie": ["pasticcera", "chantilly", "ganache", "mousse"],
        "unita_default": "KG",
        "centro_costo": "1.4_PRODOTTI_SEMIFINITI",
        "keywords": ["crema pasticcera", "crema chantilly", "ganache", "mousse",
                    "crema al burro", "bavarese", "namelaka"]
    },
    "COPERTURE_GLASSE": {
        "codice": "SL-COP",
        "nome": "Coperture e glasse",
        "sottocategorie": ["glassa", "fondant", "gelatina"],
        "unita_default": "KG",
        "centro_costo": "1.4_PRODOTTI_SEMIFINITI",
        "keywords": ["glassa", "fondant", "ghiaccia reale", "gelatina",
                    "copertura a specchio", "glaze", "mirror"]
    },
    
    # === GELATI ===
    "GELATO_BASI": {
        "codice": "GEL-BAS",
        "nome": "Basi per gelato",
        "sottocategorie": ["latte", "frutta", "variegati"],
        "unita_default": "KG",
        "centro_costo": "1.5_GELATI_GRANITE",
        "keywords": ["base gelato", "neutro", "variegato", "topping",
                    "granella", "panna gelato"]
    },
    "GELATO_FINITO": {
        "codice": "GEL-FIN",
        "nome": "Gelato e sorbetti",
        "sottocategorie": ["cremosi", "sorbetti", "semifreddi"],
        "unita_default": "KG",
        "centro_costo": "1.5_GELATI_GRANITE",
        "keywords": ["gelato", "sorbetto", "granita", "semifreddo"]
    },
    
    # === PRODOTTI FINITI ACQUISTATI ===
    "SNACK_CONFEZIONATI": {
        "codice": "PF-SNK",
        "nome": "Snack confezionati",
        "sottocategorie": ["patatine", "crackers", "barrette"],
        "unita_default": "PZ",
        "centro_costo": "1.6_PRODOTTI_CONFEZIONATI",
        "keywords": ["patatine", "chips", "crackers", "snack", "taralli",
                    "grissini", "barretta", "san carlo", "pai"]
    },
    "DOLCIUMI_CONFEZIONATI": {
        "codice": "PF-DOL",
        "nome": "Dolciumi confezionati",
        "sottocategorie": ["caramelle", "cioccolatini", "biscotti"],
        "unita_default": "PZ",
        "centro_costo": "1.6_PRODOTTI_CONFEZIONATI",
        "keywords": ["caramelle", "cioccolatini", "biscotti", "wafer",
                    "chewing gum", "lecca lecca", "haribo", "kinder"]
    },
    
    # === IMBALLAGGI ===
    "IMBALLAGGI_CARTA": {
        "codice": "IMB-CAR",
        "nome": "Imballaggi carta",
        "sottocategorie": ["scatole", "sacchetti", "tovaglioli"],
        "unita_default": "PZ",
        "centro_costo": "13.1_IMBALLAGGI",
        "keywords": ["scatola", "sacchetto", "carta", "tovagliolo", "tovaglietta",
                    "carta forno", "carta stagnola", "pellicola"]
    },
    "IMBALLAGGI_PLASTICA": {
        "codice": "IMB-PLA",
        "nome": "Imballaggi plastica",
        "sottocategorie": ["vaschette", "coperchi", "contenitori"],
        "unita_default": "PZ",
        "centro_costo": "13.1_IMBALLAGGI",
        "keywords": ["vaschetta", "contenitore", "coperchio", "plastica",
                    "blister", "cestino", "vassoi"]
    },
    "MONOUSO": {
        "codice": "IMB-MUS",
        "nome": "Monouso",
        "sottocategorie": ["bicchieri", "piatti", "posate"],
        "unita_default": "PZ",
        "centro_costo": "13.1_IMBALLAGGI",
        "keywords": ["bicchiere carta", "piattino", "cucchiaino", "paletta",
                    "cannuccia", "agitatore", "coppetta gelato", "cono"]
    },
    
    # === FALLBACK ===
    "ALTRO": {
        "codice": "ALT-GEN",
        "nome": "Altri prodotti",
        "sottocategorie": [],
        "unita_default": "PZ",
        "centro_costo": "99_ALTRI_COSTI",
        "keywords": []
    }
}


# Pattern per estrazione quantità
PATTERN_QUANTITA = [
    # "10 KG", "10KG", "10 kg"
    (r'(\d+[.,]?\d*)\s*(kg|lt|l|pz|pezzi|cf|confezioni?|cartoni?|bt|bottiglie?|cl|ml|gr|g)\b', None),
    # "KG 10", "Kg. 10"
    (r'(kg|lt|l|pz|pezzi|cf|confezioni?|cartoni?|bt|bottiglie?|cl|ml|gr|g)[.\s]*(\d+[.,]?\d*)', 'reverse'),
    # "x 24", "X24", "x24 pz"
    (r'[xX]\s*(\d+)\s*(pz|pezzi)?', 'multiplier'),
]


def classifica_prodotto(descrizione: str, fornitore: str = "") -> Tuple[str, Dict[str, Any], float]:
    """
    Classifica un prodotto in base alla descrizione.
    
    Returns:
        Tuple[categoria_id, config_categoria, confidence]
    """
    if not descrizione:
        return "ALTRO", CATEGORIE_MERCEOLOGICHE["ALTRO"], 0.0
    
    testo = f"{descrizione} {fornitore}".lower()
    
    # Score per categoria
    scores = {}
    for cat_id, config in CATEGORIE_MERCEOLOGICHE.items():
        score = 0
        for keyword in config.get("keywords", []):
            if keyword.lower() in testo:
                score += len(keyword) * 2  # Peso per lunghezza keyword
        if score > 0:
            scores[cat_id] = score
    
    if scores:
        best_cat = max(scores, key=scores.get)
        confidence = min(scores[best_cat] / 30.0, 1.0)
        return best_cat, CATEGORIE_MERCEOLOGICHE[best_cat], confidence
    
    return "ALTRO", CATEGORIE_MERCEOLOGICHE["ALTRO"], 0.1


def estrai_quantita(descrizione: str) -> Tuple[float, str]:
    """
    Estrae quantità e unità di misura dalla descrizione.
    
    Returns:
        Tuple[quantita, unita_misura]
    """
    if not descrizione:
        return 1.0, "PZ"
    
    desc_lower = descrizione.lower()
    
    # Normalizza unità
    unita_map = {
        "kg": "KG", "kilo": "KG", "chilo": "KG",
        "lt": "LT", "l": "LT", "litro": "LT", "litri": "LT",
        "pz": "PZ", "pezzi": "PZ", "pezzo": "PZ",
        "cf": "CF", "conf": "CF", "confezione": "CF", "confezioni": "CF",
        "ct": "CT", "cartone": "CT", "cartoni": "CT",
        "bt": "BT", "bottiglia": "BT", "bottiglie": "BT",
        "cl": "CL", "ml": "ML",
        "gr": "GR", "g": "GR", "grammi": "GR"
    }
    
    for pattern, tipo in PATTERN_QUANTITA:
        match = re.search(pattern, desc_lower, re.IGNORECASE)
        if match:
            if tipo == "reverse":
                unita_raw = match.group(1)
                qta_str = match.group(2)
            elif tipo == "multiplier":
                return float(match.group(1)), "PZ"
            else:
                qta_str = match.group(1)
                unita_raw = match.group(2)
            
            qta = float(qta_str.replace(",", "."))
            unita = unita_map.get(unita_raw.lower(), "PZ")
            return qta, unita
    
    return 1.0, "PZ"


def parse_linea_fattura(linea: Dict[str, Any], fornitore: str = "") -> Dict[str, Any]:
    """
    Parsa una linea fattura XML ed estrae tutti i dati per il magazzino.
    
    Returns:
        Dict con dati prodotto classificato
    """
    descrizione = linea.get("descrizione", "") or linea.get("description", "")
    
    # Quantità e prezzo dalla linea
    qta_linea = float(linea.get("quantita", 1) or 1)
    unita_linea = linea.get("unita_misura", "PZ") or "PZ"
    prezzo_unitario = float(linea.get("prezzo_unitario", 0) or 0)
    prezzo_totale = float(linea.get("prezzo_totale", 0) or 0)
    aliquota_iva = float(linea.get("aliquota_iva", 22) or 22)
    
    # Estrai quantità aggiuntiva dalla descrizione (es. "x 24")
    qta_desc, unita_desc = estrai_quantita(descrizione)
    
    # Se l'unità dalla descrizione è diversa, potrebbe essere un moltiplicatore
    if qta_desc > 1 and unita_linea != unita_desc:
        # Es: 10 cartoni x 24 pezzi
        qta_totale = qta_linea * qta_desc
        unita_finale = unita_desc
    else:
        qta_totale = qta_linea
        unita_finale = unita_linea
    
    # Classifica prodotto
    categoria_id, categoria_config, confidence = classifica_prodotto(descrizione, fornitore)
    
    # Normalizza descrizione per codice prodotto
    desc_normalizzata = re.sub(r'[^a-zA-Z0-9\s]', '', descrizione)
    desc_normalizzata = " ".join(desc_normalizzata.split()[:5]).upper()
    
    return {
        "descrizione_originale": descrizione,
        "descrizione_normalizzata": desc_normalizzata,
        "quantita": qta_totale,
        "unita_misura": unita_finale,
        "prezzo_unitario": prezzo_unitario,
        "prezzo_totale": prezzo_totale,
        "aliquota_iva": aliquota_iva,
        "categoria_id": categoria_id,
        "categoria_codice": categoria_config["codice"],
        "categoria_nome": categoria_config["nome"],
        "centro_costo": categoria_config.get("centro_costo"),
        "classificazione_confidence": confidence,
        "fornitore": fornitore
    }


def calcola_scarico_ricetta(
    ingredienti_ricetta: List[Dict[str, Any]],
    porzioni_prodotte: int,
    porzioni_ricetta: int
) -> List[Dict[str, Any]]:
    """
    Calcola gli scarichi di magazzino per una produzione.
    
    Es: Ricetta per 10 porzioni, produciamo 100 sfogliatelle
    -> Moltiplica tutti gli ingredienti per 10
    
    Returns:
        Lista di scarichi da effettuare
    """
    fattore = porzioni_prodotte / porzioni_ricetta
    
    scarichi = []
    for ing in ingredienti_ricetta:
        # Gestisce quantità come stringa o numero
        qta_raw = ing.get("quantita", 0) or ing.get("quantita_originale", 0)
        try:
            qta_originale = float(qta_raw) if qta_raw else 0.0
        except (ValueError, TypeError):
            qta_originale = 0.0
        
        unita = ing.get("unita", "") or ing.get("unita_originale", "")
        
        scarichi.append({
            "ingrediente": ing.get("nome"),
            "quantita_ricetta": qta_originale,
            "quantita_scarico": qta_originale * fattore,
            "unita_misura": unita,
            "fattore_moltiplicazione": fattore
        })
    
    return scarichi


def get_tutte_categorie() -> List[Dict[str, Any]]:
    """Restituisce tutte le categorie merceologiche configurate."""
    return [
        {
            "id": cat_id,
            "codice": config["codice"],
            "nome": config["nome"],
            "sottocategorie": config.get("sottocategorie", []),
            "unita_default": config["unita_default"],
            "centro_costo": config.get("centro_costo")
        }
        for cat_id, config in CATEGORIE_MERCEOLOGICHE.items()
        if cat_id != "ALTRO"
    ]
