"""
Utilità condivise tra tutti i router:
- Connessione DB
- Helper date
- Parser XML fatture
- Dizionari allergeni e scadenze
- Funzioni di fuzzy matching
"""
import os, re, uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from fuzzywuzzy import fuzz
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

# ===================== DB =====================
_client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = _client[os.environ['DB_NAME']]

# ===================== HELPER DATE =====================
def formatta_data_italiana(data_str: str) -> str:
    if not data_str:
        return datetime.now().strftime("%d/%m/%Y")
    if "/" in data_str and len(data_str.split("/")[0]) <= 2:
        return data_str
    if "-" in data_str:
        try:
            dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except Exception:
            try:
                dt = datetime.strptime(data_str[:10], "%Y-%m-%d")
                return dt.strftime("%d/%m/%Y")
            except Exception:
                pass
    return data_str

# ===================== HELPER TESTO =====================
def normalizza_testo(testo: str) -> str:
    if not testo:
        return ""
    testo = re.sub(r'\s+', ' ', testo.lower().strip())
    testo = re.sub(r'[^\w\s]', '', testo)
    return testo

def fuzzy_match(testo1: str, testo2: str, soglia: int = 70) -> bool:
    if not testo1 or not testo2:
        return False
    t1 = normalizza_testo(testo1)
    t2 = normalizza_testo(testo2)
    return max(fuzz.ratio(t1, t2), fuzz.partial_ratio(t1, t2), fuzz.token_sort_ratio(t1, t2)) >= soglia

def cerca_match_ingrediente(ingrediente: str, prodotti_fattura: list, soglia: int = 70) -> Optional[dict]:
    ingrediente_norm = normalizza_testo(ingrediente)
    miglior_match, miglior_score = None, 0
    for prodotto in prodotti_fattura:
        desc_norm = normalizza_testo(prodotto.get('descrizione', ''))
        score = max(fuzz.ratio(ingrediente_norm, desc_norm),
                    fuzz.partial_ratio(ingrediente_norm, desc_norm),
                    fuzz.token_sort_ratio(ingrediente_norm, desc_norm))
        prima = ingrediente_norm.split()[0] if ingrediente_norm else ""
        if prima and len(prima) > 2 and prima in desc_norm:
            score += 15
        if score > miglior_score and score >= soglia:
            miglior_score = score
            miglior_match = {**prodotto, 'score': score}
    return miglior_match

def pulisci_nome_ingrediente(ingrediente: str) -> str:
    if not ingrediente:
        return ""
    testo = ingrediente.strip()
    testo = re.sub(r'\s+[xX]\s*\d+(?:[.,]\d+)?(?:\s*(?:kg|g|lt|ml|l))?(?=\s|$)', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+(non\s+)?contiene\s+allergeni.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-\s*[A-Za-z\."]+(?:\s+[A-Za-z\."]+)*(?:\s+(?:S\.?[rR]\.?[lL]\.?|S\.?[pP]\.?[aA]\.?|srl|spa))?.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+L\.?F?\.?\d*/?[\w\-]*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+FVI/[\w\-]+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+n°?\s*fatt\.?\s*[\w/\-]+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', '', testo)
    testo = re.sub(r'\s+SACCHI\s+SALTECHNO.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+DA\s+KG\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+KG\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+(?:[.,]\d+)?\s*KG\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+(?:[.,]\d+)?\s*(?:G|LT|ML|L)\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-\s*\d{5,}$', '', testo)
    testo = re.sub(r'\s+Orig\.?\s*\w+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+RINFORZ\.?\w*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+ASTUC\.?\w*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+I\s+B\s+\w+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+P[xX]\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+\^\s*\d*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\w*\d+\w*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+GR\.?\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+', ' ', testo).strip()
    testo = re.sub(r'\s*-\s*$', '', testo).strip()
    if testo:
        parole = testo.split()
        parole_f = []
        for i, p in enumerate(parole):
            p_l = p.lower()
            if p_l in ['00', '0', 'man', 'man.', '0/man.']:
                parole_f.append(p_l)
            elif i == 0:
                parole_f.append(p.capitalize())
            else:
                parole_f.append(p_l)
        testo = ' '.join(parole_f)
    return testo

