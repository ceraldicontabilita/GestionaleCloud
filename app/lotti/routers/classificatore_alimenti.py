"""
CLASSIFICATORE ALIMENTI — UNICA fonte di verità per decidere se una riga
(fattura, giacenza, listino) è merce alimentare visibile o roba di
manutenzione/servizi/attrezzatura da tenere SOLO per statistica.

Regola di Enzo (giu 2026): i non-alimentari (candeggina, diluente, cavi,
monitor, morsettiere, cancelleria...) NON devono comparire nelle viste
prodotti. Restano nelle fatture e nei movimenti per i calcoli, ma non
allungano le liste.

Usato da: magazzino_unificato (gestione-prodotti), fatture (carico bar da
fattura), magazzino_bar (pulizia-non-merce), listino (sync da fatture),
ordini_app (giacenze). NESSUN altro file deve definire regex proprie.
"""
import re as _re
import unicodedata as _ud

# ── Servizi / voci contabili (non hanno stock fisico) ─────────────────────────
NON_MERCE_RE = _re.compile(
    r"rinnovo|dominio|\bservizio\b|servizio di|canone|abbonamento|hosting|"
    r"noleggio|assistenza|manutenzione|consulenz|\bspese\b|commission|"
    r"\bbollo\b|interess|contributo|\.it\b|\.com\b|instant ink|firma digitale|"
    r"licenz|vi rimettiamo fattura|anticipazione contrattuale|sponsorizzazione|"
    r"accise|locazione|tribunale|giudizio|\bcausa\b|forfait|restauro|"
    r"nota di credito|preventivo|detrarre|\bacconto\b|ns\.?\s*ft|\bddt\b|cancelleria|"
    # righe fattura generiche/ausiliarie + cauzioni + targhe auto compatte (leasing:
    # "GG782PN STELVIO...", "GW980EP Canone..."). Targa SOLO senza spazi interni:
    # con spazi opzionali matcherebbe sigle confezione tipo "CF 100 PZ" (verificato
    # su 3.694 righe fattura reali il 02/07/2026: 31 match, tutti non-food).
    r"articolo vario|riga ausiliaria|cauzion|\b[a-z]{2}\d{3}[a-z]{2}\b|"
    # righe bolletta energia elettrica (viste nel file righe_xml del 02/07:
    # "SPESA ONERI DI SISTEMA", "SPESA PER L'ENERGIA - Fascia F1...")
    r"oneri di sistema|spesa per l.energia|dispacciament|perdite di rete|"
    r"cogenerazion|quota fissa|quota potenza|energia attiva|fascia f\d|"
    # righe-nota omaggi ("+ 1 CARTONE IN OMAGGIO", "1 CARTONE OMAGGIO ...")
    # NON sono prodotti: gli omaggi veri li traccia sconti_merce dalla fattura
    r"\bomaggi?o\b",
    _re.I,
)

# ── Detersivi/chimici di pulizia del laboratorio ──────────────────────────────
# Esclusi dai cataloghi ALIMENTARI ma soggetti a scheda di SICUREZZA per HACCP
# (richiesta Enzo 02/07/2026: principi attivi, pericoli per l'uomo, scheda ASL).
# La campagna ricerca web li identifica con prompt dedicato (tipo='sicurezza').
RX_DETERSIVI = _re.compile(
    # "ammoniaca" con eccezione: l'ammoniaca PER DOLCI (bicarbonato di ammonio,
    # E503) è una materia prima di pasticceria, non un detersivo.
    r"candegg|\bsapone\b|deterg|detersiv|brillantant|sgrassat|"
    r"ammoniaca(?!.{0,40}(?:bicarbonato|e\s?503|per dolci))|"
    r"igienizz|disinfett|anticalcare|amuchina|alco[o]?l denaturato",
    _re.I,
)

# ── Oggetti fisici NON alimentari (pulizia, elettrico, attrezzatura, monouso) ─
HARD_NONFOOD = _re.compile(
    "|".join([
        # pulizia / chimici (i detersivi condividono RX_DETERSIVI, sopra)
        RX_DETERSIVI.pattern,
        r"diluent", r"solvent", r"vernic",
        r"\bspugn", r"\bscopa\b", r"\bmocio\b",
        # elettrico / informatica / ricambi
        r"\bcavo\b", r"\bhdmi\b", r"\bmonitor\b", r"morsett", r"elettrod",
        r"\bpiedino\b", r"impastatric", r"ricamb", r"\bvite\b", r"bullone",
        r"tassell", r"guarnizion", r"\bfiltro\b", r"riparaz", r"attrezzatur",
        r"macchinar", r"raccordo", r"\bdisplay\b", r"\btoner\b", r"lampadin",
        r"brugol", r"barra filettata", r"\bzincat", r"chiave a bussol",
        # edilizia / arredo
        r"battiscopa", r"paravent", r"\binox\b", r"acciaio", r"piastrell",
        r"lappato", r"pavimenti", r"adesiva", r"\d{3,}x\d{3,}",
        # monouso / stoviglie / packaging
        r"bicchier", r"tazzin", r"\btazza\b", r"\btazze\b", r"cucchiain",
        r"forchett", r"forchettin", r"coltell", r"piattin", r"\bpiatti\b",
        r"\bpiatto\b", r"vassoi", r"tovagliol", r"palett", r"cannucc",
        r"vaschett", r"contenitor", r"sacchett", r"pirottin", r"coppett",
        r"\bruoto\b", r"\bruoti\b", r"pastierina", r"tortiera", r"shopper",
        r"\brotolo\b", r"coperch", r"\bposate\b", r"\bcalice\b", r"\bguanti\b",
        r"pellicola", r"alluminio in fogli", r"carta forno", r"carta igienic",
        r"scottex", r"caffeino", r"snack vegan",
    ]),
    _re.I,
)

