"""
Router Ingredienti — Sistema di normalizzazione nomi commerciali → cucina.

Flusso matching a 3 livelli:
  L1: Mapping manuale (nome_mapping collection)
  L2: Keyword matching (dizionario culinario statico)
  L3: LLM (Claude Sonnet) per i casi ambigui

Endpoint principali:
  GET  /api/ingredienti/cerca?q=farina           → ricerca semantica nel dizionario
  GET  /api/ingredienti/confronto?ingrediente=x  → confronto fornitori con prezzo effettivo
  POST /api/ingredienti/normalizza-batch         → normalizza tutti i prodotti del dizionario
  PATCH /api/ingredienti/dizionario/{id}/butto   → imposta percentuale di scarto
  POST /api/ingredienti/mapping-manuale          → salva mapping confermato dall'utente
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from pymongo import UpdateOne as PyUpdateOne

from app.lotti.db import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingredienti", tags=["ingredienti"])


# ==================== L2 — DIZIONARIO CULINARIO STATICO ====================
# chiave = nome canonico (cucina), valori = keyword per riconoscimento automatico
# Aggiungi qui nuove categorie senza toccare altro codice

INGREDIENTI_CANONICI: dict[str, list[str]] = {
    "Farina 00": ["farina 00", "farina tipo 00", "tipo 00", "farina bianca"],
    "Farina Manitoba": ["farina manitoba", "manitoba", "w38", "w33", "w36", "w40"],
    "Farina tipo 0": ["farina tipo 0", "tipo 0"],
    "Farina tipo 1": ["farina tipo 1", "tipo 1"],
    "Farina tipo 2": ["farina tipo 2", "tipo 2"],
    "Farina integrale": ["farina integrale", "integrale"],
    "Semola": ["semola rimacinata", "semola", "semolato", "semolino"],
    "Farina": ["farina"],
    "Olio extravergine": ["olio extravergine", "olio evo", "evo", "extravergine", "olio oliva"],
    "Olio di semi": ["olio semi", "olio arachide", "olio girasole", "olio vegetale", "olio soia"],
    "Olio": ["olio"],
    "Burro": ["burro", "burro piadi", "beurre"],
    "Margarina": ["margarina"],
    "Panna": ["panna fresca", "panna montare", "panna cucina", "panna"],
    "Latte": ["latte intero", "latte fresco", "latte uht", "latte parzialmente", "latte"],
    "Uova": ["uova fresche", "uova categoria", "cat.a uova", "uova", "uovo"],
    "Zucchero": ["zucchero semolato", "zucchero a velo", "zucchero grezzo", "zucchero raf.sem", "zucchero raf.semol", "zucch.classico", "zucchero"],
    "Sale": ["sale fino", "sale grosso", "sale marino", "sale"],
    "Lievito": ["lievito di birra", "lievito secco", "lievito chimico", "lievito"],
    "Bicarbonato": ["bicarbonato", "sodio"],
    "Carne bovina": [
        "manzo",
        "bovino",
        "scottona",
        "vitello",
        "vitellone",
        "muscolo",
        "filetto di manzo",
        "filetto bovino",
        "lombata",
        "costata",
        "bistecca",
        "tritato manzo",
        "macinato manzo",
    ],
    "Carne suina": ["maiale", "suino", "lonza", "spalla maiale", "pancetta", "coppa"],
    "Pollo": ["petto pollo", "cosce pollo", "alette pollo", "fusi pollo", "pollo intero", "pollo"],
    "Tacchino": ["tacchino", "fesa tacchino"],
    "Agnello": ["agnello"],
    "Coniglio": ["coniglio"],
    "Carne macinata": ["macinato", "tritato", "carne macinata"],
    "Prosciutto cotto": ["prosciutto cotto", "p.cotto", "p/cotto", "p. cotto"],
    "Prosciutto crudo": ["prosciutto crudo", "crudo di parma", "san daniele", "p.crudo", "p/crudo", "p. crudo", "crudo"],
    "Mortadella": ["mortadella"],
    "Salame": ["salame"],
    "Bresaola": ["bresaola"],
    "Salsiccia": ["salsiccia", "wurstel"],
    "Speck": ["speck"],
    "Mozzarella": ["mozzarella di bufala", "fior di latte", "mozzarella"],
    "Parmigiano": ["parmigiano reggiano", "grana padano", "grana"],
    "Ricotta": ["ricotta"],
    "Pecorino": ["pecorino"],
    "Scamorza": ["scamorza", "provola", "provolone"],
    "Formaggio": ["formaggio", "cheese"],
    "Pomodoro": [
        "pomodori pelati",
        "passata pomodoro",
        "concentrato pomodoro",
        "pomodori insalata",
        "pomodoro",
    ],
    "Pomodorini": ["pomodorini", "ciliegino", "datterino"],
    "Patate": ["patate", "patata novella", "patata"],
    "Cipolla": ["cipolla bianca", "cipolla rossa", "cipolla"],
    "Aglio": ["aglio"],
    "Carote": ["carote", "carota"],
    "Zucchine": ["zucchine", "zucchina", "zucchino"],
    "Melanzane": ["melanzane", "melanzana"],
    "Peperoni": ["peperoni", "peperone"],
    "Funghi": ["funghi", "champignon", "porcini"],
    "Spinaci": ["spinaci", "spinacino"],
    "Insalata": ["insalata", "lattuga", "radicchio", "rucola", "songino"],
    "Limoni": ["limoni", "limone"],
    "Arance": ["arance", "arancia"],
    "Mele": ["mele stark", "mele fuji", "mele granny", "mele golden", "mele", "mela verde", "mela"],
    "Banane": ["banana", "banane"],
    "Pesche": ["pesca", "pesche"],
    "Pere": ["pera", "pere"],
    "Pompelmo": ["pompelmo", "pompelmi"],
    "Pesce": ["merluzzo", "salmone", "tonno", "branzino", "orata", "sogliola", "baccalà"],
    "Gamberi": ["gamberi", "gamberetti", "gamberone", "scampi"],
    "Seppie": ["seppie", "polpo", "calamari"],
    "Pasta": [
        "spaghetti",
        "penne",
        "rigatoni",
        "fusilli",
        "farfalle",
        "linguine",
        "tagliatelle",
        "bucatini",
        "pasta di semola",
    ],
    "Riso": ["riso arborio", "riso carnaroli", "riso vialone", "riso basmati", "riso"],
    "Pane": [
        "pane casereccio",
        "pane di casa",
        "panino",
        "rosetta",
        "baguette",
        "sandwich",
        "toast",
        "pagnotta",
        "pancarrè",
        "pan grattato",
        "pane",
    ],
    "Pasta frolla": ["pasta frolla"],
    "Pasta sfoglia": ["pasta sfoglia"],
    "Caffè": ["caffè", "caffe", "miscela caffè", "espresso"],
    "Tè": ["tè", "te", "tea", "tisana", "infuso"],
    "Cacao": ["cacao amaro", "cacao"],
    "Cioccolato": ["cioccolato fondente", "cioccolato bianco", "cioccolato al latte", "cioccolato"],
    "Acqua": ["acqua minerale", "acqua naturale", "acqua frizzante"],
    "Succhi": ["succo frutta", "nettare", "succo"],
    "Cola": ["coca-cola", "pepsi", "cola"],
    "Aranciata": ["aranciata", "fanta"],
    "Birra": ["birra lager", "birra ale", "birra rossa", "birra"],
    "Vino rosso": ["vino rosso", "chianti", "barolo", "montepulciano"],
    "Vino bianco": ["vino bianco", "pinot grigio", "soave", "vermentino"],
    "Prosecco": ["prosecco", "spumante", "champagne"],
    "Liquori": ["grappa", "rum", "vodka", "gin", "whisky", "brandy", "amaro", "sambuca", "liquore"],
    "Vino": ["vino"],
    "Aceto": ["aceto balsamico", "aceto di vino", "aceto"],
    "Maionese": ["maionese"],
    "Ketchup": ["ketchup"],
    "Senape": ["senape"],
    "Salsa soia": ["salsa soia", "soia"],
    "Detersivi": ["detersivo", "detergente", "sgrassatore", "candeggina", "disinfettante"],
    "Shopper": ["shoppers", "sacchetto", "borsa"],
}


# ── Ampliamento vocabolario canonico (pasticceria/gelateria/rosticceria/cucina) ──
# Additivo: unito a INGREDIENTI_CANONICI. Nel match L2 vince la keyword più lunga,
# quindi i termini specifici ("granella di nocciola") battono i generici ("nocciola").
# In caso di parità vince la voce base (più unificante).
INGREDIENTI_CANONICI_EXTRA: dict[str, list[str]] = {
    # Farine e amidi
    "Fecola di patate": ["fecola di patate", "fecola"],
    "Amido di mais": ["amido di mais", "amido mais", "maizena"],
    "Farina di mandorle": ["farina di mandorle", "farina mandorle", "tpt mandorle"],
    "Farina di riso": ["farina di riso"],
    "Farina di castagne": ["farina di castagne", "farina castagne"],
    "Farina di mais": ["farina di mais", "fioretto", "bramata"],
    "Grano saraceno": ["grano saraceno"],
    "Farina di farro": ["farina di farro", "farro"],
    "Glutine": ["glutine di frumento", "glutine"],
    # Zuccheri e dolcificanti
    "Zucchero di canna": ["zucchero di canna", "zucchero canna", "moscovado", "demerara"],
    "Zucchero invertito": ["zucchero invertito", "trimoline", "trimolina"],
    "Destrosio": ["destrosio"],
    "Fruttosio": ["fruttosio"],
    "Glucosio": ["sciroppo di glucosio", "glucosio disidratato", "glucosio"],
    "Maltodestrine": ["maltodestrine", "maltodestrina"],
    "Miele": ["miele millefiori", "miele di acacia", "miele"],
    "Sciroppo": ["sciroppo d'acero", "sciroppo di agave", "agave", "sciroppo"],
    "Malto": ["estratto di malto", "malto d'orzo", "malto"],
    "Pasta di zucchero": ["pasta di zucchero", "fondente da copertura", "mmf"],
    "Isomalto": ["isomalto"],
    # Grassi (le abbreviazioni di margarina entrano qui, unite alla voce base)
    "Margarina": ["margarina", "margarine", "margar", "marg.", "homillina", "olva thermo", "melange plus homillina"],
    "Burro": ["burro anidro", "burro chiarificato", "burro concentrato"],
    "Olio di oliva": ["olio di oliva", "olio d'oliva"],
    "Olio di cocco": ["olio di cocco", "burro di cocco"],
    "Strutto": ["strutto", "sugna"],
    # Latticini e uova
    "Latte in polvere": ["latte in polvere", "latte magro in polvere", "lsmp"],
    "Latte condensato": ["latte condensato"],
    "Panna fresca": ["panna fresca", "panna da montare", "crema di latte"],
    "Yogurt": ["yogurt", "yoghurt"],
    "Mascarpone": ["mascarpone"],
    "Formaggio spalmabile": ["philadelphia", "formaggio spalmabile", "cream cheese"],
    "Tuorlo": ["tuorlo pastorizzato", "tuorlo", "tuorli", "rosso d'uovo"],
    "Albume": ["albume", "albumi", "bianco d'uovo", "albumina"],
    "Uovo pastorizzato": ["uovo intero pastorizzato", "uova pastorizzate", "uovo liquido"],
    # Lievitanti / gelificanti / addensanti
    "Lievito madre": ["lievito madre", "pasta madre", "licoli"],
    "Gelatina": ["gelatina in fogli", "colla di pesce", "gelatina alimentare", "gelatina"],
    "Pectina": ["pectina nh", "pectina gialla", "pectina"],
    "Agar agar": ["agar agar", "agar"],
    "Gomma xantana": ["gomma xantana", "xantana", "gomma di guar", "carrube"],
    "Stabilizzante": ["stabilizzante", "base gelato", "neutro per gelato", "addensante"],
    # Cioccolato / cacao / coperture
    "Cioccolato fondente": ["cioccolato fondente", "copertura fondente"],
    "Cioccolato al latte": ["cioccolato al latte", "copertura al latte"],
    "Cioccolato bianco": ["cioccolato bianco", "copertura bianca"],
    "Burro di cacao": ["burro di cacao"],
    "Gianduia": ["gianduia", "gianduja", "pasta gianduia"],
    "Gocce di cioccolato": ["gocce di cioccolato", "gocce cioccolato", "scaglie di cioccolato", "chips di cioccolato"],
    "Crema alla nocciola": ["nutella", "crema spalmabile alla nocciola"],
    "Pralinato": ["pralinato", "praliné", "praline"],
    # Frutta secca
    "Nocciole": ["nocciola", "nocciole", "tonda gentile", "nocciole tostate"],
    "Granella di nocciola": ["granella di nocciola", "granella di nocciole", "granella nocciola"],
    "Pasta di nocciola": ["pasta di nocciola", "pasta pura di nocciola", "pasta nocciola"],
    "Mandorle": ["mandorla", "mandorle", "mandorle pelate", "mandorle tostate"],
    "Granella di mandorla": ["granella di mandorla", "granella mandorla", "mandorle a lamelle", "mandorle a filetti"],
    "Pasta di mandorla": ["pasta di mandorla", "pasta di mandorle", "marzapane"],
    "Pistacchio": ["pistacchio", "pistacchi", "pistacchio di bronte"],
    "Granella di pistacchio": ["granella di pistacchio", "granella pistacchio"],
    "Pasta di pistacchio": ["pasta di pistacchio", "pasta pistacchio"],
    "Noci": ["gherigli di noce", "noci", "noce sgusciata"],
    "Pinoli": ["pinoli", "pinolo"],
    "Arachidi": ["arachidi", "arachide", "noccioline"],
    "Anacardi": ["anacardi", "anacardo"],
    "Cocco": ["cocco rapè", "farina di cocco", "cocco grattugiato", "cocco"],
    "Castagne": ["marron glacé", "marroni", "castagne"],
    # Frutta candita / disidratata / fresca per dolci
    "Frutta candita": ["frutta candita", "canditi", "arancia candita", "scorza candita", "cedro candito"],
    "Scorzetta arancio": ["scorzetta arancio", "scorza arancia", "scorzone arancio", "scorza palermo"],
    "Grano cotto": ["grano cotto", "grano per pastiera"],
    "Naspro": ["naspro", "pasta glassatura", "pate a glacer", "glassatura bianco", "glassatura fondente"],
    "Uvetta": ["uvetta", "uva passa", "uva sultanina"],
    "Amarena": ["amarena", "amarene", "ciliegie candite", "visciola", "visciole", "visciolata"],
    "Fragole": ["fragola", "fragole", "fragoline", "fragolina"],
    "Lamponi": ["lampone", "lamponi"],
    "Mirtilli": ["mirtillo", "mirtilli"],
    "Frutti di bosco": ["frutti di bosco"],
    "Albicocche": ["albicocca", "albicocche"],
    "Ananas": ["ananas"],
    "Purea di frutta": ["purea di frutta", "polpa di frutta"],
    # Aromi / spezie / coloranti
    "Vaniglia": ["bacca di vaniglia", "vaniglia bourbon", "estratto di vaniglia", "vaniglia", "vanillina"],
    "Cannella": ["cannella"],
    "Scorza di limone": ["scorza di limone", "buccia di limone", "aroma limone"],
    "Scorza di arancia": ["scorza di arancia", "aroma arancia"],
    "Aroma": ["aroma rum", "aroma di mandorla", "essenza", "aroma"],
    "Colorante alimentare": ["colorante alimentare", "colorante", "coloranti"],
    "Cardamomo": ["cardamomo"],
    "Zenzero": ["zenzero", "ginger"],
    "Noce moscata": ["noce moscata"],
    "Chiodi di garofano": ["chiodi di garofano"],
    "Anice": ["semi di anice", "anice"],
    "Zafferano": ["zafferano"],
    "Pepe": ["pepe nero", "pepe bianco", "pepe"],
    "Peperoncino": ["peperoncino"],
    "Origano": ["origano"],
    "Basilico": ["basilico"],
    "Prezzemolo": ["prezzemolo"],
    "Rosmarino": ["rosmarino"],
    "Salvia": ["salvia"],
    "Alloro": ["alloro"],
    "Menta": ["menta"],
    # Semilavorati pasticceria / gelateria
    "Variegato": ["variegato", "variegatura"],
    "Crema pasticcera": ["crema pasticcera", "crema pasticciera"],
    "Confettura": ["confettura", "marmellata", "composta di frutta"],
    "Glassa": ["glassa a specchio", "gelatina neutra", "glassa a freddo", "glassa"],
    "Pan di Spagna": ["pan di spagna", "pandispagna", "savoiardi", "biscotto savoiardo"],
    "Meringa": ["meringa", "meringhe"],
    "Cialde": ["cono gelato", "coni per gelato", "cialda", "cialde", "wafer"],
    "Marshmallow": ["marshmallow"],
    # Rosticceria / salumi / formaggi / verdure
    "Pancetta": ["pancetta", "guanciale"],
    "Würstel": ["wurstel", "würstel", "hot dog"],
    "Provola": ["provola affumicata", "provola"],
    "Stracchino": ["stracchino", "crescenza"],
    "Gorgonzola": ["gorgonzola"],
    "Burrata": ["burrata", "stracciatella di bufala"],
    "Besciamella": ["besciamella"],
    "Ragù": ["ragù", "ragu", "sugo di carne"],
    "Olive": ["olive verdi", "olive nere", "patè di olive", "olive"],
    "Capperi": ["capperi", "cappero"],
    "Acciughe": ["acciughe", "alici", "filetti di acciuga"],
    "Tonno": ["tonno"],
    "Mais": ["mais dolce", "mais"],
    "Piselli": ["piselli", "pisello"],
    "Fagioli": ["fagioli", "cannellini", "borlotti"],
    "Ceci": ["ceci", "cece"],
    "Lenticchie": ["lenticchie"],
}

# Unione: estende le keyword delle voci base e aggiunge le nuove
for _k, _v in INGREDIENTI_CANONICI_EXTRA.items():
    if _k in INGREDIENTI_CANONICI:
        INGREDIENTI_CANONICI[_k] = list(dict.fromkeys(INGREDIENTI_CANONICI[_k] + _v))
    else:
        INGREDIENTI_CANONICI[_k] = _v


# ── Consolidamento: etichette sovra-specifiche/varianti → UN canonico ──
# Risolve la frammentazione (es. l'LLM che scrive "margarina per croissant").
_CONSOLIDA: dict[str, str] = {
    "margarina per croissant": "Margarina",
    "margarina per dolci": "Margarina",
    "margarina per sfoglia": "Margarina",
    "margarina sfoglia": "Margarina",
    "margarina crema": "Margarina",
    "margarina vegetale": "Margarina",
    "margarina liquida": "Margarina",
    "margarina wiener": "Margarina",
    "crema di nocciole": "Crema alla nocciola",
    "pasta nocciola pura": "Pasta di nocciola",
}


_SING_KEY_MAP = None  # cache {forma_singolarizzata: chiave_canonica}, popolata pigramente


def _consolida_canonico(canonico: Optional[str]) -> Optional[str]:
    """Riduce un canonico al canonico unico controllato:
    consolidamento varianti + maiuscola coerente (così 'margarina' e 'Margarina'
    sono la stessa voce)."""
    if not canonico:
        return canonico
    base = str(canonico).strip()
    low = base.lower()
    if low in _CONSOLIDA:
        return _CONSOLIDA[low]
    # match esatto su chiave canonica (preserva il case ufficiale)
    for k in INGREDIENTI_CANONICI:
        if k.lower() == low:
            return k
    # Unifica singolare/plurale verso la chiave canonica ESISTENTE con la stessa
    # forma singolarizzata: 'Nocciola' e 'Nocciole' convergono sulla chiave 'Nocciole'
    # (a prescindere da quale delle due sia l'input). Mappa pre-calcolata una volta.
    # Sicuro: ritorna solo chiavi già presenti; 'Latte' resta 'Latte' perché nessuna
    # chiave ha forma singolarizzata 'latta'.
    global _SING_KEY_MAP
    if _SING_KEY_MAP is None:
        _SING_KEY_MAP = {}
        for k in INGREDIENTI_CANONICI:
            _SING_KEY_MAP.setdefault(_singolarizza(k.lower()), k)
    hit = _SING_KEY_MAP.get(_singolarizza(low))
    if hit:
        return hit
    # capitalizza in modo pulito se è tutto minuscolo
    if base and base == base.lower():
        return base[0].upper() + base[1:]
    return base


async def _impara_mapping(nome: str, canonico: str) -> None:
    """Il dizionario 'impara': salva term→canonico in nome_mapping (L1), così le
    fatture successive lo risolvono subito e in modo coerente. Non sovrascrive
    mapping già presenti (manuali o già appresi)."""
    if not nome or not canonico:
        return
    key = nome.lower().strip()[:200]
    try:
        existing = await db.nome_mapping.find_one(
            {"descrizione_key": key}, {"_id": 0, "nome_canc": 1}
        )
        if existing and existing.get("nome_canc"):
            return
        await db.nome_mapping.update_one(
            {"descrizione_key": key},
            {"$set": {
                "descrizione_key": key,
                "nome_canc": canonico,
                "fonte": "auto",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
    except Exception:
        logger.debug("[ingredienti] errore non bloccante ignorato")


def _singolarizza(testo: str) -> str:
    """Riduce i plurali italiani al singolare per il keyword match
    ('nocciole'→'nocciola', 'mandorle'→'mandorla', 'uova'→'uovo' via eccezioni).
    Euristica leggera, applicata parola per parola; non altera parole < 4 lettere."""
    ecc = {"uova": "uovo", "u, ova": "uovo"}
    out = []
    for w in testo.split():
        wl = w.lower()
        if wl in ecc:
            out.append(ecc[wl]); continue
        if len(wl) >= 4:
            if wl.endswith("he"):       # es. 'paste'->no; 'oche'->oca gestito sotto
                wl = wl[:-2] + "ca"
            elif wl.endswith("ghi"):
                wl = wl[:-3] + "go"
            elif wl.endswith("e"):      # nocciole->nocciola, mandorle->mandorla
                wl = wl[:-1] + "a"
            elif wl.endswith("i"):      # fagioli->fagiolo, pinoli->pinolo
                wl = wl[:-1] + "o"
        out.append(wl)
    return " ".join(out)


def match_livello2(nome: str) -> Optional[str]:
    """
    Livello 2: keyword matching sul nome commerciale.
    Restituisce il nome canonico se trovato con confidenza alta.
    Cerca prima match esatto, poi match parziale. Insensibile a singolare/plurale.
    Ogni keyword deve iniziare dove NON c'è una lettera prima (cifre e simboli
    valgono da separatore: "24RIGATONI" matcha "rigatoni"); quelle CORTE (≤3,
    es. "te", "evo") anche finire senza lettera dopo. Per sottostringa pura
    "te" era dentro "torte"/"paste"/"palette", "orata" dentro "decorate",
    "cola" dentro "cioccolattati" → canonici assurdi ("804 PALETTE" → "Tè",
    "TAPPI GRANDI" → "Tè" — bug storico in STATO.md, riprodotto live il
    02/07/2026 e verificato su 3.694 righe fattura reali: 93 falsi canonici
    eliminati, 1 sola perdita vera recuperata con la keyword "tea").
    """
    nome_lower = nome.lower().strip()
    varianti = {nome_lower, _singolarizza(nome_lower)}

    def _kw_presente(kw: str) -> bool:
        k = kw.strip()
        pre = r"(?<![a-zà-ÿ])"
        suffisso = r"(?![a-zà-ÿ])" if len(k) <= 3 else ""
        rx = re.compile(pre + re.escape(k) + suffisso)
        return any(rx.search(v) for v in varianti)

    # Primo passaggio: match parziale ordinato per specificità (keyword più lunghe prima)
    candidati = []
    for canonico, keywords in INGREDIENTI_CANONICI.items():
        for kw in keywords:
            if _kw_presente(kw):
                candidati.append((canonico, kw, len(kw)))

    if not candidati:
        return None

    # Scegli il candidato con keyword più lunga (più specifica)
    candidati.sort(key=lambda x: -x[2])
    return _consolida_canonico(candidati[0][0])


async def match_livello1(nome: str) -> Optional[str]:
    """
    Livello 1: cerca nel nome_mapping (mapping manuale o confermato da utente).
    """
    key = nome.lower().strip()[:200]
    doc = await db.nome_mapping.find_one({"descrizione_key": key}, {"_id": 0, "nome_canc": 1})
    return doc.get("nome_canc") if doc else None


async def match_livello3_llm(nome: str) -> Optional[str]:
    """
    Livello 3: LLM (Claude Sonnet) per i casi che L1 e L2 non risolvono.
    Usa un singolo prompt per ottenere il nome cucina dell'ingrediente.
    """
    try:
        import httpx

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 50,
                    "system": (
                        "Sei un esperto di terminologia culinaria italiana. "
                        "Dato il nome commerciale di un prodotto alimentare presente in una fattura, "
                        "rispondi SOLO con il nome generico usato in cucina (es: 'farina 00', 'olio extravergine', 'petto di pollo'). "
                        "Massimo 4 parole, minuscolo. Se non è un alimento, rispondi 'non-alimentare'."
                    ),
                    "messages": [{"role": "user", "content": f"Nome prodotto fattura: '{nome}'"}],
                },
            )
            data = r.json()
            risposta = data.get("content", [{}])[0].get("text", "")
            return risposta.strip().lower() if risposta else None

    except Exception as e:
        logger.warning(f"[L3] LLM fallito per '{nome}': {e}")
        return None


async def normalizza_ingrediente(nome: str, usa_llm: bool = True) -> dict:
    """
    Pipeline completa di normalizzazione:
    L1 → L2 → L3(opzionale)
    Restituisce {'ingrediente_canonico', 'livello', 'confidenza'}
    """
    # L1 — mapping manuale
    l1 = await match_livello1(nome)
    if l1:
        return {"ingrediente_canonico": _consolida_canonico(l1), "livello": 1, "confidenza": "alta"}

    # L2 — keyword matching
    l2 = match_livello2(nome)
    if l2:
        canc = _consolida_canonico(l2)
        await _impara_mapping(nome, canc)
        return {"ingrediente_canonico": canc, "livello": 2, "confidenza": "alta"}

    # L3 — LLM (solo se richiesto e nome significativo)
    if usa_llm and len(nome) >= 5:
        l3 = await match_livello3_llm(nome)
        if l3 and l3 != "non-alimentare":
            canc = _consolida_canonico(l3)
            await _impara_mapping(nome, canc)
            return {"ingrediente_canonico": canc, "livello": 3, "confidenza": "media"}

    return {"ingrediente_canonico": None, "livello": 0, "confidenza": "nessuna"}


# ==================== ENDPOINT ====================


@router.get("/cerca")
async def cerca_ingrediente(
    q: str = Query(..., min_length=2),
    per_fornitore: bool = Query(
        False, description="Raggruppa per fornitore invece che per ingrediente"
    ),
):
    """
    Ricerca semantica a 3 livelli nel dizionario prodotti.
    Cerca per nome commerciale E per ingrediente canonico.

    Es: q='farina' trova 'FARINA 00 MOLINO ROSSO KG25', 'FARINA MANITOBA W330', ecc.
    """
    q_lower = q.lower().strip()

    # Regex MongoDB: match sul nome_normalizzato (nome commerciale)
    regex = {"$regex": q_lower, "$options": "i"}

    # Trova anche tutti i prodotti con ingrediente_canonico che contiene q
    prodotti_raw = (
        await db.dizionario_prodotti.find(
            {
                "$or": [
                    {"nome_normalizzato": regex},
                    {"nome_originale": regex},
                    {"ingrediente_canonico": regex},
                ],
                "prezzo_kg": {"$gt": 0},
            },
            {"_id": 0},
        )
        .sort("prezzo_kg", 1)
        .limit(100)
        .to_list(100)
    )

    # Arricchisci ogni prodotto con ingrediente_canonico.
    # SEMPRE ricalcola con L2 (ignora il valore storicamente salvato se L2 trova qualcosa
    # di più specifico — evita il caso "Farina 00" categorizzato come "Farina").
    # L1 in UN colpo solo con $in: era una find_one per risultato (fino a 100
    # query per battitura di autocomplete).
    chiavi_l1 = [
        (p.get("nome_originale") or p.get("nome_normalizzato", "")).lower().strip()[:200]
        for p in prodotti_raw
    ]
    mappa_l1 = {}
    if chiavi_l1:
        async for m in db.nome_mapping.find(
            {"descrizione_key": {"$in": chiavi_l1}}, {"_id": 0, "descrizione_key": 1, "nome_canc": 1}
        ):
            mappa_l1[m["descrizione_key"]] = m.get("nome_canc")
    for p in prodotti_raw:
        nome = p.get("nome_originale") or p.get("nome_normalizzato", "")

        # L1 (mapping manuale) ha la precedenza assoluta
        l1 = mappa_l1.get(nome.lower().strip()[:200])
        if l1:
            p["ingrediente_canonico"] = _consolida_canonico(l1)
        else:
            # L2: ricalcola sempre per ottenere la categoria più specifica
            l2 = match_livello2(nome)
            if l2:
                p["ingrediente_canonico"] = l2  # già consolidato da match_livello2
            elif p.get("ingrediente_canonico"):
                # Nessun match: consolida comunque il valore salvato (orfani legacy
                # 'Nocciola' → chiave 'Nocciole'). Solo chiavi esistenti, zero invenzioni.
                p["ingrediente_canonico"] = _consolida_canonico(p["ingrediente_canonico"])

        # Calcola prezzo effettivo
        prezzo_kg = float(p.get("prezzo_kg") or 0)
        butto = float(p.get("butto_percentuale") or 0)
        p["prezzo_effettivo_kg"] = (
            round(prezzo_kg / (1 - butto / 100), 4) if butto < 100 else prezzo_kg
        )

    if per_fornitore:
        return prodotti_raw

    # Raggruppa per ingrediente_canonico
    gruppi: dict = {}
    senza_canonico = []
    for p in prodotti_raw:
        canc = p.get("ingrediente_canonico")
        if canc:
            if canc not in gruppi:
                gruppi[canc] = []
            gruppi[canc].append(p)
        else:
            senza_canonico.append(p)

    # ── Merge gruppi correlati ───────────────────────────────────────────────
    # Se la query è un termine generico (es: "farina") e ci sono più gruppi
    # che contengono quel termine nel canonico (es: "Farina", "Farina 00",
    # "Farina Manitoba"), li fondiamo in un unico gruppo più generico.
    if len(gruppi) > 1:
        related = [k for k in gruppi if q_lower in k.lower()]
        if len(related) > 1:
            # Il gruppo padre è quello col nome più corto (più generico)
            parent = min(related, key=len)
            merged: list = []
            for k in related:
                merged.extend(gruppi.pop(k))
            gruppi[parent] = merged
    # ────────────────────────────────────────────────────────────────────────

    return {
        "query": q,
        "gruppi": [
            {
                "ingrediente": canc,
                "prodotti": sorted(prods, key=lambda x: x.get("prezzo_effettivo_kg") or 999),
                "prezzo_min": min((p.get("prezzo_effettivo_kg") or 0) for p in prods),
                "n_fornitori": len(set(p.get("fornitore", "") for p in prods)),
            }
            for canc, prods in sorted(gruppi.items())
        ],
        "senza_categoria": senza_canonico,
        "totale": len(prodotti_raw),
    }


@router.get("/confronto-fornitori")
async def confronto_fornitori(
    ingrediente: str = Query(..., min_length=2), includi_esclusi: bool = Query(False)
):
    """
    Confronta tutti i fornitori per lo stesso ingrediente canonico.
    Ordina per prezzo_effettivo_kg = prezzo_kg / (1 - butto% / 100).

    Es: ingrediente='olio extravergine' → lista fornitori con prezzi effettivi.
    """
    q_lower = ingrediente.lower().strip()

    # Fornitori esclusi
    esclusi_doc = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(500)
    fornitori_esclusi = {f["nome"].lower() for f in esclusi_doc}

    from datetime import datetime, timedelta

    due_mesi_fa = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    prodotti = await db.dizionario_prodotti.find(
        {
            "$or": [
                {"ingrediente_canonico": {"$regex": q_lower, "$options": "i"}},
                {"nome_normalizzato": {"$regex": q_lower, "$options": "i"}},
                {"nome_originale": {"$regex": q_lower, "$options": "i"}},
            ],
            "prezzo_kg": {"$gt": 0},
        },
        {"_id": 0},
    ).to_list(200)

    risultati = []
    for p in prodotti:
        fornitore = p.get("fornitore", "")
        if not includi_esclusi and fornitore.lower() in fornitori_esclusi:
            continue

        # Filtra fatture più vecchie di 2 mesi
        data_raw = p.get("data_fattura") or p.get("ultimo_aggiornamento") or ""
        data_str = str(data_raw)[:10] if data_raw else ""
        try:
            if "/" in data_str:
                dd, mm, yy = data_str.split("/")
                data_iso = f"20{yy}-{mm}-{dd}" if len(yy) == 2 else f"{yy}-{mm}-{dd}"
            else:
                data_iso = data_str
            if data_iso and data_iso < due_mesi_fa:
                continue
        except Exception:
            logger.debug("[ingredienti] errore non bloccante ignorato")

        prezzo_kg = float(p.get("prezzo_kg") or 0)
        butto = float(p.get("butto_percentuale") or 0)
        prezzo_eff = (
            round(prezzo_kg / (1 - butto / 100), 4) if butto > 0 and butto < 100 else prezzo_kg
        )

        risultati.append(
            {
                "id": p.get("id"),
                "nome_commerciale": p.get("nome_originale") or p.get("nome_normalizzato"),
                "fornitore": fornitore,
                "prezzo_kg": prezzo_kg,
                "butto_percentuale": butto,
                "prezzo_effettivo_kg": prezzo_eff,
                "unita_confezione": p.get("unita_confezione", "kg"),
                "peso_confezione": float(p.get("peso_confezione") or 1),
                "ultima_fattura_data": p.get("data_fattura")
                or p.get("ultima_fattura_data")
                or p.get("ultimo_aggiornamento", ""),
                "ingrediente_canonico": p.get("ingrediente_canonico", ""),
            }
        )

    # Ordina per prezzo effettivo
    risultati.sort(key=lambda x: x["prezzo_effettivo_kg"])

    # KPI butto medio per fornitore
    butto_per_fornitore: dict = {}
    for r in risultati:
        f = r["fornitore"]
        if f not in butto_per_fornitore:
            butto_per_fornitore[f] = []
        butto_per_fornitore[f].append(r["butto_percentuale"])
    butto_medio = {f: round(sum(v) / len(v), 1) for f, v in butto_per_fornitore.items()}

    return {
        "ingrediente": ingrediente,
        "n_prodotti": len(risultati),
        "prodotti": risultati,
        "butto_medio_per_fornitore": butto_medio,
        "migliore": risultati[0] if risultati else None,
    }


# Cache in-process per smart-search: è un autocomplete (una chiamata per
# battitura da TabIngredienti) e ricaricare 3000 fatture con tutte le righe
# da Atlas a ogni tasto era il collo di bottiglia peggiore percepito.
_SMART_CACHE = {"righe": None, "scade": 0.0}


async def _righe_fatture_recenti():
    """Righe prodotto delle fatture degli ultimi 6 mesi (fornitori esclusi già
    filtrati), appiattite e tenute in cache 120 secondi."""
    import time as _t
    if _SMART_CACHE["righe"] is not None and _t.monotonic() < _SMART_CACHE["scade"]:
        return _SMART_CACHE["righe"]
    from app.lotti.routers.utils import parse_data_flessibile
    sei_mesi_fa = (datetime.now() - timedelta(days=180)).date()

    esclusi_doc = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(500)
    fornitori_esclusi = {
        f["nome"].strip().strip('"').strip("'").strip().lower() for f in esclusi_doc
    }

    righe = []
    async for fattura in db.fatture.find(
        {}, {"_id": 0, "fornitore": 1, "data_fattura": 1, "numero_fattura": 1, "prodotti": 1}
    ):
        fornitore = (fattura.get("fornitore") or "").strip().strip('"').strip("'").strip()
        if fornitore.lower() in fornitori_esclusi:
            continue
        # data_fattura in formati misti: filtro su date vere (senza data → tengo)
        d = parse_data_flessibile(fattura.get("data_fattura"))
        if d and d < sei_mesi_fa:
            continue
        data_fatt = fattura.get("data_fattura", "")
        num_fatt = fattura.get("numero_fattura", "")
        for prod in fattura.get("prodotti") or []:
            desc = (prod.get("descrizione") or "").strip()
            if not desc or len(desc) < 3:
                continue
            righe.append((desc, desc.lower(), fornitore, data_fatt, num_fatt, prod))

    _SMART_CACHE["righe"] = righe
    _SMART_CACHE["scade"] = _t.monotonic() + 120
    return righe


@router.get("/smart-search")
async def smart_search_prodotti(
    q: str = Query(..., min_length=2),
):
    """
    Ricerca INTELLIGENTE in TUTTE le fatture di TUTTI i fornitori.
    Cerca per parole chiave, raggruppa prodotti simili, mostra prezzi per unità e cartone.
    Ignora fornitori esclusi. Mostra solo fatture ultimi 6 mesi.
    """
    # Parole chiave dalla query
    parole = [p.lower().strip() for p in q.split() if len(p) >= 2]
    if not parole:
        return {"q": q, "risultati": [], "totale": 0}

    righe = await _righe_fatture_recenti()

    trovati = []
    seen_keys = set()

    for desc, desc_lower, fornitore, data_fatt, num_fatt, prod in righe:
        # Tutte le parole devono essere presenti
        if not all(p in desc_lower for p in parole):
            continue

        # Dedup per (descrizione normalizzata + fornitore)
        dedup_key = (desc_lower[:40], fornitore.lower()[:20])
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # Estrai prezzo e quantità
        try:
            prezzo_unit = float(str(prod.get("prezzo") or "0").strip().replace(",", "."))
        except Exception as e:
            logging.exception(f"[ingredienti] Errore non gestito: {e}")
            prezzo_unit = 0
        try:
            quantita = float(str(prod.get("quantita") or "0").strip().replace(",", "."))
        except Exception as e:
            logging.exception(f"[ingredienti] Errore non gestito: {e}")
            quantita = 0
        unita = (prod.get("unita_misura") or "").strip().upper()

        # Calcola prezzo totale riga
        prezzo_riga = round(prezzo_unit * quantita, 2) if quantita > 0 else prezzo_unit

        # Estrai pezzi per cartone dal nome (es. "X 24", "x24")
        match_pz = re.search(r"[xX]\s*(\d+)", desc)
        pz_cartone = int(match_pz.group(1)) if match_pz else 0

        # Estrai peso/volume (es. "CL 33", "33cl", "LT 1.5")
        match_ml = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:cl|CL)", desc)
        match_lt = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:lt|LT|L\b)", desc)
        match_kg = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg|KG|Kg)", desc)
        match_gr = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:gr|GR|g\b|G\b)", desc)

        peso_info = ""
        if match_ml:
            peso_info = f"{match_ml.group(1)}cl"
        elif match_lt:
            peso_info = f"{match_lt.group(1)}lt"
        elif match_kg:
            peso_info = f"{match_kg.group(1)}kg"
        elif match_gr:
            peso_info = f"{match_gr.group(1)}g"

        # Prezzo per pezzo se cartone
        prezzo_pezzo = round(prezzo_unit / pz_cartone, 4) if pz_cartone > 1 else prezzo_unit
        prezzo_cartone = prezzo_unit if pz_cartone > 1 else 0

        trovati.append(
            {
                "descrizione": desc,
                "fornitore": fornitore,
                "data_fattura": data_fatt,
                "numero_fattura": num_fatt,
                "prezzo_unitario": round(prezzo_unit, 4),
                "quantita": quantita,
                "unita_misura": unita,
                "prezzo_pezzo": round(prezzo_pezzo, 4),
                "prezzo_cartone": round(prezzo_cartone, 2),
                "pz_cartone": pz_cartone,
                "peso_info": peso_info,
            }
        )

    # Ordina per prezzo pezzo (più economico prima)
    trovati.sort(key=lambda x: x["prezzo_pezzo"] if x["prezzo_pezzo"] > 0 else 9999)

    return {
        "q": q,
        "totale": len(trovati),
        "risultati": trovati,
    }


@router.get("/prezzi-alert")
async def prezzi_alert(soglia: float = Query(15.0)):
    """
    Restituisce mappa {product_id: delta_pct} per prodotti dove il loro ingrediente_canonico
    ha variazione di prezzo > soglia% tra fornitori diversi.
    Usato per badge alert in OrdiniFornitoriView.
    """
    prodotti = await db.dizionario_prodotti.find(
        {
            "prezzo_kg": {"$gte": 0.50, "$lte": 200.0},
            "ingrediente_canonico": {"$exists": True, "$nin": [None, ""]},
        },
        {"_id": 0, "id": 1, "ingrediente_canonico": 1, "prezzo_kg": 1, "fornitore": 1},
    ).to_list(5000)

    # Raggruppa per ingrediente_canonico: un prezzo per fornitore
    per_canc: dict = {}  # {canc: {fornitore: prezzo, ...}}
    id_to_canc: dict = {}  # {product_id: canc}
    for p in prodotti:
        canc = (p.get("ingrediente_canonico") or "").strip()
        pid = p.get("id")
        if not canc or not pid:
            continue
        prezzo = float(p.get("prezzo_kg") or 0)
        fornitore = p.get("fornitore") or ""
        if canc not in per_canc:
            per_canc[canc] = {}
        if fornitore not in per_canc[canc] or per_canc[canc][fornitore] > prezzo:
            per_canc[canc][fornitore] = prezzo
        id_to_canc[pid] = canc

    # Calcola delta per gruppi con ≥2 fornitori
    canc_delta: dict = {}
    for canc, forn_map in per_canc.items():
        if len(forn_map) < 2:
            continue
        prezzi = list(forn_map.values())
        p_min = min(prezzi)
        p_max = max(prezzi)
        if p_min <= 0:
            continue
        delta = (p_max - p_min) / p_min * 100
        # Solo delta realistici (15% - 300%): esclude prodotti diversi stesso canonico
        if soglia <= delta <= 300:
            canc_delta[canc] = round(delta, 1)

    # Mappa product_id → delta_pct
    risultato = {pid: canc_delta[canc] for pid, canc in id_to_canc.items() if canc in canc_delta}
    return risultato


class ButtoPatch(BaseModel):
    butto_percentuale: float  # 0.0 – 99.9


@router.patch("/dizionario/{prodotto_id}/butto")
async def set_butto(prodotto_id: str, payload: ButtoPatch):
    """Imposta la percentuale di scarto (butto) per un prodotto del dizionario."""
    if not (0 <= payload.butto_percentuale < 100):
        raise HTTPException(status_code=400, detail="butto_percentuale deve essere 0-99.9")

    result = await db.dizionario_prodotti.update_one(
        {"id": prodotto_id},
        {
            "$set": {
                "butto_percentuale": payload.butto_percentuale,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    return {"success": True, "butto_percentuale": payload.butto_percentuale}


class MappingManualePayload(BaseModel):
    nome_originale: str
    ingrediente_canonico: str


@router.post("/mapping-manuale")
async def salva_mapping_manuale(payload: MappingManualePayload):
    """
    Salva un mapping confermato dall'utente (L1) e lo applica al prodotto nel dizionario.
    """
    key = payload.nome_originale.lower().strip()[:200]

    await db.nome_mapping.update_one(
        {"descrizione_key": key},
        {
            "$set": {
                "descrizione_key": key,
                "descrizione_originale": payload.nome_originale,
                "nome_canc": payload.ingrediente_canonico,
                "categoria": payload.ingrediente_canonico,
                "fonte": "utente",
                "creato_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    # Aggiorna anche il documento nel dizionario_prodotti
    await db.dizionario_prodotti.update_many(
        {
            "$or": [
                {"nome_originale": payload.nome_originale},
                {"nome_normalizzato": key},
            ]
        },
        {"$set": {"ingrediente_canonico": payload.ingrediente_canonico}},
    )

    return {"success": True, "mapping": {key: payload.ingrediente_canonico}}


@router.post("/normalizza-batch")
async def normalizza_batch(
    usa_llm: bool = Query(False, description="Usa LLM (livello 3) per i prodotti non riconosciuti"),
    solo_mancanti: bool = Query(
        True, description="Processa solo prodotti senza ingrediente_canonico (False = sovrascrive tutto)"
    ),
    limit: int = Query(0, description="Max prodotti da processare (0 = tutti)"),
):
    """
    Job batch: normalizza i prodotti del dizionario assegnando ingrediente_canonico.

    - L1: nome_mapping → L2: keyword (gratis, deterministico) → L3: LLM (solo se usa_llm=True)
    - Scorre a cursore TUTTO il dizionario (niente cap) e scrive in bulk.
    - Passata consigliata sullo storico: prima usa_llm=False + solo_mancanti=False
      (riclassifica tutto gratis e sovrascrive), poi usa_llm=True + solo_mancanti=True
      (LLM solo sul residuo non riconosciuto).
    """
    filtro = {"prezzo_kg": {"$gt": 0}}
    if solo_mancanti:
        filtro["$or"] = [
            {"ingrediente_canonico": {"$exists": False}},
            {"ingrediente_canonico": None},
            {"ingrediente_canonico": ""},
        ]

    risultati = {"l1": 0, "l2": 0, "l3": 0, "non_riconosciuti": 0, "totale": 0}
    ops = []

    async def _flush():
        if ops:
            await db.dizionario_prodotti.bulk_write(ops, ordered=False)
            ops.clear()

    cursor = db.dizionario_prodotti.find(
        filtro, {"_id": 0, "id": 1, "nome_originale": 1, "nome_normalizzato": 1, "ingrediente_canonico": 1}
    )
    risultati["consolidati_salvati"] = 0
    async for p in cursor:
        if limit and risultati["totale"] >= limit:
            break
        nome = p.get("nome_originale") or p.get("nome_normalizzato", "")
        if not nome:
            continue
        risultati["totale"] += 1

        match = await normalizza_ingrediente(nome, usa_llm=usa_llm)

        if match["ingrediente_canonico"]:
            ops.append(PyUpdateOne(
                {"id": p["id"]},
                {"$set": {"ingrediente_canonico": match["ingrediente_canonico"]}},
            ))
            risultati[f"l{match['livello']}"] += 1
        else:
            # Nessun match dal nome: consolida comunque il valore salvato (orfani
            # legacy 'Nocciola' → 'Nocciole'). Aggiorna solo se cambia qualcosa.
            salvato = p.get("ingrediente_canonico")
            cons = _consolida_canonico(salvato) if salvato else None
            if cons and cons != salvato:
                ops.append(PyUpdateOne(
                    {"id": p["id"]}, {"$set": {"ingrediente_canonico": cons}}
                ))
                risultati["consolidati_salvati"] += 1
            else:
                risultati["non_riconosciuti"] += 1
        if len(ops) >= 500:
            await _flush()
    await _flush()

    return {
        "success": True,
        **risultati,
        "messaggio": (
            f"Processati {risultati['totale']} prodotti: "
            f"{risultati['l1']} da mapping manuale, "
            f"{risultati['l2']} da keyword, "
            f"{risultati.get('l3', 0)} da LLM, "
            f"{risultati['non_riconosciuti']} non riconosciuti."
        ),
    }


@router.get("/listino-fornitore")
async def listino_fornitore(
    fornitore: str = Query(..., description="Nome fornitore (es. SAIMA, RONDINELLA)")
):
    """
    Restituisce i prodotti del dizionario filtrati per fornitore.
    Usato da ListinoPasticceria per mostrare il listino per tab fornitore.
    """
    prodotti = (
        await db.dizionario_prodotti.find(
            {"fornitore": {"$regex": fornitore, "$options": "i"}, "prezzo_kg": {"$gt": 0}},
            {"_id": 0},
        )
        .sort("nome_normalizzato", 1)
        .to_list(2000)
    )
    return {"prodotti": prodotti, "fornitore": fornitore, "totale": len(prodotti)}


@router.post("/consolida-canonici")
async def consolida_canonici(limit: int = Query(50000)):
    """Sistema i dati esistenti: applica il consolidamento al campo
    ingrediente_canonico di dizionario_prodotti (es. 'margarina per croissant'
    → 'Margarina', minuscolo → maiuscolo coerente). Deterministico, niente LLM."""
    prodotti = (
        await db.dizionario_prodotti.find(
            {"ingrediente_canonico": {"$nin": [None, ""]}},
            {"_id": 0, "id": 1, "ingrediente_canonico": 1},
        )
        .limit(limit)
        .to_list(limit)
    )
    aggiornati = 0
    cambi: dict = {}
    for p in prodotti:
        old = p.get("ingrediente_canonico")
        new = _consolida_canonico(old)
        if new and new != old:
            await db.dizionario_prodotti.update_one(
                {"id": p["id"]}, {"$set": {"ingrediente_canonico": new}}
            )
            aggiornati += 1
            cambi[old] = new
    return {
        "success": True,
        "esaminati": len(prodotti),
        "aggiornati": aggiornati,
        "esempi": dict(list(cambi.items())[:40]),
    }


@router.get("/openfoodfacts")
async def cerca_openfoodfacts(q: str = Query(..., min_length=2, description="Testo da cercare")):
    """Cerca prodotti su Open Food Facts (database alimentare community).
    SOLO SUGGERIMENTO: i dati sono inseriti dagli utenti, vanno confermati a
    mano. Gli allergeni qui proposti NON sostituiscono la verifica in etichetta."""
    import asyncio
    import json as _json
    import urllib.request
    import urllib.parse

    def _fetch():
        params = {
            "search_terms": q, "search_simple": 1, "action": "process", "json": 1,
            "page_size": 6,
            "fields": "product_name,brands,ingredients_text_it,ingredients_text,allergens_tags",
        }
        url = "https://world.openfoodfacts.org/cgi/search.pl?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "LottiHACCP/1.0 (Ceraldi Group)"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return _json.loads(r.read())

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception:
        raise HTTPException(502, "Open Food Facts non raggiungibile, riprova")

    risultati = []
    for p in (data.get("products") or [])[:6]:
        nome = (p.get("product_name") or "").strip()
        if not nome:
            continue
        allerg = [a.split(":")[-1].replace("-", " ") for a in (p.get("allergens_tags") or [])]
        risultati.append({
            "nome": nome,
            "marca": (p.get("brands") or "").strip(),
            "ingredienti": (p.get("ingredients_text_it") or p.get("ingredients_text") or "").strip(),
            "allergeni": allerg,
        })
    return {"ok": True, "risultati": risultati, "nota": "Dati Open Food Facts (community): da confermare."}