def estrai_quantita_da_descrizione(descrizione: str) -> tuple:
    if not descrizione:
        return (1, 'pz')
    desc = descrizione.upper()
    for pattern, unita in [(r'(\d+(?:[.,]\d+)?)\s*KG', 'kg'), (r'(\d+(?:[.,]\d+)?)\s*G(?!R)', 'g'),
                           (r'(\d+(?:[.,]\d+)?)\s*LT?', 'l'), (r'(\d+(?:[.,]\d+)?)\s*ML', 'ml')]:
        m = re.search(pattern, desc)
        if m:
            return (float(m.group(1).replace(',', '.')), unita)
    return (1, 'pz')

# ===================== PARSER XML =====================
def parse_fattura_xml(xml_content: bytes) -> dict:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        root = ET.fromstring(xml_content.decode('utf-8'))
    
    result = {'fornitore': '', 'piva': '', 'numero_fattura': '', 'data_fattura': '', 'prodotti': []}
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'Denominazione' and not result['fornitore']:
            result['fornitore'] = elem.text or ''
        if tag == 'IdCodice' and not result['piva']:
            result['piva'] = elem.text or ''
        if tag == 'Numero' and not result['numero_fattura']:
            result['numero_fattura'] = elem.text or ''
        if tag == 'Data' and not result['data_fattura']:
            result['data_fattura'] = elem.text or ''
    
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'DettaglioLinee':
            prodotto = {'descrizione': '', 'quantita': '', 'prezzo': '', 'unita_misura': '', '_lotto_data': {}}
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'Descrizione':
                    prodotto['descrizione'] = (child.text or '').strip()
                elif child_tag == 'Quantita':
                    prodotto['quantita'] = child.text or ''
                elif child_tag == 'PrezzoUnitario':
                    prodotto['prezzo'] = child.text or ''
                elif child_tag == 'UnitaMisura':
                    prodotto['unita_misura'] = (child.text or '').strip().upper()
                elif child_tag == 'AltriDatiGestionali':
                    tipo, rif_testo, rif_data = '', '', ''
                    for sub in child:
                        sub_tag = sub.tag.split('}')[-1] if '}' in sub.tag else sub.tag
                        if sub_tag == 'TipoDato': tipo = (sub.text or '').strip().upper()
                        elif sub_tag == 'RiferimentoTesto': rif_testo = (sub.text or '').strip()
                        elif sub_tag == 'RiferimentoData': rif_data = (sub.text or '').strip()
                    if tipo == 'DATI LOTTO' and rif_testo:
                        lotto_data = {}
                        if m := re.search(r'Id:\s*(\w+)', rif_testo, re.IGNORECASE): lotto_data['lotto_id_fornitore'] = m.group(1)
                        if m := re.search(r'Scadenza:\s*(\d{2}/\d{2}/\d{4})', rif_testo, re.IGNORECASE): lotto_data['data_scadenza'] = m.group(1)
                        if m := re.search(r'Qt[a-z\s]*:\s*([\d.]+)', rif_testo, re.IGNORECASE): lotto_data['quantita_originale'] = float(m.group(1))
                        if lotto_data: prodotto['_lotto_data'] = lotto_data
                    elif rif_testo and not prodotto['_lotto_data']:
                        if re.match(r'^[A-Z]{2}\s*\d+', rif_testo):
                            lotto_data = {'lotto_id_fornitore': rif_testo}
                            if rif_data: lotto_data['data_scadenza'] = rif_data
                            prodotto['_lotto_data'] = lotto_data
            if prodotto['descrizione']:
                result['prodotti'].append(prodotto)
    return result

