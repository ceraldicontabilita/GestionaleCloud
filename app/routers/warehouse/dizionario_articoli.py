"""
Router per Dizionario Articoli - Mappatura Prodotti a Piano dei Conti e HACCP

Funzionalità:
1. Estrazione automatica articoli unici dalle fatture
2. Categorizzazione automatica con pattern matching
3. Mappatura a Piano dei Conti per contabilità
4. Mappatura a categorie HACCP per tracciabilità alimentare
5. Interfaccia CRUD per gestione manuale mappature
"""
from fastapi import APIRouter, HTTPException, Query, Body, Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import re
import logging
from uuid import uuid4

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


def safe_parse_float(value) -> float:
    """Converte in modo sicuro qualsiasi valore in float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            # Rimuovi spazi e converti virgola in punto
            cleaned = value.strip().replace(',', '.')
            return float(cleaned) if cleaned else 0.0
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def sum_prices(prices: List) -> float:
    """Somma in modo sicuro una lista di prezzi."""
    total = 0.0
    for p in prices:
        total += safe_parse_float(p)
    return total


# ============== CATEGORIE HACCP ==============
CATEGORIE_HACCP = {
    "carni_fresche": {
        "nome": "Carni Fresche",
        "descrizione": "Carne bovina, suina, avicola, ovina",
        "temperatura_conservazione": "0-4°C",
        "rischio": "alto",
        "tracciabilita": ["lotto", "origine", "data_macellazione", "scadenza"],
        "ccp": ["temperatura", "separazione_crudo_cotto"]
    },
    "pesce_fresco": {
        "nome": "Pesce e Prodotti Ittici Freschi",
        "descrizione": "Pesce, molluschi, crostacei freschi",
        "temperatura_conservazione": "0-2°C",
        "rischio": "alto",
        "tracciabilita": ["lotto", "zona_pesca", "data_pesca", "scadenza"],
        "ccp": ["temperatura", "catena_freddo", "parassiti"]
    },
    "latticini": {
        "nome": "Latticini e Derivati del Latte",
        "descrizione": "Latte, formaggi, yogurt, panna, burro",
        "temperatura_conservazione": "0-4°C",
        "rischio": "alto",
        "tracciabilita": ["lotto", "origine_latte", "scadenza"],
        "ccp": ["temperatura", "pastorizzazione"]
    },
    "uova": {
        "nome": "Uova e Ovoprodotti",
        "descrizione": "Uova fresche, tuorli, albumi pastorizzati",
        "temperatura_conservazione": "4-8°C",
        "rischio": "alto",
        "tracciabilita": ["lotto", "codice_allevamento", "categoria", "scadenza"],
        "ccp": ["temperatura", "salmonella"]
    },
    "frutta_verdura": {
        "nome": "Frutta e Verdura Fresca",
        "descrizione": "Ortaggi, frutta fresca, erbe aromatiche",
        "temperatura_conservazione": "4-8°C",
        "rischio": "medio",
        "tracciabilita": ["lotto", "origine", "produttore"],
        "ccp": ["lavaggio", "conservazione"]
    },
    "surgelati": {
        "nome": "Prodotti Surgelati",
        "descrizione": "Alimenti congelati e surgelati",
        "temperatura_conservazione": "≤-18°C",
        "rischio": "medio",
        "tracciabilita": ["lotto", "data_congelamento", "scadenza"],
        "ccp": ["catena_freddo", "scongelamento"]
    },
    "prodotti_forno": {
        "nome": "Prodotti da Forno e Pasticceria",
        "descrizione": "Pane, dolci, cornetti, pasticceria fresca",
        "temperatura_conservazione": "ambiente o refrigerato",
        "rischio": "medio",
        "tracciabilita": ["lotto", "data_produzione", "allergeni"],
        "ccp": ["cottura", "conservazione", "allergeni"]
    },
    "farine_cereali": {
        "nome": "Farine e Cereali",
        "descrizione": "Farina, semola, cereali, riso, pasta secca",
        "temperatura_conservazione": "ambiente",
        "rischio": "basso",
        "tracciabilita": ["lotto", "origine_grano", "scadenza"],
        "ccp": ["stoccaggio_asciutto", "parassiti"]
    },
    "conserve_scatolame": {
        "nome": "Conserve e Scatolame",
        "descrizione": "Pomodori pelati, legumi, tonno, sottoli",
        "temperatura_conservazione": "ambiente",
        "rischio": "basso",
        "tracciabilita": ["lotto", "scadenza"],
        "ccp": ["integrita_confezione"]
    },
    "bevande_analcoliche": {
        "nome": "Bevande Analcoliche",
        "descrizione": "Acqua, succhi, soft drink, the, caffè",
        "temperatura_conservazione": "ambiente o refrigerato",
        "rischio": "basso",
        "tracciabilita": ["lotto", "scadenza"],
        "ccp": ["conservazione"]
    },
    "bevande_alcoliche": {
        "nome": "Bevande Alcoliche",
        "descrizione": "Vino, birra, liquori, aperitivi",
        "temperatura_conservazione": "ambiente controllato",
        "rischio": "basso",
        "tracciabilita": ["lotto", "annata", "denominazione"],
        "ccp": ["conservazione"]
    },
    "spezie_condimenti": {
        "nome": "Spezie e Condimenti",
        "descrizione": "Sale, olio, aceto, spezie, aromi",
        "temperatura_conservazione": "ambiente",
        "rischio": "basso",
        "tracciabilita": ["lotto", "scadenza"],
        "ccp": ["stoccaggio"]
    },
    "salumi_insaccati": {
        "nome": "Salumi e Insaccati",
        "descrizione": "Prosciutto, salame, mortadella, wurstel",
        "temperatura_conservazione": "0-4°C",
        "rischio": "alto",
        "tracciabilita": ["lotto", "origine", "scadenza", "nitrati"],
        "ccp": ["temperatura", "listeria"]
    },
    "dolciumi_snack": {
        "nome": "Dolciumi e Snack",
        "descrizione": "Cioccolato, caramelle, biscotti, snack",
        "temperatura_conservazione": "ambiente",
        "rischio": "basso",
        "tracciabilita": ["lotto", "scadenza", "allergeni"],
        "ccp": ["allergeni"]
    },
    "additivi_ingredienti": {
        "nome": "Additivi e Ingredienti Speciali",
        "descrizione": "Lieviti, addensanti, coloranti, aromi",
        "temperatura_conservazione": "come da etichetta",
        "rischio": "basso",
        "tracciabilita": ["lotto", "scadenza", "scheda_tecnica"],
        "ccp": ["dosaggio"]
    },
    "non_alimentare": {
        "nome": "Prodotti Non Alimentari",
        "descrizione": "Detersivi, imballaggi, attrezzature, servizi",
        "temperatura_conservazione": "N/A",
        "rischio": "N/A",
        "tracciabilita": [],
        "ccp": []
    }
}


# ============== PATTERN MATCHING ARTICOLI ==============
PATTERNS_ARTICOLI = {
    # UOVA E OVOPRODOTTI
    "uova": {
        "patterns": [
            r"uov[ao]", r"ovoprodott", r"tuorlo", r"albume", r"cat\.?\s*a",
            r"gallina", r"allevamento.*terra"
        ],
        "categoria_haccp": "uova",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # LATTICINI
    "latticini": {
        "patterns": [
            r"latte\b", r"mozzarell", r"ricotta", r"panna", r"burro",
            r"formaggio", r"gorgonzola", r"parmigiano", r"grana\s+padano",
            r"provola", r"provolone", r"stracchino", r"mascarpone",
            r"yogurt", r"fiordilatte", r"fior\s+di\s+latte", r"scamorza"
        ],
        "categoria_haccp": "latticini",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # CARNI
    "carni": {
        "patterns": [
            r"carn[ei]", r"bovino", r"suino", r"maiale", r"pollo", r"tacchino",
            r"vitello", r"agnello", r"manzo", r"bistecca", r"filetto",
            r"salsiccia", r"cotoletta", r"hamburger", r"polpett"
        ],
        "categoria_haccp": "carni_fresche",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # SALUMI
    "salumi": {
        "patterns": [
            r"prosciutto", r"salame", r"mortadella", r"wurstel", r"bresaola",
            r"speck", r"pancetta", r"guanciale", r"coppa", r"culatello",
            r"nduja", r"soppressata", r"capocollo", r"cervellatina",
            r"fiorucci", r"cotto\s+vellutato", r"hirschsalami", r"salami"
        ],
        "categoria_haccp": "salumi_insaccati",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # PESCE
    "pesce": {
        "patterns": [
            r"pesce", r"tonno", r"salmone", r"merluzzo", r"baccal[aà]",
            r"gamberi", r"calamari", r"cozze", r"vongole", r"aragosta",
            r"orata", r"branzino", r"sogliola", r"acciughe", r"alice",
            r"polpo", r"seppie", r"frutti\s+di\s+mare", r"crostacei"
        ],
        "categoria_haccp": "pesce_fresco",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # FRUTTA
    "frutta": {
        "patterns": [
            r"aranc[ei]", r"limon[ei]", r"mela\b", r"mele\b", r"pera\b", r"pere\b",
            r"banana", r"fragol", r"lamponi", r"mirtilli", r"ananas",
            r"kiwi", r"mango", r"avocado", r"melogran", r"pompelm",
            r"uva\b", r"pesche", r"albicocche", r"ciliegie", r"melone",
            r"anguria", r"cocomer", r"lime", r"frutta\b", r"succo"
        ],
        "categoria_haccp": "frutta_verdura",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # VERDURA
    "verdura": {
        "patterns": [
            r"pomodor", r"zucchin", r"melanzane", r"peperon", r"insalata",
            r"lattuga", r"iceberg", r"rucola", r"spinaci", r"scarola",
            r"friarielli", r"broccoli", r"cavolfiore", r"cavolo", r"verza",
            r"carote", r"patate", r"patata", r"cipolle", r"aglio", r"sedano",
            r"finocchi", r"carciofi", r"asparagi", r"funghi", r"tartufo",
            r"verdur", r"ortaggi", r"menta\b", r"basilico", r"prezzemolo",
            r"misticanza", r"cetrioli", r"cavoli\b", r"mais\b", r"bonduelle"
        ],
        "categoria_haccp": "frutta_verdura",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # PRODOTTI DA FORNO / PASTICCERIA
    "pasticceria": {
        "patterns": [
            r"croissant", r"cornett[oi]", r"brioche", r"sfogliat",
            r"ciambella", r"danish", r"muffin", r"plumcake", r"crostata",
            r"bab[aà]", r"past[ai]ccer", r"torta", r"pan\s*di\s*spagna",
            r"pan\s*brioche", r"tappi", r"treccina", r"fagottino",
            r"coda.*aragosta", r"rosettine", r"ciabatta", r"focaccia",
            r"pane\b", r"panino", r"biscott", r"frollini", r"wafer",
            r"krapfen", r"rustica", r"classica\s+gr", r"sfogl.*nap",
            r"cannoli", r"caruso", r"superfarcito", r"mignon"
        ],
        "categoria_haccp": "prodotti_forno",
        "conto": "05.01.11",
        "conto_nome": "Acquisto prodotti da forno"
    },
    
    # FARINE E SEMOLE
    "farine": {
        "patterns": [
            r"farina", r"semola", r"semolato", r"manitoba", r"integrale",
            r"grano\b", r"frumento", r"caputo", r"tipo\s*00", r"tipo\s*0",
            r"lievito", r"lievitazione", r"pasta\s+sfoglia", r"amido",
            r"artecrema"
        ],
        "categoria_haccp": "farine_cereali",
        "conto": "05.01.02",
        "conto_nome": "Acquisto materie prime"
    },
    
    # SURGELATI
    "surgelati": {
        "patterns": [
            r"surgelat", r"congelat", r"frozen", r"master\s*frost",
            r"findus", r"orogel", r"surgital", r"\-18", r"cubetti\s+misti"
        ],
        "categoria_haccp": "surgelati",
        "conto": "05.01.10",
        "conto_nome": "Acquisto surgelati"
    },
    
    # CAFFE
    "caffe": {
        "patterns": [
            r"caff[eè]", r"kimbo", r"lavazza", r"illy", r"segafredo",
            r"borbone", r"nespresso", r"espresso", r"ginseng", r"orzo",
            r"cappuccin", r"tazzina", r"tazza.*vetro", r"toraldo",
            r"cialde", r"origini\s+box"
        ],
        "categoria_haccp": "bevande_analcoliche",
        "conto": "05.01.09",
        "conto_nome": "Acquisto caffè e affini"
    },
    
    # BEVANDE ANALCOLICHE
    "bevande_analcoliche": {
        "patterns": [
            r"coca[\s-]*cola", r"pepsi", r"fanta", r"sprite",
            r"aranciata", r"chinotto", r"chin8", r"estathe", r"the\b", r"tè\b",
            r"succo", r"yoga", r"red\s*bull", r"monster", r"gatorade",
            r"limonata", r"cedrata", r"energy\s*drink", r"natia", r"sorgesana",
            r"lemonsoda", r"schweppes", r"tonic[ao]", r"fever\s*tree",
            r"crodino", r"sanbitter", r"cocktail\s+rosso", r"sanpellegrino",
            r"ferrarelle", r"lete\b", r"vitasnella", r"lilia", r"san\s*benedetto",
            r"primavera", r"cl\s*\d+\s*x\s*\d+.*pet", r"cl\s*\d+\s*x\s*\d+.*vap"
        ],
        "categoria_haccp": "bevande_analcoliche",
        "conto": "05.01.04",
        "conto_nome": "Acquisto bevande analcoliche"
    },
    
    # ACQUA MINERALE (separato per maggiore precisione)
    "acqua": {
        "patterns": [
            r"acqua\b", r"ferrarelle", r"lete\b", r"vitasnella", r"lilia\b",
            r"san\s*benedetto", r"levissima", r"sant['']?anna", r"panna\b",
            r"primavera\s+cl", r"naturale\s+lt", r"frizzante\s+lt"
        ],
        "categoria_haccp": "bevande_analcoliche",
        "conto": "05.01.04",
        "conto_nome": "Acquisto bevande analcoliche"
    },
    
    # BEVANDE ALCOLICHE
    "bevande_alcoliche": {
        "patterns": [
            r"birra", r"peroni", r"heineken", r"ceres", r"beck", r"tourtel",
            r"vino\b", r"prosecco", r"champagne", r"spumante",
            r"aperol", r"campari", r"spritz", r"amaro", r"limoncello",
            r"grappa", r"vodka", r"rum\b", r"whisky", r"gin\b",
            r"liquore", r"digestivo", r"sambuca", r"fusti\b",
            r"baileys", r"punt.*mes", r"irish\s+cream",
            r"l['']?ape\b", r"bagnoli", r"aperitivo.*cl",
            r"bianco\s+sarti", r"passoa", r"sciroppo.*cl",
            r"kbirr", r"cuore\s+di\s+napoli", r"n['']?artigiana"
        ],
        "categoria_haccp": "bevande_alcoliche",
        "conto": "05.01.03",
        "conto_nome": "Acquisto bevande alcoliche"
    },
    
    # CONSERVE
    "conserve": {
        "patterns": [
            r"pelati", r"polpa\s+pomodoro", r"passata", r"concentrato",
            r"sottoli", r"sottacet", r"olive", r"capperi", r"carciofi.*olio",
            r"confettur", r"marmellat", r"miele\b", r"nutella",
            r"crema.*nocciole", r"torrente", r"fagioli", r"borlotti",
            r"legumi", r"ceci", r"lenticchie", r"piselli"
        ],
        "categoria_haccp": "conserve_scatolame",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # SPEZIE E CONDIMENTI
    "condimenti": {
        "patterns": [
            r"olio\b", r"olio.*oliva", r"aceto", r"sale\b", r"pepe\b",
            r"origano", r"rosmarino", r"salvia", r"timo", r"maggiorana",
            r"curry", r"paprika", r"zafferano", r"noce\s*moscata",
            r"senape", r"ketchup", r"maionese", r"salsa"
        ],
        "categoria_haccp": "spezie_condimenti",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # DOLCIUMI, GOMME E CARAMELLE
    "dolciumi": {
        "patterns": [
            r"cioccolat", r"caramell", r"gomme", r"chewing", r"vigorsol",
            r"mentos", r"snack", r"patatine", r"chips", r"cracker",
            r"frisk", r"vivident", r"viv\.", r"brooklyn", r"golia",
            r"morositas", r"tic\s*tac", r"big\s*babol", r"happydent",
            r"chloroph", r"spearmint", r"peppermint", r"extra\s+strong",
            r"air\s+action", r"activ\s+plus", r"daygum", r"protex",
            r"alpenliebe", r"vig\.\s*aa", r"black\s+ice"
        ],
        "categoria_haccp": "dolciumi_snack",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # INGREDIENTI PASTICCERIA E GELATERIA
    "ingredienti_pasticceria": {
        "patterns": [
            r"zucchero", r"zucch.*velo", r"impalpabile", r"neve\s+bianca",
            r"gelatina", r"gelina", r"agar", r"pectina",
            r"mandorl", r"nocciole", r"granella", r"pistacchi",
            r"cioccolato.*copertura", r"surrogato", r"fondente",
            r"crema.*rio", r"crema.*spalmabile", r"amarena",
            r"visciola", r"margar", r"margarina", r"wiener",
            r"melange", r"homillina", r"gateaux", r"mix\s+cake",
            r"base\s+pasta", r"plunder", r"pirottini?", r"sottogeli",
            r"sac\s+a\s+poche"
        ],
        "categoria_haccp": "additivi_ingredienti",
        "conto": "05.01.13",
        "conto_nome": "Additivi e ingredienti alimentari"
    },
    
    # GRASSI E OLI DA CUCINA
    "grassi": {
        "patterns": [
            r"strutto", r"margarina", r"burro\s+fuso", r"olio.*semi",
            r"olio.*frittura", r"papillon", r"raffinato"
        ],
        "categoria_haccp": "spezie_condimenti",
        "conto": "05.01.02",
        "conto_nome": "Acquisto materie prime"
    },
    
    # PRODOTTI VEGETALI / SOIA
    "vegetali_soia": {
        "patterns": [
            r"soya", r"soia", r"valsoia", r"avena\s+drink", r"latte.*soia",
            r"latte.*avena", r"latte.*riso", r"hopla", r"vegetale.*ml",
            r"prep.*veget"
        ],
        "categoria_haccp": "latticini",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # ADDITIVI E INGREDIENTI SPECIALI
    "additivi": {
        "patterns": [
            r"nuppy", r"olva", r"thermos", r"crema\s+gateaux",
            r"preparato", r"base\s+per", r"mix\s+per", r"aroma",
            r"estratto", r"vanillina", r"addensante", r"pectina",
            r"est\.\s*zuppa", r"zuppa\s+inglese"
        ],
        "categoria_haccp": "additivi_ingredienti",
        "conto": "05.01.13",
        "conto_nome": "Additivi e ingredienti alimentari"
    },
    
    # PULIZIA
    "pulizia": {
        "patterns": [
            r"detersivo", r"detergente", r"igienizzant", r"disinfettant",
            r"sapone", r"candeggina", r"alcol", r"ammorbident",
            r"carta\s*igienica", r"rotoli.*carta", r"asciugamani\s*carta",
            r"tovaglio", r"sacchetti", r"dealo", r"panno\s*micr",
            r"ecochem", r"ecospot", r"big\s*matik", r"big\s*brill",
            r"brillantante", r"lavast", r"chanteclair", r"sgrassatore",
            r"wettex", r"alba\s+pavimenti", r"alba\s+lavapavimenti",
            r"liq.*piatti"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.01.08",
        "conto_nome": "Prodotti per pulizia e igiene"
    },
    
    # IMBALLAGGI E CONTENITORI
    "imballaggi": {
        "patterns": [
            r"imballag", r"confezioni", r"vassoi", r"scatole",
            r"buste\b", r"shopper", r"pellicola", r"alluminio",
            r"carta\s*forno", r"busta\s+shop", r"bicch.*vetro",
            r"bicch.*rock", r"bicchier", r"bicch.*oslo", r"bicch.*after",
            r"tovaglia", r"tovaglio", r"sacchi\s+ambra", r"boxone",
            r"theiera", r"teiera"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.01.07",
        "conto_nome": "Materiali di consumo e imballaggio"
    },
    
    # TRASPORTO
    "trasporto": {
        "patterns": [
            r"trasporto", r"spedizione", r"spese\s*fisse", r"consegna",
            r"corriere"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.16",
        "conto_nome": "Trasporti su acquisti"
    },
    
    # UTENZE ELETTRICITA
    "utenze_elettricita": {
        "patterns": [
            r"energia\s*elettrica", r"kwh", r"potenza", r"kilowatt",
            r"accisa\s*energia", r"spesa\s+per\s+l['']?energia",
            r"spesa\s+oneri\s+di\s+sistema", r"energia\s+fascia\s+f",
            r"perdite\s+di\s+rete", r"quota\s+energ", r"quota\s+fissa",
            r"ore\s+picco", r"ore\s+fuori\s+picco", r"arim\b"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.05",
        "conto_nome": "Utenze - Energia elettrica"
    },
    
    # TELEFONIA
    "telefonia": {
        "patterns": [
            r"fastweb", r"tim\b", r"vodafone", r"wind", r"fibra",
            r"wi-?fi", r"telefon", r"sim\b", r"mobile"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.07",
        "conto_nome": "Telefonia e comunicazioni"
    },
    
    # NOLEGGIO AUTO E LOCAZIONE
    "noleggio_auto": {
        "patterns": [
            r"stelvio", r"arval", r"leasys", r"noleggio\s*lungo",
            r"canone\s*locazione", r"canone\s*servizi",
            r"gg\d+[a-z]+\s+canone"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.22",
        "conto_nome": "Noleggio automezzi"
    },
    
    # COMMISSIONI POS E BANCARIE
    "commissioni_pos": {
        "patterns": [
            r"canone\s+mensile\s+pos", r"comm.*tecnica", r"comm.*minima",
            r"comm.*%.*pos", r"pagobcm", r"storno\s+comm", r"sc\s+op\s+fino",
            r"pos\s+cless"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.18",
        "conto_nome": "Commissioni bancarie e POS"
    },
    
    # SERVIZI E FATTURAZIONE
    "servizi": {
        "patterns": [
            r"servizio.*produzione", r"servizio.*invio\s+fattura",
            r"imposta\s+di\s+bollo", r"bollo\b", r"riga\s+ausiliaria",
            r"fornitura\s+\d+", r"importo\s+totale\s+iva", r"riaccredit",
            r"corrispettiv", r"prontotimas", r"manutenzione"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.01",
        "conto_nome": "Costi per servizi"
    },
    
    # MATERIALE ELETTRICO E FERRAMENTA
    "ferramenta": {
        "patterns": [
            r"schneider", r"interruttore", r"magnetotermico", r"strip\s+led",
            r"led.*\d+w", r"lrs-\d+", r"multispot", r"guarnizion",
            r"raccordo", r"utilfer", r"canne\s+fumarie"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.01.06",
        "conto_nome": "Acquisto piccola utensileria"
    },
    
    # PASTA SECCA
    "pasta": {
        "patterns": [
            r"spaghett", r"penne\b", r"rigatoni", r"fusilli", r"maccheroni",
            r"tagliatelle", r"linguine", r"farfalle", r"orecchiette",
            r"de\s*cecco", r"barilla", r"voiello", r"rummo", r"garofalo"
        ],
        "categoria_haccp": "farine_cereali",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # WURSTEL E AFFETTATI CONFEZIONATI
    "wurstel": {
        "patterns": [
            r"wudy", r"wurstel", r"hot\s*dog", r"frank", r"aia\b"
        ],
        "categoria_haccp": "salumi_insaccati",
        "conto": "05.01.05",
        "conto_nome": "Acquisto prodotti alimentari"
    },
    
    # SCONTI E OMAGGI
    "sconti": {
        "patterns": [
            r"sconto\s+\d+\s+euro", r"omaggi", r"omaggio", r"altri\s+importi"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.99",
        "conto_nome": "Altri costi"
    },
    
    # SPESE VARIE
    "spese_varie": {
        "patterns": [
            r"spese\s*bolli", r"spese\s*fatturazione", r"spese\s*accessorie",
            r"cancelleria", r"articolo\s*vario", r"art.*vario"
        ],
        "categoria_haccp": "non_alimentare",
        "conto": "05.02.01",
        "conto_nome": "Costi per servizi"
    }
}


def categorizza_articolo(descrizione: str) -> Dict[str, Any]:
    """
    Categorizza un articolo in base alla sua descrizione.
    Ritorna categoria HACCP, conto piano dei conti, e confidenza.
    """
    if not descrizione:
        return {
            "categoria_haccp": "non_alimentare",
            "categoria_haccp_nome": "Prodotti Non Alimentari",
            "conto": "05.01.01",
            "conto_nome": "Acquisto merci",
            "confidenza": 0.0,
            "matched_pattern": None
        }
    
    desc_lower = descrizione.lower()
    
    best_match = None
    best_confidenza = 0.0
    
    for cat_key, cat_info in PATTERNS_ARTICOLI.items():
        for pattern in cat_info["patterns"]:
            if re.search(pattern, desc_lower, re.IGNORECASE):
                # Calcola confidenza basata sulla lunghezza del match
                match = re.search(pattern, desc_lower, re.IGNORECASE)
                if match:
                    match_len = len(match.group())
                    confidenza = min(match_len / len(descrizione) * 3, 1.0)  # Normalizza
                    
                    if confidenza > best_confidenza:
                        best_confidenza = confidenza
                        best_match = {
                            "categoria": cat_key,
                            "categoria_haccp": cat_info["categoria_haccp"],
                            "conto": cat_info["conto"],
                            "conto_nome": cat_info["conto_nome"],
                            "pattern": pattern
                        }
    
    if best_match:
        haccp_info = CATEGORIE_HACCP.get(best_match["categoria_haccp"], {})
        return {
            "categoria_haccp": best_match["categoria_haccp"],
            "categoria_haccp_nome": haccp_info.get("nome", best_match["categoria_haccp"]),
            "conto": best_match["conto"],
            "conto_nome": best_match["conto_nome"],
            "confidenza": round(best_confidenza, 2),
            "matched_pattern": best_match["pattern"],
            "rischio_haccp": haccp_info.get("rischio", "N/A"),
            "temperatura": haccp_info.get("temperatura_conservazione", "N/A")
        }
    
    # Default: non classificato
    return {
        "categoria_haccp": "non_alimentare",
        "categoria_haccp_nome": "Non classificato",
        "conto": "05.01.01",
        "conto_nome": "Acquisto merci",
        "confidenza": 0.0,
        "matched_pattern": None
    }


# ============== API ENDPOINTS ==============

@router.get("/estrai-articoli")
async def estrai_articoli_fatture(
    limite: int = Query(1000, description="Numero massimo articoli da estrarre"),
    min_occorrenze: int = Query(1, description="Minimo occorrenze per includere")
) -> Dict[str, Any]:
    """
    Estrae tutti gli articoli unici dalle fatture e li categorizza automaticamente.
    """
    db = Database.get_db()
    
    pipeline = [
        {"$unwind": "$linee"},
        {"$group": {
            "_id": "$linee.descrizione",
            "count": {"$sum": 1},
            "fornitori": {"$addToSet": "$supplier_name"},
            "prezzi": {"$push": "$linee.prezzo_totale"},
            "sample_prezzo": {"$first": "$linee.prezzo_unitario"}
        }},
        {"$match": {
            "_id": {"$ne": None, "$ne": ""},
            "count": {"$gte": min_occorrenze}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limite}
    ]
    
    articoli_raw = await db.invoices.aggregate(pipeline).to_list(limite)
    
    # Categorizza ogni articolo
    articoli = []
    stats = {
        "totale": len(articoli_raw),
        "categorizzati_alta_confidenza": 0,
        "categorizzati_media_confidenza": 0,
        "non_categorizzati": 0,
        "per_categoria_haccp": {},
        "per_conto": {}
    }
    
    for art in articoli_raw:
        desc = art["_id"]
        cat = categorizza_articolo(desc)
        
        # Calcola totale importo dalla lista prezzi
        totale_importo = sum_prices(art.get("prezzi", []))
        
        articolo = {
            "descrizione": desc,
            "occorrenze": art["count"],
            "n_fornitori": len(art.get("fornitori", [])),
            "totale_importo": round(totale_importo, 2),
            **cat
        }
        articoli.append(articolo)
        
        # Statistiche
        if cat["confidenza"] >= 0.5:
            stats["categorizzati_alta_confidenza"] += 1
        elif cat["confidenza"] > 0:
            stats["categorizzati_media_confidenza"] += 1
        else:
            stats["non_categorizzati"] += 1
        
        # Per categoria HACCP
        haccp = cat["categoria_haccp"]
        if haccp not in stats["per_categoria_haccp"]:
            stats["per_categoria_haccp"][haccp] = 0
        stats["per_categoria_haccp"][haccp] += 1
        
        # Per conto
        conto = cat["conto"]
        if conto not in stats["per_conto"]:
            stats["per_conto"][conto] = {"count": 0, "nome": cat["conto_nome"]}
        stats["per_conto"][conto]["count"] += 1
    
    return {
        "articoli": articoli,
        "statistiche": stats
    }


@router.get("/categorie-haccp")
async def get_categorie_haccp() -> Dict[str, Any]:
    """
    Ritorna tutte le categorie HACCP disponibili con le loro caratteristiche.
    """
    return {
        "categorie": CATEGORIE_HACCP,
        "totale": len(CATEGORIE_HACCP)
    }


@router.get("/dizionario")
async def get_dizionario(
    skip: int = 0,
    limit: int = 100,
    categoria_haccp: Optional[str] = None,
    non_mappati: bool = False
) -> Dict[str, Any]:
    """
    Recupera il dizionario articoli salvato nel database.
    """
    db = Database.get_db()
    
    query = {}
    if categoria_haccp:
        query["categoria_haccp"] = categoria_haccp
    if non_mappati:
        query["mappatura_manuale"] = {"$ne": True}
    
    items = await db.dizionario_articoli.find(
        query,
        {"_id": 0}
    ).sort("occorrenze", -1).skip(skip).limit(limit).to_list(limit)
    
    total = await db.dizionario_articoli.count_documents(query)
    
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("/genera-dizionario")
async def genera_dizionario() -> Dict[str, Any]:
    """
    Genera/aggiorna il dizionario articoli estraendo dalle fatture
    e applicando la categorizzazione automatica.
    """
    db = Database.get_db()
    
    # Estrai articoli senza calcoli numerici in MongoDB
    pipeline = [
        {"$unwind": "$linee"},
        {"$group": {
            "_id": "$linee.descrizione",
            "count": {"$sum": 1},
            "fornitori": {"$addToSet": "$supplier_name"},
            "prezzi": {"$push": "$linee.prezzo_totale"}
        }},
        {"$match": {"_id": {"$ne": None, "$ne": ""}}},
        {"$sort": {"count": -1}}
    ]
    
    articoli_raw = await db.invoices.aggregate(pipeline).to_list(10000)
    
    created = 0
    updated = 0
    
    for art in articoli_raw:
        desc = art["_id"]
        
        # Controlla se esiste già
        existing = await db.dizionario_articoli.find_one({"descrizione": desc})
        
        # Categorizza
        cat = categorizza_articolo(desc)
        
        # Calcola totale importo in Python
        totale_importo = sum_prices(art.get("prezzi", []))
        
        doc = {
            "descrizione": desc,
            "occorrenze": art["count"],
            "n_fornitori": len(art.get("fornitori", [])),
            "fornitori": art.get("fornitori", [])[:10],
            "totale_importo": round(totale_importo, 2),
            "categoria_haccp": cat["categoria_haccp"],
            "categoria_haccp_nome": cat["categoria_haccp_nome"],
            "conto": cat["conto"],
            "conto_nome": cat["conto_nome"],
            "confidenza": cat["confidenza"],
            "rischio_haccp": cat.get("rischio_haccp", "N/A"),
            "temperatura_conservazione": cat.get("temperatura", "N/A"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            # Mantieni mappature manuali
            if existing.get("mappatura_manuale"):
                doc["mappatura_manuale"] = True
                doc["categoria_haccp"] = existing["categoria_haccp"]
                doc["conto"] = existing["conto"]
                doc["conto_nome"] = existing.get("conto_nome", doc["conto_nome"])
            
            await db.dizionario_articoli.update_one(
                {"descrizione": desc},
                {"$set": doc}
            )
            updated += 1
        else:
            doc["id"] = str(uuid4())
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            doc["mappatura_manuale"] = False
            await db.dizionario_articoli.insert_one(doc.copy())
            created += 1
    
    return {
        "success": True,
        "created": created,
        "updated": updated,
        "total": created + updated
    }


@router.put("/articolo/{descrizione_encoded}")
async def aggiorna_mappatura_articolo(
    descrizione_encoded: str = Path(..., description="Descrizione articolo URL-encoded"),
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna manualmente la mappatura di un articolo.
    """
    db = Database.get_db()
    
    # Decodifica descrizione
    import urllib.parse
    descrizione = urllib.parse.unquote(descrizione_encoded)
    
    # Verifica che l'articolo esista
    existing = await db.dizionario_articoli.find_one({"descrizione": descrizione})
    if not existing:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    
    # Valida categoria HACCP
    if data.get("categoria_haccp") and data["categoria_haccp"] not in CATEGORIE_HACCP and data["categoria_haccp"] != "non_alimentare":
        raise HTTPException(status_code=400, detail=f"Categoria HACCP non valida: {data['categoria_haccp']}")
    
    # Prepara update
    update_data = {
        "mappatura_manuale": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if "categoria_haccp" in data:
        update_data["categoria_haccp"] = data["categoria_haccp"]
        haccp_info = CATEGORIE_HACCP.get(data["categoria_haccp"], {})
        update_data["categoria_haccp_nome"] = haccp_info.get("nome", data["categoria_haccp"])
        update_data["rischio_haccp"] = haccp_info.get("rischio", "N/A")
        update_data["temperatura_conservazione"] = haccp_info.get("temperatura_conservazione", "N/A")
    
    if "conto" in data:
        update_data["conto"] = data["conto"]
    if "conto_nome" in data:
        update_data["conto_nome"] = data["conto_nome"]
    if "note" in data:
        update_data["note"] = data["note"]
    
    await db.dizionario_articoli.update_one(
        {"descrizione": descrizione},
        {"$set": update_data}
    )
    
    # Ritorna articolo aggiornato
    updated = await db.dizionario_articoli.find_one({"descrizione": descrizione}, {"_id": 0})
    return updated


@router.get("/statistiche")
async def get_statistiche_dizionario() -> Dict[str, Any]:
    """
    Statistiche sul dizionario articoli.
    """
    db = Database.get_db()
    
    total = await db.dizionario_articoli.count_documents({})
    manuali = await db.dizionario_articoli.count_documents({"mappatura_manuale": True})
    
    # Per categoria HACCP
    pipeline_haccp = [
        {"$group": {
            "_id": "$categoria_haccp",
            "count": {"$sum": 1},
            "occorrenze_totali": {"$sum": "$occorrenze"}
        }},
        {"$sort": {"count": -1}}
    ]
    per_haccp = await db.dizionario_articoli.aggregate(pipeline_haccp).to_list(50)
    
    # Per conto
    pipeline_conto = [
        {"$group": {
            "_id": "$conto",
            "nome": {"$first": "$conto_nome"},
            "count": {"$sum": 1},
            "importo_totale": {"$sum": "$totale_importo"}
        }},
        {"$sort": {"importo_totale": -1}}
    ]
    per_conto = await db.dizionario_articoli.aggregate(pipeline_conto).to_list(50)
    
    # Per confidenza
    alta_conf = await db.dizionario_articoli.count_documents({"confidenza": {"$gte": 0.5}})
    media_conf = await db.dizionario_articoli.count_documents({
        "confidenza": {"$gt": 0, "$lt": 0.5}
    })
    non_class = await db.dizionario_articoli.count_documents({"confidenza": 0})
    
    return {
        "totale_articoli": total,
        "mappature_manuali": manuali,
        "per_categoria_haccp": per_haccp,
        "per_conto": per_conto,
        "confidenza": {
            "alta": alta_conf,
            "media": media_conf,
            "non_classificati": non_class
        }
    }


@router.post("/ricategorizza-fatture")
async def ricategorizza_fatture_da_dizionario() -> Dict[str, Any]:
    """
    Applica le categorie del dizionario a tutte le fatture.
    Aggiorna categoria_contabile e conto_costo nelle fatture.
    """
    db = Database.get_db()
    
    # Carica dizionario in memoria per velocità
    dizionario = {}
    async for item in db.dizionario_articoli.find({}, {"_id": 0}):
        dizionario[item["descrizione"]] = item
    
    logger.info(f"Dizionario caricato: {len(dizionario)} articoli")
    
    updated = 0
    
    # Processa fatture
    async for fattura in db.invoices.find({"linee": {"$exists": True, "$ne": []}}):
        linee = fattura.get("linee", [])
        
        # Trova categoria dominante (quella con più importo)
        categorie_importi = {}
        for linea in linee:
            desc = linea.get("descrizione", "")
            importo = float(linea.get("prezzo_totale", 0) or 0)
            
            if desc in dizionario:
                cat = dizionario[desc]
                conto = cat["conto"]
                if conto not in categorie_importi:
                    categorie_importi[conto] = {
                        "importo": 0,
                        "conto_nome": cat["conto_nome"],
                        "categoria_haccp": cat["categoria_haccp"]
                    }
                categorie_importi[conto]["importo"] += importo
        
        if categorie_importi:
            # Prendi la categoria con importo maggiore
            best_conto = max(categorie_importi, key=lambda k: categorie_importi[k]["importo"])
            best_info = categorie_importi[best_conto]
            
            await db.invoices.update_one(
                {"_id": fattura["_id"]},
                {"$set": {
                    "conto_costo_codice": best_conto,
                    "conto_costo_nome": best_info["conto_nome"],
                    "categoria_haccp_dominante": best_info["categoria_haccp"],
                    "dizionario_applied_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            updated += 1
    
    return {
        "success": True,
        "fatture_aggiornate": updated,
        "articoli_dizionario": len(dizionario)
    }


@router.get("/cerca")
async def cerca_articoli(
    q: str = Query(..., min_length=2, description="Termine di ricerca"),
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Cerca articoli nel dizionario.
    """
    db = Database.get_db()
    
    items = await db.dizionario_articoli.find(
        {"descrizione": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).sort("occorrenze", -1).limit(limit).to_list(limit)
    
    return items


@router.delete("/reset-dizionario")
async def reset_dizionario() -> Dict[str, Any]:
    """
    Elimina tutto il dizionario (per rigenerarlo).
    """
    db = Database.get_db()
    result = await db.dizionario_articoli.delete_many({})
    return {
        "success": True,
        "deleted": result.deleted_count
    }



@router.post("/categorizza-ai")
async def categorizza_articoli_ai(
    limite: int = Query(50, description="Numero massimo articoli da processare")
) -> Dict[str, Any]:
    """
    Usa GPT-5.2 per categorizzare gli articoli con confidenza 0.
    Aggiorna direttamente il dizionario con le categorie AI.
    """
    try:
        from app.services.ai_categorizzazione import aggiorna_dizionario_con_ai
        db = Database.get_db()
        result = await aggiorna_dizionario_con_ai(db, limite=limite)
        return result
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Servizio AI non disponibile: {str(e)}")
    except Exception as e:
        logger.error(f"Errore categorizzazione AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/non-classificati")
async def get_articoli_non_classificati(
    limite: int = Query(100, description="Numero massimo articoli")
) -> List[Dict[str, Any]]:
    """
    Ritorna gli articoli con confidenza 0, ordinati per occorrenze.
    """
    db = Database.get_db()
    items = await db.dizionario_articoli.find(
        {"confidenza": 0},
        {"_id": 0}
    ).sort("occorrenze", -1).limit(limite).to_list(limite)
    return items
