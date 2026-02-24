"""
Servizio di Categorizzazione Contabile Intelligente

Analizza descrizioni prodotti e fornitori per:
1. Determinare la categoria merceologica
2. Mappare al conto corretto del Piano dei Conti
3. Calcolare la deducibilità fiscale (IRES/IRAP)
4. Gestire casi speciali (noleggi, manutenzioni, carburanti, ecc.)

Basato sulla normativa fiscale italiana vigente.
"""
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CategoriaFiscale(Enum):
    """Categorie fiscali per deducibilità"""
    MERCE_RIVENDITA = "merce_rivendita"  # 100% deducibile
    MATERIE_PRIME = "materie_prime"  # 100% deducibile
    SERVIZI = "servizi"  # 100% deducibile
    UTENZE = "utenze"  # 100% deducibile (se uso promiscuo: 50%)
    TELEFONIA = "telefonia"  # 80% deducibile
    CARBURANTE = "carburante"  # 100% se strumentale, 20% se auto promiscuo
    NOLEGGIO_BENI_STRUMENTALI = "noleggio_beni_strumentali"  # 100% deducibile
    NOLEGGIO_AUTO = "noleggio_auto"  # Limiti annui (es. €3.615,20)
    MANUTENZIONE_ORDINARIA = "manutenzione_ordinaria"  # 100% deducibile fino al 5% beni ammortizzabili
    MANUTENZIONE_STRAORDINARIA = "manutenzione_straordinaria"  # Ammortizzabile
    ASSICURAZIONI = "assicurazioni"  # 100% deducibile
    CONSULENZE_PROFESSIONALI = "consulenze"  # 100% deducibile + ritenuta
    PUBBLICITA = "pubblicita"  # 100% deducibile
    RAPPRESENTANZA = "rappresentanza"  # Limiti % sul fatturato
    ATTREZZATURE_MINORI = "attrezzature_minori"  # 100% se < €516,46
    BENI_STRUMENTALI = "beni_strumentali"  # Ammortizzabili
    LEASING = "leasing"  # Deducibile con limiti
    AFFITTO_LOCALI = "affitto"  # 100% deducibile
    INTERESSI_PASSIVI = "interessi"  # Deducibili con limiti ROL
    IMPOSTE_TASSE = "imposte"  # Alcune deducibili, altre no
    PERSONALE = "personale"  # 100% deducibile + contributi
    ALTRO = "altro"


@dataclass
class CategorizzazioneResult:
    """Risultato della categorizzazione di una fattura/linea"""
    categoria_merceologica: str
    conto_codice: str
    conto_nome: str
    categoria_fiscale: CategoriaFiscale
    percentuale_deducibilita_ires: float  # 0-100
    percentuale_deducibilita_irap: float  # 0-100
    note_fiscali: str
    confidenza: float  # 0-1


# ============== REGOLE DI CATEGORIZZAZIONE ==============