# ===================== ALLERGENI =====================
ALLERGENI_DICT = {
    "glutine": {"nome": "Cereali contenenti GLUTINE", "keywords": ["glutine","grano","frumento","farina","semola","orzo","segale","avena","farro","kamut","spelta","triticale","seitan","malto","pangrattato","pane","pasta","biscotti","crackers","grissini","pizza","focaccia","brioche","croissant","cornetto","sfoglia","pan di spagna","savoiardi","wafer","manitoba","00","0"]},
    "crostacei": {"nome": "CROSTACEI e derivati", "keywords": ["crostacei","gamberi","gamberetti","scampi","aragosta","astice","granchio","granseola","canocchie","mazzancolle"]},
    "uova": {"nome": "UOVA e derivati", "keywords": ["uova","uovo","tuorlo","albume","ovoprodotti","rosso d'uovo","lecitina di uovo","lisozima","maionese","meringa","zabaione","pasta all'uovo"]},
    "pesce": {"nome": "PESCE e derivati", "keywords": ["pesce","merluzzo","salmone","tonno","acciuga","alice","sardina","sgombro","orata","branzino","trota","sogliola","rombo","nasello","baccalà","stoccafisso","colatura","garum","surimi"]},
    "arachidi": {"nome": "ARACHIDI e derivati", "keywords": ["arachidi","arachide","noccioline americane","burro di arachidi","olio di arachidi"]},
    "soia": {"nome": "SOIA e derivati", "keywords": ["soia","soja","edamame","tofu","tempeh","miso","salsa di soia","lecitina di soia","proteine di soia","latte di soia"]},
    "latte": {"nome": "LATTE e derivati (incluso lattosio)", "keywords": ["latte","lattosio","latticini","panna","burro","formaggio","mozzarella","ricotta","mascarpone","yogurt","kefir","parmigiano","grana","pecorino","gorgonzola","taleggio","provolone","scamorza","fiordilatte","stracciatella","burrata","caciotta","asiago","fontina","emmental","gruyere","brie","camembert","cheddar","cream cheese","philadelphia","caseina","caseinato","siero di latte","lattoalbumina","crema","besciamella","biancalieve"]},
    "frutta_guscio": {"nome": "FRUTTA A GUSCIO", "keywords": ["mandorle","mandorla","nocciole","nocciola","noci","noce","anacardi","anacardo","pistacchi","pistacchio","noci pecan","noci macadamia","noci del brasile","noci queensland","pinoli","castagne","praline","gianduia","nutella","pasta di nocciole","farina di mandorle","farina di nocciole","crema nocciola","crema pistacchio"]},
    "sedano": {"nome": "SEDANO e derivati", "keywords": ["sedano","sedano rapa","sale di sedano"]},
    "senape": {"nome": "SENAPE e derivati", "keywords": ["senape","mostarda","semi di senape"]},
    "sesamo": {"nome": "SEMI DI SESAMO e derivati", "keywords": ["sesamo","semi di sesamo","olio di sesamo","tahina","tahini","gomasio","halva"]},
    "solfiti": {"nome": "ANIDRIDE SOLFOROSA e SOLFITI (>10mg/kg)", "keywords": ["solfiti","solfito","anidride solforosa","metabisolfito","bisolfito","e220","e221","e222","e223","e224","e225","e226","e227","e228","vino","aceto"]},
    "lupini": {"nome": "LUPINI e derivati", "keywords": ["lupini","lupino","farina di lupini"]},
    "molluschi": {"nome": "MOLLUSCHI e derivati", "keywords": ["molluschi","cozze","vongole","ostriche","capesante","calamari","seppie","polpo","totani","moscardini","telline","fasolari","cannolicchi","patelle","lumache di mare"]}
}