# Marchi/sigle di prodotti chimici e tecnici noti entrati dalle fatture
_BRAND_NONFOOD = _re.compile(r"\bmaxima\b|\bsvitol\b|\bwd-?40\b|\bacer\b|\bdewin\b", _re.I)

# ── Parole che da sole indicano CIBO ──────────────────────────────────────────
FOOD_WORDS = _re.compile(
    r"\b(" + "|".join([
        "farina", "farine", "semola", "semolino", "burro", "oli[ova]", "olio",
        "pasta", "past[ae]", "zucchero", "zucch", "cacao", "cioccolat", "cremor",
        "latte", "panna", "uova", "uovo", "lievito", "lieviti", "crema", "creme",
        "caff[e\u00e8]", "mutti", "pomodor", "passata", "frutta", "mandorl",
        "nocciol", "vanigl", "miele", "sale", "pistacch", "liquirizia",
        "mozzarell", "ricotta", "mascarpone", "provol", "formagg", "farcitura",
        "glassa", "gelatina", "confettur", "marmellat", "sciroppo", "granella",
        "copertura", "candit", "amido", "fecola", "malto", "destrosio", "strutto",
        "margarina", "pectina", "aroma", "estratto", "tuorlo", "albume",
        "prosciutt", "salame", "mortadell", "wurstel", "carne", "pollo",
        "tonno", "acciugh", "verdur", "spinaci", "funghi", "carciof", "peperon",
        "melanzan", "zucchin", "patate", "cipoll", "aglio", "basilico",
        "origano", "pepe", "cannella", "the", "t\u00e8",
        "camomilla", "orzo", "riso", "couscous", "ceci", "fagioli",
        "lenticchie", "nutella", "gianduia", "praline", "torrone", "amaretti",
        "savoiardi", "biscott", "pan di spagna", "pandispagna", "impasto",
        "yogurt", "gelato", "granita", "succo", "nettare", "bevanda", "acqua",
        "vino", "birra", "spuman", "prosecco", "liquore", "amaro", "rum",
        "gin", "vodka", "grappa", "limoncello", "aperol", "campari", "bitter",
        "cola", "aranciata", "gassosa", "chinotto", "tonica", "sciropp",
        "miscela", "cialde", "capsule caff", "arabica", "robusta",
        "noce", "noci", "uvetta", "scorzett", "arancia", "limone",
        "fragol", "lampon", "mirtill", "ananas", "banana", "mela", "pera",
        "albicocc", "pesca", "ciliegi", "fico", "cocco", "datteri", "fichi",
        "panettone", "pandoro", "colomba", "bab\u00e0", "sfogliat", "cornett",
        "brioche", "croissant", "pizza margherita", "pesce", "gamber",
        "anguria", "melone", "kiwi", "mandarino", "estathe", "lurisia",
        "tourtel", "kimbo", "whisk", "tartellett", "surrogato", "fondente",
    ]) + r")",
    _re.IGNORECASE,
)

FOOD_CAT = {
    "Beveraggi", "Verdure",
    "Farine/Cereali", "Latticini", "Creme/Paste", "Cioccolato", "Zuccheri",
    "Lieviti", "Oli/Grassi", "Uova", "Frutta/Noci", "Carni/Salumi", "Pesce",
    "Bibite", "Vini e Bevande", "Liquori", "Caffe", "Caffè", "Surgelati",
    "Conserve", "Aromi/Spezie", "Gelateria",
}


def strip_accents(t: str) -> str:
    return "".join(c for c in _ud.normalize("NFD", t or "") if _ud.category(c) != "Mn").lower()


def e_servizio(nome: str) -> bool:
    """True se la riga è un servizio/voce contabile (niente stock fisico)."""
    return bool(NON_MERCE_RE.search(nome or ""))


_FOOD_CAT_NORM = {strip_accents(c) for c in FOOD_CAT}


def e_non_food_certo(nome: str) -> bool:
    """True se la riga è POSITIVAMENTE non alimentare: servizio, pulizia,
    elettrico, attrezzatura, marchio tecnico."""
    n = nome or ""
    return bool(NON_MERCE_RE.search(n) or HARD_NONFOOD.search(n) or _BRAND_NONFOOD.search(n))


def e_alimento(nome: str, categoria: str = "") -> bool:
    """STRETTO (per la curatela in Gestione prodotti): True solo se riconosce
    il cibo per categoria o parola. Mai True se positivamente non-food."""
    if not nome or len(nome.strip()) < 3:
        return False
    if not _re.search(r"[A-Za-z\u00c0-\u00ff]{3,}", nome):
        return False
    if e_non_food_certo(nome):
        return False
    if strip_accents(categoria) in _FOOD_CAT_NORM:
        return True
    return bool(FOOD_WORDS.search(nome))


def e_merce_alimentare(nome: str, categoria: str = "") -> bool:
    """PERMISSIVO (per listino/giacenze/cataloghi): nasconde SOLO ciò che è
    positivamente non-food. Ferrarelle/Red Bull/Heineken (marchi senza
    parola-cibo) restano visibili: vengono da fornitori alimentari."""
    if not nome or len(nome.strip()) < 3:
        return False
    if not _re.search(r"[A-Za-z\u00c0-\u00ff]{3,}", nome):
        return False
    return not e_non_food_certo(nome)