# Pattern per categoria merceologica basati su descrizione prodotto
PATTERNS_DESCRIZIONE = {
    # BEVANDE E ALCOLICI
    "bevande_alcoliche": {
        "patterns": [
            r"limoncello", r"amaro", r"grappa", r"vodka", r"rum", r"whisky",
            r"\bgin\b", r"cognac", r"brandy", r"liquore", r"aperitivo",
            r"vermut", r"vermouth", r"sambuca", r"nocino", r"digestivo",
            r"distillat", r"spirit", r"cocktail", r"tonic", r"%\s*vol",
            r"vino\b", r"birra", r"prosecco", r"champagne", r"spumante",
            r"falanghina", r"aglianico", r"fiano", r"greco\s+di\s+tufo",
            r"verdicchio", r"gewurztraminer", r"pecorino\s+igt",
            r"valp?olicella", r"ripasso", r"docg?\b", r"igt\b",
            r"millesimato", r"extra\s+brut", r"extra\s+dry"
        ],
        "conto": ("05.01.03", "Acquisto bevande alcoliche"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Merce destinata alla rivendita"
    },
    
    # BEVANDE NON ALCOLICHE
    "bevande_analcoliche": {
        "patterns": [
            r"acqua\s+(minerale|naturale|frizzante|tonica)", r"succo",
            r"aranciata", r"cola", r"the\s+freddo", r"energy\s+drink",
            r"limonata", r"gassosa", r"bibita", r"bevanda",
            r"red\s*bull", r"monster\s+energy"
        ],
        "conto": ("05.01.04", "Acquisto bevande analcoliche"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Merce destinata alla rivendita"
    },
    
    # PRODOTTI ALIMENTARI
    "alimentari": {
        "patterns": [
            r"pasta\b", r"riso\b", r"farina", r"pane\b", r"pizza",
            r"formaggio", r"mozzarella", r"prosciutto", r"salame",
            r"carne\b", r"pesce\b", r"verdur", r"frutta",
            r"zucchero", r"sale\b", r"latte\b", r"burro",
            r"uova?\b", r"tarall", r"alimentar", r"food", r"cibo", 
            r"snack", r"patatine", r"rosette\b", r"panin",
            r"olio\s+(extravergine|d[ie]\s*oliva|d[ie]\s*semi)"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Merce destinata alla rivendita"
    },
    
    # UTENZE - ACQUA
    "utenze_acqua": {
        "patterns": [
            r"fornitura\s+\d+", r"consumo\s+(idrico|acqua)",
            r"acquedotto", r"servizio\s+idrico", r"acque\s+s\.?p\.?a",
            r"acqua\s+bene\s+comune", r"abc\s*-?\s*acqua"
        ],
        "conto": ("05.02.04", "Utenze - Acqua"),
        "categoria_fiscale": CategoriaFiscale.UTENZE,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Utenza acqua - 100% deducibile se uso esclusivo aziendale"
    },
    
    # UTENZE - ENERGIA ELETTRICA
    "utenze_elettricita": {
        "patterns": [
            r"energia\s+elettrica", r"luce\b", r"enel\b", r"edison\b",
            r"a2a\b", r"iren\b", r"hera\b", r"sorgenia", r"eni\s+gas.*luce",
            r"consumo\s+(elettrico|energia)", r"kwh", r"potenza\s+impegnata"
        ],
        "conto": ("05.02.05", "Utenze - Energia elettrica"),
        "categoria_fiscale": CategoriaFiscale.UTENZE,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Utenza elettrica - 100% deducibile se uso esclusivo aziendale"
    },
    
    # UTENZE - GAS
    "utenze_gas": {
        "patterns": [
            r"gas\s+(naturale|metano)", r"eni\s+gas", r"italgas",
            r"smc\b", r"consumo\s+gas", r"riscaldamento\s+gas",
            r"metano\b"
        ],
        "conto": ("05.02.06", "Utenze - Gas"),
        "categoria_fiscale": CategoriaFiscale.UTENZE,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Utenza gas - 100% deducibile se uso esclusivo aziendale"
    },
    
    # TELEFONIA E INTERNET
    "telefonia": {
        "patterns": [
            r"tim\b", r"vodafone", r"wind\b", r"fastweb", r"telecom",
            r"telefon", r"mobile", r"sim\b", r"roaming", r"adsl",
            r"fibra\b", r"internet", r"connettivit", r"dati\s+mobili",
            r"voip\b", r"centralino", r"wi-?fi"
        ],
        "conto": ("05.02.07", "Telefonia e comunicazioni"),
        "categoria_fiscale": CategoriaFiscale.TELEFONIA,
        "deducibilita_ires": 80,
        "deducibilita_irap": 80,
        "note": "Telefonia - deducibile 80% ai fini IRES (art. 102 TUIR)"
    },
    
    # CLOUD E SOFTWARE
    "software_cloud": {
        "patterns": [
            r"google\s+(cloud|workspace|drive)", r"microsoft\s+365",
            r"office\s+365", r"amazon\s+aws", r"azure\b",
            r"software", r"licenza", r"abbonamento\s+digital",
            r"saas\b", r"hosting", r"dominio\b", r"server\b"
        ],
        "conto": ("05.02.08", "Software e servizi cloud"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Servizi digitali - 100% deducibile"
    },
    
    # NOLEGGI BENI STRUMENTALI
    "noleggio_attrezzature": {
        "patterns": [
            r"noleggio\s+(?!auto|veicol)", r"rental", r"locazione\s+operativa",
            r"affitto\s+attrezzatur"
        ],
        "conto": ("05.02.09", "Noleggi e locazioni operative"),
        "categoria_fiscale": CategoriaFiscale.NOLEGGIO_BENI_STRUMENTALI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Noleggio beni strumentali - 100% deducibile"
    },
    
    # MANUTENZIONI E RIPARAZIONI
    "manutenzione": {
        "patterns": [
            r"manutenz", r"riparaz", r"assistenza\s+tecnica",
            r"intervento\b", r"ricamb", r"spare\s+parts",
            r"sostituz", r"ripristino", r"revisione",
            r"canone\s+manutenzione", r"controllo\s+semestrale",
            r"uscita\s+tecnica", r"ascensor", r"estintore"
        ],
        "conto": ("05.02.10", "Manutenzioni e riparazioni"),
        "categoria_fiscale": CategoriaFiscale.MANUTENZIONE_ORDINARIA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Manutenzione ordinaria - deducibile 100% fino al 5% dei beni ammortizzabili"
    },
    
    # CARBURANTI
    "carburante": {
        "patterns": [
            r"benzina", r"gasolio", r"diesel", r"carburant",
            r"rifornimento", r"eni\s+station", r"q8\b", r"tamoil",
            r"ip\s+station", r"total\s+erg", r"esso\b", r"shell\b"
        ],
        "conto": ("05.02.11", "Carburanti e lubrificanti"),
        "categoria_fiscale": CategoriaFiscale.CARBURANTE,
        "deducibilita_ires": 100,  # Se veicolo strumentale
        "deducibilita_irap": 100,
        "note": "Carburante - 100% se veicolo strumentale, 20% se uso promiscuo (auto aziendali)"
    },
    
    # FERRAMENTA E UTENSILERIA
    "ferramenta": {
        "patterns": [
            r"lama\b", r"vite\b", r"bullone", r"dado\b", r"nastro",
            r"fascetta", r"utensil", r"attrezz", r"chiave\b",
            r"cacciavite", r"martello", r"pinza", r"trapano",
            r"sega\b", r"wuerth", r"berner", r"wurth",
            r"cerniere?\b", r"silicone", r"centralino",
            r"bicchier.*rock", r"teiera", r"ramekin", r"souffle",
            r"piatto.*pizza", r"vassoio", r"posate", r"cucchiai",
            r"forchett", r"coltell.*tavola", r"portaposate",
            r"pedana.*aliment", r"pile\s+(aa|aaa|stilo)",
            r"cavo\s+(hdmi|usb|lightning)", r"mouse", r"tastiera",
            r"led\s+faro", r"lampada\s+led", r"alimentatore"
        ],
        "conto": ("05.01.06", "Acquisto piccola utensileria"),
        "categoria_fiscale": CategoriaFiscale.ATTREZZATURE_MINORI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Utensileria minore - deducibile 100% se valore unitario < €516,46"
    },
    
    # MATERIALE DI CONSUMO E IMBALLAGGIO
    "materiale_consumo": {
        "patterns": [
            r"borsa\b", r"busta\b", r"sacchetto", r"imballag",
            r"carta\b", r"cartone", r"scatol", r"confezione",
            r"pellicola", r"vaschett", r"contenitor", r"packaging",
            r"tovagliolo", r"tovagliett", r"piatti?\s+pian",
            r"coppett", r"rotoli?\s+(termico|cassa)"
        ],
        "conto": ("05.01.07", "Materiali di consumo e imballaggio"),
        "categoria_fiscale": CategoriaFiscale.MATERIE_PRIME,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Materiali di consumo - 100% deducibile"
    },
    
    # SPESE BANCARIE
    "spese_bancarie": {
        "patterns": [
            r"commissione\b", r"spese?\s+(gestione|incasso|bonifico)",
            r"interessi?\s+(passiv|bancari)", r"canone\s+c/?c",
            r"servizio\s+bancario", r"pos\s+(fee|mensile)", r"rid\b",
            r"canone\s+mensile\s+pos", r"comm\s*%\s*tecnica",
            r"pagobcm", r"satispay", r"sumup", r"nexi"
        ],
        "conto": ("05.05.02", "Spese e commissioni bancarie"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Spese bancarie - 100% deducibile"
    },
    
    # CONSULENZE PROFESSIONALI
    "consulenze": {
        "patterns": [
            r"consulen", r"commercialista", r"avvocato", r"notaio",
            r"professionista", r"parcella", r"onorario",
            r"assistenza\s+(legale|fiscale|contabile)"
        ],
        "conto": ("05.02.12", "Consulenze e prestazioni professionali"),
        "categoria_fiscale": CategoriaFiscale.CONSULENZE_PROFESSIONALI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Consulenze - 100% deducibile, verificare ritenuta d'acconto"
    },
    
    # ASSICURAZIONI
    "assicurazioni": {
        "patterns": [
            r"assicuraz", r"polizza", r"premio\s+(assicurativo|annuo)",
            r"rca\b", r"kasko", r"furto\s+incendio", r"rc\s+professionale"
        ],
        "conto": ("05.02.13", "Assicurazioni"),
        "categoria_fiscale": CategoriaFiscale.ASSICURAZIONI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Assicurazioni - 100% deducibile"
    },
    
    # PUBBLICITA E MARKETING
    "pubblicita": {
        "patterns": [
            r"pubblicit", r"marketing", r"promoz", r"spot\b",
            r"inserzione", r"banner", r"social\s+media", r"adv\b",
            r"campagna", r"volantino", r"brochure", r"gadget"
        ],
        "conto": ("05.02.14", "Pubblicita e marketing"),
        "categoria_fiscale": CategoriaFiscale.PUBBLICITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Pubblicita - 100% deducibile"
    },
    
    # SPONSORIZZAZIONI
    "sponsorizzazioni": {
        "patterns": [
            r"sponsoriz", r"main\s+sponsor", r"partner\s+sponsor"
        ],
        "conto": ("05.02.14", "Pubblicita e marketing"),
        "categoria_fiscale": CategoriaFiscale.PUBBLICITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Sponsorizzazioni - 100% deducibile"
    },
    
    # AFFITTO LOCALI
    "affitto": {
        "patterns": [
            r"affitto\b", r"canone\s+locazione", r"pigione",
            r"locazione\s+(immobile|locale)", r"fitto\b"
        ],
        "conto": ("05.02.03", "Canoni di locazione"),
        "categoria_fiscale": CategoriaFiscale.AFFITTO_LOCALI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Affitto locali - 100% deducibile"
    },
    
    # PREMI E OMAGGI
    "premi_omaggi": {
        "patterns": [
            r"premio\s+(consumo|fedelt|acquisto)", r"omaggio",
            r"campione\s+gratuito", r"sconto\s+merce", r"regalo",
            r"gadget\s+promozional"
        ],
        "conto": ("05.02.15", "Omaggi e spese promozionali"),
        "categoria_fiscale": CategoriaFiscale.RAPPRESENTANZA,
        "deducibilita_ires": 100,  # Fino a €50 per omaggio
        "deducibilita_irap": 100,
        "note": "Omaggi - deducibili 100% se valore unitario <= €50 (art. 108 TUIR)"
    },
    
    # ACCISE E CONTRIBUTI
    "accise": {
        "patterns": [
            r"accise?", r"contributo?\s+(di\s+)?stato", r"imposta\s+consumo",
            r"diritti?\s+doganal", r"dazi"
        ],
        "conto": ("05.06.02", "Accise e imposte indirette"),
        "categoria_fiscale": CategoriaFiscale.IMPOSTE_TASSE,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Accise - deducibili 100%"
    },
    
    # TRASPORTI E SPEDIZIONI
    "trasporti": {
        "patterns": [
            r"trasport", r"spedizion", r"corriere", r"dhl\b",
            r"ups\b", r"fedex", r"bartolini", r"brt\b", r"gls\b",
            r"sda\b", r"poste\s+italian", r"consegna\b", r"delivery",
            r"pedaggio", r"autostrad", r"parking", r"parcheggio"
        ],
        "conto": ("05.02.16", "Trasporti su acquisti"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Spese di trasporto - 100% deducibile"
    },
    
    # SPESE DI RAPPRESENTANZA
    "rappresentanza": {
        "patterns": [
            r"pranzo\s+(aziendale|di\s+lavoro)", r"cena\s+di\s+lavoro",
            r"pasto\s+(esterno|aziendale)", r"menu\s+fisso",
            r"ospitalit", r"conviv"
        ],
        "conto": ("05.02.18", "Spese di rappresentanza"),
        "categoria_fiscale": CategoriaFiscale.RAPPRESENTANZA,
        "deducibilita_ires": 75,  # 75% deducibile
        "deducibilita_irap": 100,
        "note": "Spese rappresentanza - deducibili 75% fino ai limiti di legge (art. 108 TUIR)"
    },
    
    # PULIZIA E IGIENE
    "pulizia": {
        "patterns": [
            r"pulizia", r"detergent", r"igienizz", r"sanificaz",
            r"disinfettant", r"sapone", r"carta\s+igienica",
            r"detersivo", r"cleaning", r"amuchina", r"wettex",
            r"guanti\s+(nitrile|lattice|vinile|monouso)",
            r"bobine", r"rotoli\s+cassa", r"tovaglioli"
        ],
        "conto": ("05.01.08", "Prodotti per pulizia e igiene"),
        "categoria_fiscale": CategoriaFiscale.MATERIE_PRIME,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Prodotti pulizia - 100% deducibile"
    },
    
    # CAFFE E TORREFAZIONE
    "caffe": {
        "patterns": [
            r"caff[eè]\b", r"espresso", r"cappuccino", r"moka",
            r"miscela", r"arabica", r"robusta", r"torrefazione",
            r"capsula", r"cialda", r"nespresso", r"dolce\s+gusto",
            r"lavazza", r"illy\b", r"segafredo", r"costadoro"
        ],
        "conto": ("05.01.09", "Acquisto caffe e affini"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Caffe per rivendita - 100% deducibile"
    },
    
    # SURGELATI
    "surgelati": {
        "patterns": [
            r"surgelat", r"congelat", r"frozen", r"ghiaccia",
            r"gelato\b", r"sorbetto", r"granita", r"semifreddo"
        ],
        "conto": ("05.01.10", "Acquisto surgelati"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Surgelati per rivendita - 100% deducibile"
    },
    
    # PRODOTTI DA FORNO E PASTICCERIA
    "pasticceria": {
        "patterns": [
            r"cornett", r"brioche", r"croissant", r"sfoglia",
            r"pasticceria", r"torta", r"dolciar", r"ciambella",
            r"plum\s*cake", r"biscott", r"pastiera", r"cannolo",
            r"pane\s+(multicereali|integrale|bianco)", r"panino",
            r"ciabatta", r"rosetta", r"panetteria", r"focaccia",
            r"caramel", r"chewing\s*gum", r"gomma\s+da\s+masticar",
            r"menta\s+fredda", r"vigorsol", r"vivident", r"frisk"
        ],
        "conto": ("05.01.11", "Acquisto prodotti da forno"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Prodotti da forno per rivendita - 100% deducibile"
    },
    
    # DIRITTI SIAE/SCF
    "diritti_autore": {
        "patterns": [
            r"siae\b", r"scf\b", r"diritti?\s+d[\'']?autore",
            r"musica\s+d[\'']?ambiente", r"compensi?\s+siae",
            r"licenza\s+musicale", r"repertorio"
        ],
        "conto": ("05.02.21", "Diritti SIAE e licenze"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Diritti SIAE - 100% deducibile come costi per servizi"
    },
    
    # NOLEGGIO AUTO LUNGO TERMINE
    "noleggio_auto": {
        "patterns": [
            r"noleggio\s+(auto|veicol|lungo\s+termine)",
            r"arval\b", r"leasys", r"ald\s+automotive",
            r"canone\s+finanziario", r"nlt\b", r"lease"
        ],
        "conto": ("05.02.22", "Noleggio automezzi"),
        "categoria_fiscale": CategoriaFiscale.NOLEGGIO_AUTO,
        "deducibilita_ires": 20,  # 20% per uso promiscuo
        "deducibilita_irap": 20,
        "note": "Noleggio auto - deducibile 20% uso promiscuo (art. 164 TUIR), 100% se strumentale"
    },
    
    # BUONI PASTO
    "buoni_pasto": {
        "patterns": [
            r"buon[io]\s+pasto", r"ticket\s+restaurant", r"edenred",
            r"sodexo\s+pass", r"day\s+tronic", r"pellegrini\s+card"
        ],
        "conto": ("05.03.05", "Buoni pasto dipendenti"),
        "categoria_fiscale": CategoriaFiscale.PERSONALE,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Buoni pasto - 100% deducibile, IVA 4% detraibile"
    },
    
    # CANONI E ABBONAMENTI
    "canoni_abbonamenti": {
        "patterns": [
            r"canone\s+(manutenzione|assistenza|abbonamento)",
            r"abbonamento\s+(annuale|mensile|trimestrale)",
            r"legalmail", r"pec\b", r"firma\s+digitale"
        ],
        "conto": ("05.02.23", "Canoni e abbonamenti"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Canoni e abbonamenti - 100% deducibile"
    },
    
    # BIRRA
    "birra": {
        "patterns": [
            r"birra\b", r"peroni\b", r"heineken", r"moretti",
            r"nastro\s+azzurro", r"tourtel", r"corona\b",
            r"budweiser", r"ceres\b", r"beck[\'']?s"
        ],
        "conto": ("05.01.03", "Acquisto bevande alcoliche"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Birra per rivendita - 100% deducibile"
    },
    
    # MATERIALE EDILE E FERRAMENTA SPECIFICO
    "materiale_edile": {
        "patterns": [
            r"profilat", r"alluminio\b", r"acquaragia",
            r"vernice", r"stucco", r"cemento", r"malta",
            r"piastrelle", r"legno\b", r"pannello"
        ],
        "conto": ("05.01.12", "Materiale edile e costruzioni"),
        "categoria_fiscale": CategoriaFiscale.MATERIE_PRIME,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Materiale edile - 100% deducibile"
    },
    
    # THE E INFUSI
    "the_infusi": {
        "patterns": [
            r"\bthe\b", r"\btea\b", r"infuso", r"camomilla",
            r"tisana", r"esta\s+the", r"ferrero.*the",
            r"lipton", r"twinings"
        ],
        "conto": ("05.01.04", "Acquisto bevande analcoliche"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "The e infusi per rivendita - 100% deducibile"
    },
    
    # SALUMI E INSACCATI
    "salumi": {
        "patterns": [
            r"salame\b", r"prosciutt", r"pancetta", r"mortadella",
            r"bresaola", r"speck\b", r"coppa\b", r"lardo\b",
            r"wurstel", r"salsiccia", r"insaccat", r"affettat",
            r"cervellatina", r"cotto\b.*suino"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Salumi per rivendita - 100% deducibile"
    },
    
    # LATTICINI E FORMAGGI
    "latticini": {
        "patterns": [
            r"grana\s+padano", r"parmigiano", r"pecorino",
            r"mozzarella", r"ricotta", r"burro\b", r"panna\b",
            r"yogurt", r"latticin", r"caseari"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Latticini per rivendita - 100% deducibile"
    },
    
    # CONFETTURE E MARMELLATE  
    "confetture": {
        "patterns": [
            r"confettura", r"marmellata", r"composta",
            r"hero\b", r"zuegg", r"rigoni", r"poker\s+confet"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Confetture per rivendita - 100% deducibile"
    },
    
    # PRODOTTI ORIENTALI/ETNICI
    "prodotti_etnici": {
        "patterns": [
            r"wasabi", r"sushi", r"soia\b", r"tofu",
            r"noodle", r"ramen", r"curry", r"tandoori"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Prodotti etnici per rivendita - 100% deducibile"
    },
    
    # AMMONIACA E PRODOTTI CHIMICI ALIMENTARI
    "additivi_alimentari": {
        "patterns": [
            r"ammoniaca.*bicarbonato", r"e503\b", r"lievito",
            r"bicarbonato", r"additiv", r"conservant"
        ],
        "conto": ("05.01.13", "Additivi e ingredienti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MATERIE_PRIME,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Additivi alimentari - 100% deducibile"
    },
    
    # FRUTTA SECCA E CANDITI
    "frutta_secca": {
        "patterns": [
            r"scorzone", r"candito", r"frutta\s+secca",
            r"mandorl", r"nocciola", r"pistacchio", r"noce\b",
            r"uvetta", r"datteri", r"fichi\s+secchi"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Frutta secca per rivendita - 100% deducibile"
    },
    
    # FUNGHI
    "funghi": {
        "patterns": [
            r"fungh", r"champignon", r"porcin", r"ovul",
            r"chiodini", r"pleurotus", r"tartufo"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Funghi per rivendita - 100% deducibile"
    },
    
    # VERDURE E ORTAGGI
    "verdure": {
        "patterns": [
            r"sedano\b", r"carota", r"cipolla", r"pomodor",
            r"insalata", r"lattuga", r"zucchina", r"melanzana",
            r"peperone", r"patata", r"mirtill", r"ortofrutt"
        ],
        "conto": ("05.01.05", "Acquisto prodotti alimentari"),
        "categoria_fiscale": CategoriaFiscale.MERCE_RIVENDITA,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Verdure per rivendita - 100% deducibile"
    },
    
    # TAPPEZZERIA E TENDAGGI
    "tappezzeria": {
        "patterns": [
            r"tappezzer", r"tendaggi", r"tenda\b", r"tessut",
            r"stoffa", r"rivestiment", r"imbottit"
        ],
        "conto": ("05.02.24", "Arredi e tappezzeria"),
        "categoria_fiscale": CategoriaFiscale.SERVIZI,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Tappezzeria - 100% deducibile come servizi"
    },
    
    # IMBALLAGGI SPECIFICI
    "imballaggi": {
        "patterns": [
            r"borsa\s+tnt", r"shopper", r"busta\s+biodegradabile",
            r"sacchett", r"vaschett", r"contenitor.*monouso"
        ],
        "conto": ("05.01.07", "Materiali di consumo e imballaggio"),
        "categoria_fiscale": CategoriaFiscale.MATERIE_PRIME,
        "deducibilita_ires": 100,
        "deducibilita_irap": 100,
        "note": "Imballaggi - 100% deducibile"
    }
}

# Pattern per categoria basati su fornitore
PATTERNS_FORNITORE = {
    # Bevande alcoliche e vini
    "distilleria|distillerie": "bevande_alcoliche",
    "tanqueray|campari|martini.*rossi": "bevande_alcoliche",
    "drink\\s*up|coop.*eureka|asprinio": "bevande_alcoliche",
    "enoteca|cantina|vinicol|feudi\\s+di\\s+san\\s+gregorio": "bevande_alcoliche",
    "umani\\s+ronchi|bortolomiol|collefasani|giordano\\s+vini": "bevande_alcoliche",
    "gasatissima|free\\s+srls": "bevande_alcoliche",
    
    # Caffe e torrefazione
    "kimbo|lavazza|illy|segafredo|costadoro|torrefazione": "caffe",
    "foodness|domori": "caffe",  # Caffè ginseng e the
    
    # Surgelati
    "master\\s*frost|mister\\s*frost|surgela|frigori": "surgelati",
    
    # Pasticceria e dolci
    "dolciaria|acquaviva|pasticceria": "pasticceria",
    "perfetti\\s+van\\s+melle|amarelli|venchi": "pasticceria",
    "pastiglie\\s+leone|mondo\\s+senza\\s+glutine": "pasticceria",
    "sweet\\s+drink": "pasticceria",  # Torroni
    
    # Panetteria
    "gb\\s*food|panetter|panificio|duegi": "pasticceria",
    
    # Alimentari generali
    "g\\.?i\\.?a\\.?l|generale\\s+ingrosso\\s+alimentar": "alimentari",
    "ap\\s+commerciale|ingrosso\\s+alimentar": "alimentari",
    "big\\s+food|sud\\s+ingrosso|rondinella\\s+market": "alimentari",
    "saima|cozzolino|nasti\\s+group|di\\s+cosmo": "alimentari",
    "cilatte|europa\\s+23|carini": "alimentari",
    "san\\s+carlo|barilla|ferrero|mulino|galbani": "alimentari",
    "siro\\s+s\\.?r\\.?l|f\\.?lli\\s+sommella|f\\.?lli\\s+fiorentino": "alimentari",
    "granzuccheri|olive\\s+miraglia|eurouova|df\\s+baldassarre": "alimentari",
    "carni\\s+de|lubrano|varriale": "alimentari",  # Macellerie e ortofrutta
    "ingrosso.*bibite|cinoglosso": "bevande_analcoliche",
    
    # Materiali consumo e igiene
    "langellotti|gtm\\s+detersivi|tommasino": "pulizia",
    "anthirat|pest": "pulizia",  # Disinfestazione
    
    # Imballaggi e carta
    "carta\\s*[&e]?\\s*party|artecarta|alfa\\s+service": "imballaggi",
    "carpino|mautoneone|ste\\.?cla": "imballaggi",
    "sanson\\s+cart|m&g\\s+distribuzione": "imballaggi",  # Rotoli termici
    
    # Ferramenta e utensili
    "wuerth|wurth|berner": "ferramenta",
    "leroy\\s+merlin|bricofer|obi\\b|brico": "ferramenta",
    "buonaiuto|scaramuzza|stabium|termoidraulica": "materiale_edile",
    "climaria|freddo.*caldo": "manutenzione",  # Impianti clima
    "ferlam|cmt\\s+srl|le\\.?fer": "materiale_edile",
    "ferramenta\\s+f\\.?lli\\s+leo|icommerce": "ferramenta",
    
    # Attrezzature bar/ristorazione
    "fla\\s+s\\.?r\\.?l|f\\.?lli\\s+casolaro|imperatore\\s+hotellerie": "ferramenta",
    "ve\\.?mo\\.?\\s+hotellerie|ristosubito|priolinox": "ferramenta",
    "van\\s+berkel|spillatura|novacqua": "ferramenta",
    "metro\\s+italia|magma\\s+srl": "ferramenta",  # Grossisti HoReCa
    "gruppo\\s+martellozzo": "bevande_alcoliche",  # Spumanti
    
    # Segnaletica e comunicazione
    "targhetdirect|cartelli|insegn": "pubblicita",
    
    # Disinfestazione e pest control
    "r\\.?t\\.?a\\.?\\s+romana|pest\\s*west": "pulizia",
    
    # Pasti esterni e ristorazione
    "vi\\.?ma\\.?\\s+s\\.?r\\.?l|mensa|pranzo\\s+aziendale": "rappresentanza",
    
    # Parcheggi e pedaggi
    "campania\\s+2|autostrad|telepass|parking": "trasporti",
    
    # Utenze
    "enel|edison|a2a|iren|sorgenia": "utenze_elettricita",
    "eni\\s+(gas|plenitude)|italgas": "utenze_gas",
    "abc.*acqua|acquedotto": "utenze_acqua",
    
    # Telefonia e internet
    "tim\\b|telecom|vodafone|wind|fastweb": "telefonia",
    
    # Software e cloud
    "google|microsoft|amazon\\s+aws|azure": "software_cloud",
    "hp\\s+italy|hp\\s+instant\\s+ink": "canoni_abbonamenti",
    "amazon\\s+business|amazon\\s+eu": "ferramenta",  # Acquisti vari
    "fattura24|invoicex|tnx\\s+srl": "canoni_abbonamenti",
    "cromo\\s+srl|madbit": "canoni_abbonamenti",  # Servizi cloud
    "infocamere|today\\s+service": "consulenze",  # Servizi camerali
    
    # Elettronica
    "electronics.*house|mediamarket|r-store|tufano\\s+teresa": "ferramenta",
    "vidoelettronica|enzo\\s+led|any\\s+lamp|daedalustech": "ferramenta",
    "gruppo\\s+adam|microtecnica": "ferramenta",
    
    # Assicurazioni
    "assicuraz|unipol|generali|allianz|axa": "assicurazioni",
    
    # Consulenze e legali
    "commercialista|studio\\s+(legale|notarile)": "consulenze",
    "aniello\\s+limone|de\\s+juliis|da\\.?dif": "consulenze",  # Avvocati
    
    # Diritti d'autore
    "s\\.?i\\.?a\\.?e\\.?|siae": "diritti_autore",
    
    # Manutenzione
    "timas\\s+ascensori": "manutenzione",
    "monals|ifi\\s+sud": "manutenzione",  # Assistenza tecnica
    "punto\\s+a\\s+srl": "manutenzione",  # Estintori
    
    # Pubblicità
    "subito\\.?it|manzoni": "pubblicita",
    "paraiso|sponsoriz": "pubblicita",
    
    # Ceramiche e arredamento
    "ceramiche\\s+mara|arredotop|f\\.?covone": "materiale_edile",
    
    # Abbigliamento lavoro
    "divise.*divise|skechers|lemiro": "ferramenta",  # Uniformi/scarpe lavoro
    
    # Trasporti e parcheggi
    "adr\\s+mobility": "trasporti",
    
    # Noleggio auto
    "arval|leasys|ald\\s+automotive|service\\s+lease": "noleggio_auto",
    
    # Buoni pasto
    "edenred|sodexo|ticket\\s+restaurant": "buoni_pasto",
    
    # Servizi digitali e POS
    "infocert|aruba|register|legalmail": "canoni_abbonamenti",
    "tecmarket|satispay|sumup|nexi": "spese_bancarie",
    
    # Tappezzeria
    "tappezzer|tendaggi|covino": "tappezzeria",
    
    # Birra
    "peroni|heineken|carlsberg|ab\\s+inbev": "birra",
    "top\\s+spina": "birra",
    
    # Attrezzature bar/cucina
    "fla\\s+srl|horeca|ristorazione": "ferramenta",
}


# ============== PIANO DEI CONTI ESTESO ==============

PIANO_CONTI_ESTESO = {
    # ATTIVO
    "01.01.01": {"nome": "Cassa", "categoria": "attivo", "natura": "finanziario"},
    "01.01.02": {"nome": "Banca c/c", "categoria": "attivo", "natura": "finanziario"},
    "01.02.01": {"nome": "Crediti v/clienti", "categoria": "attivo", "natura": "finanziario"},
    "01.02.02": {"nome": "Crediti v/fornitori (anticipi)", "categoria": "attivo", "natura": "finanziario"},
    "01.03.01": {"nome": "Magazzino merci", "categoria": "attivo", "natura": "economico"},
    "01.03.02": {"nome": "Magazzino materie prime", "categoria": "attivo", "natura": "economico"},
    "01.04.01": {"nome": "IVA a credito", "categoria": "attivo", "natura": "finanziario"},
    "01.04.02": {"nome": "Ritenute subite", "categoria": "attivo", "natura": "finanziario"},
    "01.04.03": {"nome": "Acconti imposte", "categoria": "attivo", "natura": "finanziario"},
    "01.05.01": {"nome": "Ratei attivi", "categoria": "attivo", "natura": "economico"},
    "01.05.02": {"nome": "Risconti attivi", "categoria": "attivo", "natura": "economico"},
    "01.06.01": {"nome": "Impianti e macchinari", "categoria": "attivo", "natura": "economico"},
    "01.06.02": {"nome": "Attrezzature", "categoria": "attivo", "natura": "economico"},
    "01.06.03": {"nome": "Automezzi", "categoria": "attivo", "natura": "economico"},
    "01.06.04": {"nome": "Mobili e arredi", "categoria": "attivo", "natura": "economico"},
    "01.06.05": {"nome": "Macchine ufficio elettroniche", "categoria": "attivo", "natura": "economico"},
    
    # PASSIVO
    "02.01.01": {"nome": "Debiti v/fornitori", "categoria": "passivo", "natura": "finanziario"},
    "02.01.02": {"nome": "Debiti v/dipendenti", "categoria": "passivo", "natura": "finanziario"},
    "02.02.01": {"nome": "Debiti tributari", "categoria": "passivo", "natura": "finanziario"},
    "02.02.02": {"nome": "Debiti v/INPS", "categoria": "passivo", "natura": "finanziario"},
    "02.02.03": {"nome": "Debiti v/INAIL", "categoria": "passivo", "natura": "finanziario"},
    "02.02.04": {"nome": "Debiti per ritenute", "categoria": "passivo", "natura": "finanziario"},
    "02.03.01": {"nome": "IVA a debito", "categoria": "passivo", "natura": "finanziario"},
    "02.03.02": {"nome": "IVA da versare", "categoria": "passivo", "natura": "finanziario"},
    "02.04.01": {"nome": "Fondo TFR", "categoria": "passivo", "natura": "finanziario"},
    "02.04.02": {"nome": "Fondo rischi", "categoria": "passivo", "natura": "finanziario"},
    "02.05.01": {"nome": "Ratei passivi", "categoria": "passivo", "natura": "economico"},
    "02.05.02": {"nome": "Risconti passivi", "categoria": "passivo", "natura": "economico"},
    "02.06.01": {"nome": "Mutui passivi", "categoria": "passivo", "natura": "finanziario"},
    "02.06.02": {"nome": "Finanziamenti bancari", "categoria": "passivo", "natura": "finanziario"},
    
    # PATRIMONIO NETTO
    "03.01.01": {"nome": "Capitale sociale", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.02.01": {"nome": "Riserva legale", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.02.02": {"nome": "Riserva straordinaria", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.03.01": {"nome": "Utile d'esercizio", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.03.02": {"nome": "Perdita d'esercizio", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.04.01": {"nome": "Utili portati a nuovo", "categoria": "patrimonio_netto", "natura": "economico"},
    "03.04.02": {"nome": "Perdite portate a nuovo", "categoria": "patrimonio_netto", "natura": "economico"},
    
    # RICAVI
    "04.01.01": {"nome": "Ricavi vendite prodotti", "categoria": "ricavi", "natura": "economico"},
    "04.01.02": {"nome": "Ricavi vendite bar", "categoria": "ricavi", "natura": "economico"},
    "04.01.03": {"nome": "Ricavi vendite cucina", "categoria": "ricavi", "natura": "economico"},
    "04.01.04": {"nome": "Ricavi vendite alcolici", "categoria": "ricavi", "natura": "economico"},
    "04.01.05": {"nome": "Ricavi vendite tabacchi", "categoria": "ricavi", "natura": "economico"},
    "04.02.01": {"nome": "Ricavi prestazioni servizi", "categoria": "ricavi", "natura": "economico"},
    "04.03.01": {"nome": "Proventi finanziari", "categoria": "ricavi", "natura": "economico"},
    "04.03.02": {"nome": "Interessi attivi bancari", "categoria": "ricavi", "natura": "economico"},
    "04.04.01": {"nome": "Proventi straordinari", "categoria": "ricavi", "natura": "economico"},
    "04.04.02": {"nome": "Plusvalenze", "categoria": "ricavi", "natura": "economico"},
    "04.04.03": {"nome": "Sopravvenienze attive", "categoria": "ricavi", "natura": "economico"},
    
    # COSTI
    "05.01.01": {"nome": "Acquisto merci", "categoria": "costi", "natura": "economico"},
    "05.01.02": {"nome": "Acquisto materie prime", "categoria": "costi", "natura": "economico"},
    "05.01.03": {"nome": "Acquisto bevande alcoliche", "categoria": "costi", "natura": "economico"},
    "05.01.04": {"nome": "Acquisto bevande analcoliche", "categoria": "costi", "natura": "economico"},
    "05.01.05": {"nome": "Acquisto prodotti alimentari", "categoria": "costi", "natura": "economico"},
    "05.01.06": {"nome": "Acquisto piccola utensileria", "categoria": "costi", "natura": "economico"},
    "05.01.07": {"nome": "Materiali di consumo e imballaggio", "categoria": "costi", "natura": "economico"},
    "05.01.08": {"nome": "Prodotti per pulizia e igiene", "categoria": "costi", "natura": "economico"},
    "05.01.09": {"nome": "Acquisto caffe e affini", "categoria": "costi", "natura": "economico"},
    "05.01.10": {"nome": "Acquisto surgelati", "categoria": "costi", "natura": "economico"},
    "05.01.11": {"nome": "Acquisto prodotti da forno", "categoria": "costi", "natura": "economico"},
    "05.01.12": {"nome": "Materiale edile e costruzioni", "categoria": "costi", "natura": "economico"},
    "05.01.13": {"nome": "Additivi e ingredienti alimentari", "categoria": "costi", "natura": "economico"},
    
    "05.02.01": {"nome": "Costi per servizi", "categoria": "costi", "natura": "economico"},
    "05.02.02": {"nome": "Utenze (luce, gas, acqua)", "categoria": "costi", "natura": "economico"},
    "05.02.03": {"nome": "Canoni di locazione", "categoria": "costi", "natura": "economico"},
    "05.02.04": {"nome": "Utenze - Acqua", "categoria": "costi", "natura": "economico"},
    "05.02.05": {"nome": "Utenze - Energia elettrica", "categoria": "costi", "natura": "economico"},
    "05.02.06": {"nome": "Utenze - Gas", "categoria": "costi", "natura": "economico"},
    "05.02.07": {"nome": "Telefonia e comunicazioni", "categoria": "costi", "natura": "economico"},
    "05.02.08": {"nome": "Software e servizi cloud", "categoria": "costi", "natura": "economico"},
    "05.02.09": {"nome": "Noleggi e locazioni operative", "categoria": "costi", "natura": "economico"},
    "05.02.10": {"nome": "Manutenzioni e riparazioni", "categoria": "costi", "natura": "economico"},
    "05.02.11": {"nome": "Carburanti e lubrificanti", "categoria": "costi", "natura": "economico"},
    "05.02.12": {"nome": "Consulenze e prestazioni professionali", "categoria": "costi", "natura": "economico"},
    "05.02.13": {"nome": "Assicurazioni", "categoria": "costi", "natura": "economico"},
    "05.02.14": {"nome": "Pubblicita e marketing", "categoria": "costi", "natura": "economico"},
    "05.02.15": {"nome": "Omaggi e spese promozionali", "categoria": "costi", "natura": "economico"},
    "05.02.16": {"nome": "Trasporti su acquisti", "categoria": "costi", "natura": "economico"},
    "05.02.17": {"nome": "Spese viaggio e trasferte", "categoria": "costi", "natura": "economico"},
    "05.02.18": {"nome": "Spese di rappresentanza", "categoria": "costi", "natura": "economico"},
    "05.02.19": {"nome": "Spese postali", "categoria": "costi", "natura": "economico"},
    "05.02.20": {"nome": "Spese condominiali", "categoria": "costi", "natura": "economico"},
    "05.02.21": {"nome": "Diritti SIAE e licenze", "categoria": "costi", "natura": "economico"},
    "05.02.22": {"nome": "Noleggio automezzi", "categoria": "costi", "natura": "economico"},
    "05.02.23": {"nome": "Canoni e abbonamenti", "categoria": "costi", "natura": "economico"},
    "05.02.24": {"nome": "Arredi e tappezzeria", "categoria": "costi", "natura": "economico"},
    
    "05.03.01": {"nome": "Salari e stipendi", "categoria": "costi", "natura": "economico"},
    "05.03.02": {"nome": "Contributi previdenziali", "categoria": "costi", "natura": "economico"},
    "05.03.03": {"nome": "Accantonamento TFR", "categoria": "costi", "natura": "economico"},
    "05.03.04": {"nome": "Altri costi del personale", "categoria": "costi", "natura": "economico"},
    "05.03.05": {"nome": "Buoni pasto dipendenti", "categoria": "costi", "natura": "economico"},
    
    "05.04.01": {"nome": "Ammortamento immobilizzazioni materiali", "categoria": "costi", "natura": "economico"},
    "05.04.02": {"nome": "Ammortamento immobilizzazioni immateriali", "categoria": "costi", "natura": "economico"},
    "05.04.03": {"nome": "Svalutazioni", "categoria": "costi", "natura": "economico"},
    
    "05.05.01": {"nome": "Interessi passivi bancari", "categoria": "costi", "natura": "economico"},
    "05.05.02": {"nome": "Spese e commissioni bancarie", "categoria": "costi", "natura": "economico"},
    "05.05.03": {"nome": "Interessi passivi su mutui", "categoria": "costi", "natura": "economico"},
    "05.05.04": {"nome": "Interessi passivi su leasing", "categoria": "costi", "natura": "economico"},
    
    "05.06.01": {"nome": "Imposte e tasse", "categoria": "costi", "natura": "economico"},
    "05.06.02": {"nome": "Accise e imposte indirette", "categoria": "costi", "natura": "economico"},
    "05.06.03": {"nome": "IRES", "categoria": "costi", "natura": "economico"},
    "05.06.04": {"nome": "IRAP", "categoria": "costi", "natura": "economico"},
    "05.06.05": {"nome": "IMU", "categoria": "costi", "natura": "economico"},
    
    "05.07.01": {"nome": "Oneri straordinari", "categoria": "costi", "natura": "economico"},
    "05.07.02": {"nome": "Minusvalenze", "categoria": "costi", "natura": "economico"},
    "05.07.03": {"nome": "Sopravvenienze passive", "categoria": "costi", "natura": "economico"},
    "05.07.04": {"nome": "Perdite su crediti", "categoria": "costi", "natura": "economico"},
}


class CategorizzatoreContabile:
    """
    Motore di categorizzazione contabile intelligente.
    Analizza descrizioni e fornitori per determinare il conto corretto.
    """
    
    def __init__(self):
        self.patterns_descrizione = PATTERNS_DESCRIZIONE
        self.patterns_fornitore = PATTERNS_FORNITORE
        self.piano_conti = PIANO_CONTI_ESTESO
    
    def categorizza_linea(
        self,
        descrizione: str,
        fornitore: str = "",
        importo: float = 0
    ) -> CategorizzazioneResult:
        """
        Categorizza una singola linea di fattura.
        
        Args:
            descrizione: Descrizione del prodotto/servizio
            fornitore: Nome del fornitore
            importo: Importo della linea
            
        Returns:
            CategorizzazioneResult con tutti i dettagli
        """
        desc_lower = descrizione.lower().strip()
        forn_lower = fornitore.lower().strip()
        
        # 1. PRIORITA' 1: Prova prima con fornitore noto (più affidabile)
        if forn_lower:
            for pattern, categoria in self.patterns_fornitore.items():
                if re.search(pattern, forn_lower, re.IGNORECASE):
                    if categoria in self.patterns_descrizione:
                        config = self.patterns_descrizione[categoria]
                        return self._build_result(categoria, config, confidenza=0.85)
        
        # 2. PRIORITA' 2: Pattern descrizione (analisi del testo)
        for categoria, config in self.patterns_descrizione.items():
            for pattern in config["patterns"]:
                if re.search(pattern, desc_lower, re.IGNORECASE):
                    return self._build_result(categoria, config, confidenza=0.9)
        
        # 3. Fallback su "Acquisto merci" generico
        return CategorizzazioneResult(
            categoria_merceologica="merci_generiche",
            conto_codice="05.01.01",
            conto_nome="Acquisto merci",
            categoria_fiscale=CategoriaFiscale.MERCE_RIVENDITA,
            percentuale_deducibilita_ires=100,
            percentuale_deducibilita_irap=100,
            note_fiscali="Categoria generica - verificare manualmente",
            confidenza=0.3
        )
    
    def _build_result(
        self, 
        categoria: str, 
        config: Dict[str, Any],
        confidenza: float
    ) -> CategorizzazioneResult:
        """Costruisce il risultato della categorizzazione."""
        conto_codice, conto_nome = config["conto"]
        
        return CategorizzazioneResult(
            categoria_merceologica=categoria,
            conto_codice=conto_codice,
            conto_nome=conto_nome,
            categoria_fiscale=config["categoria_fiscale"],
            percentuale_deducibilita_ires=config["deducibilita_ires"],
            percentuale_deducibilita_irap=config["deducibilita_irap"],
            note_fiscali=config["note"],
            confidenza=confidenza
        )
    
    def categorizza_fattura(
        self,
        linee: List[Dict[str, Any]],
        fornitore: str = ""
    ) -> Dict[str, Any]:
        """
        Categorizza un'intera fattura analizzando tutte le linee.
        Determina la categoria prevalente.
        
        Returns:
            Dict con:
            - categoria_principale: la categoria più frequente
            - dettaglio_linee: categorizzazione per ogni linea
            - riepilogo_conti: importi aggregati per conto
            - totale_deducibile_ires: importo deducibile ai fini IRES
            - totale_deducibile_irap: importo deducibile ai fini IRAP
        """
        dettaglio_linee = []
        conti_importi: Dict[str, float] = {}
        categorie_count: Dict[str, int] = {}
        totale_ires = 0.0
        totale_irap = 0.0
        totale_fattura = 0.0
        
        for linea in linee:
            descrizione = linea.get("descrizione", "")
            
            # Calcola importo linea
            try:
                prezzo_totale = float(linea.get("prezzo_totale", 0) or 0)
            except (ValueError, TypeError):
                prezzo_totale = 0
            
            totale_fattura += prezzo_totale
            
            # Categorizza
            result = self.categorizza_linea(descrizione, fornitore, prezzo_totale)
            
            # Accumula
            dettaglio_linee.append({
                "descrizione": descrizione,
                "importo": prezzo_totale,
                **result.__dict__
            })
            
            # Aggiorna conteggi
            cat = result.categoria_merceologica
            categorie_count[cat] = categorie_count.get(cat, 0) + 1
            
            conto = result.conto_codice
            conti_importi[conto] = conti_importi.get(conto, 0) + prezzo_totale
            
            # Calcola deducibilità
            totale_ires += prezzo_totale * result.percentuale_deducibilita_ires / 100
            totale_irap += prezzo_totale * result.percentuale_deducibilita_irap / 100
        
        # Determina categoria principale
        categoria_principale = max(categorie_count, key=categorie_count.get) if categorie_count else "altro"
        
        # Prepara riepilogo conti
        riepilogo_conti = []
        for conto_cod, importo in sorted(conti_importi.items()):
            conto_info = self.piano_conti.get(conto_cod, {})
            riepilogo_conti.append({
                "codice": conto_cod,
                "nome": conto_info.get("nome", "Conto non trovato"),
                "categoria": conto_info.get("categoria", ""),
                "importo": round(importo, 2)
            })
        
        return {
            "categoria_principale": categoria_principale,
            "dettaglio_linee": dettaglio_linee,
            "riepilogo_conti": riepilogo_conti,
            "totale_fattura": round(totale_fattura, 2),
            "totale_deducibile_ires": round(totale_ires, 2),
            "totale_deducibile_irap": round(totale_irap, 2),
            "percentuale_deducibilita_ires": round(totale_ires / totale_fattura * 100, 2) if totale_fattura > 0 else 0,
            "percentuale_deducibilita_irap": round(totale_irap / totale_fattura * 100, 2) if totale_fattura > 0 else 0
        }


# Singleton instance
_categorizzatore: Optional[CategorizzatoreContabile] = None

def get_categorizzatore() -> CategorizzatoreContabile:
    """Ottiene l'istanza singleton del categorizzatore."""
    global _categorizzatore
    if _categorizzatore is None:
        _categorizzatore = CategorizzatoreContabile()
    return _categorizzatore


def categorizza_descrizione(descrizione: str, fornitore: str = "") -> CategorizzazioneResult:
    """Funzione helper per categorizzare una singola descrizione."""
    return get_categorizzatore().categorizza_linea(descrizione, fornitore)


def categorizza_fattura_completa(linee: List[Dict], fornitore: str = "") -> Dict[str, Any]:
    """Funzione helper per categorizzare un'intera fattura."""
    return get_categorizzatore().categorizza_fattura(linee, fornitore)