def rileva_allergeni(ingredienti: list) -> dict:
    trovati = {}
    for ing in ingredienti:
        if not ing: continue
        ing_l = ing.lower().strip()
        for aid, ainfo in ALLERGENI_DICT.items():
            for kw in ainfo["keywords"]:
                if kw in ing_l:
                    if aid not in trovati:
                        trovati[aid] = {"nome": ainfo["nome"], "ingredienti": []}
                    if ing not in trovati[aid]["ingredienti"]:
                        trovati[aid]["ingredienti"].append(ing)
                    break
    nomi = [i["nome"] for i in trovati.values()]
    return {
        "allergeni_presenti": list(trovati.keys()),
        "allergeni_dettaglio": trovati,
        "testo_etichetta": "Contiene: " + ", ".join(nomi) if nomi else "Non contiene allergeni dichiarati",
        "contiene_allergeni": bool(trovati)
    }

def rileva_allergeni_materia(materia_prima: str) -> str:
    if not materia_prima: return "non contiene allergeni"
    trovati = []
    mp_l = materia_prima.lower()
    for aid, ainfo in ALLERGENI_DICT.items():
        for kw in ainfo["keywords"]:
            if kw in mp_l:
                trovati.append(ainfo["nome"])
                break
    return ("Contiene: " + ", ".join(trovati)) if trovati else "non contiene allergeni"

# ===================== SCADENZE =====================
SCADENZE_INGREDIENTI = {
    "crema": (2,60), "crema pasticcera": (2,60), "crema chantilly": (2,45),
    "crema diplomatica": (2,60), "panna": (2,90), "panna montata": (1,30),
    "mascarpone": (3,90), "ricotta": (3,60), "crema al mascarpone": (2,60),
    "uova": (3,90), "uovo": (3,90), "tuorlo": (2,90), "albume": (3,120),
    "ovoprodotti": (3,90), "tuorlo d'uovo": (2,90),
    "latte": (3,90), "burro": (7,270), "yogurt": (5,60),
    "formaggio fresco": (3,60), "mozzarella": (3,60), "fiordilatte": (2,45),
    "frutta": (2,90), "fragole": (1,180), "lamponi": (1,180), "mirtilli": (2,180),
    "frutti di bosco": (1,180), "banana": (2,90), "mela": (5,180), "pera": (3,180),
    "pesca": (2,180), "albicocca": (2,180), "ciliegia": (2,180), "ciliegie": (2,180),
    "amarena": (5,270), "amarene": (5,270), "kiwi": (3,180),
    "cioccolato": (30,365), "cioccolato fondente": (30,365), "cioccolato bianco": (20,270),
    "cacao": (30,365), "ganache": (5,90), "glassa": (7,120), "gianduia": (20,270),
    "farina": (90,365), "farina 00": (90,365), "farina manitoba": (90,365),
    "semola": (90,365), "amido": (180,365), "maizena": (180,365),
    "zucchero": (365,365), "zucchero a velo": (180,365), "zucchero semolato": (365,365),
    "sale": (365,365), "lievito": (14,180), "lievito di birra": (14,180),
    "lievito madre": (7,90), "lievito secco": (180,365), "bicarbonato": (365,365),
    "nocciole": (90,365), "mandorle": (90,365), "noci": (60,270), "pistacchio": (90,365),
    "uvetta": (180,365), "canditi": (180,365), "scorza candita": (180,365),
    "arancia candita": (180,365), "cedro candito": (180,365),
    "olio": (180,365), "olio extravergine": (180,365), "strutto": (30,270), "margarina": (30,270),
    "marmellata": (30,365), "confettura": (30,365), "miele": (365,365), "sciroppo": (90,365),
    "prosciutto": (5,60), "prosciutto cotto": (5,60), "prosciutto crudo": (7,90),
    "pancetta": (7,90), "speck": (7,90), "salame": (14,120), "wurstel": (5,60),
    "parmigiano": (30,270), "pecorino": (30,270), "grana": (30,270),
    "pomodoro": (3,180), "basilico": (2,180), "verdure": (3,180),
    "olive": (14,270), "carote": (7,270), "sedano": (5,180),
    "pasta frolla": (5,180), "pasta sfoglia": (3,180), "pan di spagna": (5,270),
    "biscotto": (30,365), "meringhe": (14,180), "babà": (3,270),
    "sfogliatella": (2,180), "croissant": (2,180), "brioche": (2,180), "cornetto": (2,180),
    "default": (20,90)
}

def calcola_scadenza_prodotto(ingredienti: list, data_produzione: str, abbattuto: bool = False) -> tuple:
    try:
        if "/" in data_produzione:
            dt_prod = datetime.strptime(data_produzione, "%d/%m/%Y")
        elif "-" in data_produzione:
            dt_prod = datetime.strptime(data_produzione, "%Y-%m-%d")
        else:
            dt_prod = datetime.now()
    except (ValueError, TypeError):
        dt_prod = datetime.now()
    
    default = SCADENZE_INGREDIENTI.get("default", (20, 90))
    min_frigo, min_abb = default
    critico = "prodotto generico"
    
    for ing in ingredienti:
        if not ing: continue
        ing_l = ing.lower().strip()
        scad = SCADENZE_INGREDIENTI.get(ing_l)
        if not scad:
            for kw, s in SCADENZE_INGREDIENTI.items():
                if kw != "default" and (kw in ing_l or ing_l in kw):
                    scad = s; break
        if not scad:
            for p in ing_l.split():
                if len(p) > 3 and p in SCADENZE_INGREDIENTI:
                    scad = SCADENZE_INGREDIENTI[p]; break
        if scad and scad[0] < min_frigo:
            min_frigo, min_abb = scad
            critico = ing
    
    dt_frigo = dt_prod + timedelta(days=min_frigo)
    dt_abb = dt_prod + timedelta(days=min_abb)
    return (dt_frigo.strftime("%d/%m/%Y"), dt_abb.strftime("%d/%m/%Y"), critico, min_frigo, min_abb, min_abb // 30)

# ===================== LOTTI - codice generazione =====================
PRODOTTI_IN_KG = ["pasta frolla","pasta sfoglia","crema pasticcera","crema","panna","pasta pizza","impasto","pasta brisée","pasta fillo","ganache","glassa","marmellata","confettura","cioccolato fuso","crema al burro","crema diplomatica","crema chantilly"]

def determina_unita_misura(prodotto: str) -> str:
    p = prodotto.lower()
    return "kg" if any(x in p for x in PRODOTTI_IN_KG) else "pz"

def genera_abbreviazione_prodotto(nome: str) -> str:
    import unicodedata
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    parole = nome.upper().split()
    if len(parole) == 1: return parole[0][:8]
    if len(parole) == 2: return f"{parole[0][:6]}_{parole[1][:4]}"
    return f"{parole[0][:5]}_{parole[1][:4]}"

async def get_prossimo_progressivo(prodotto: str) -> int:
    chiave = genera_abbreviazione_prodotto(prodotto)
    contatore = await db.contatori_lotti.find_one_and_update(
        {"prodotto_chiave": chiave},
        {"$inc": {"progressivo": 1}, "$set": {"prodotto_nome": prodotto, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True, return_document=True
    )
    if contatore and '_id' in contatore:
        del contatore['_id']
    return contatore.get("progressivo", 1) if contatore else 1

def genera_codice_lotto(prodotto: str, progressivo: int, quantita: float, unita: str, data_produzione: str) -> str:
    abbrev = genera_abbreviazione_prodotto(prodotto)
    prog = f"{progressivo:03d}"
    qty = f"{int(quantita)}{unita}" if quantita == int(quantita) else f"{quantita:.1f}{unita}"
    try:
        fmt = "%d/%m/%Y" if "/" in data_produzione else "%Y-%m-%d"
        data_fmt = datetime.strptime(data_produzione, fmt).strftime("%d%m%Y")
    except Exception:
        data_fmt = data_produzione.replace("-","").replace("/","")
    return f"{abbrev}-{prog}-{qty}-{data_fmt}"
