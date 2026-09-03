"""
dizionario_categorie.py — Dizionario di classificazione merceologica.

Sorgente unica, estensibile, dei termini reali con cui classificare un prodotto
a partire dal nome in fattura. L'idea: conoscendo i sinonimi (bicchiere = calice =
tumbler = old fashioned…) e i marchi (whisky Jack Daniel's, Johnnie Walker
etichetta rossa/nera/blu…), un termine o sinonimo viene piazzato con certezza
nella categoria giusta.

Per aggiungere termini basta estendere le liste qui sotto.

Regola di priorità: un articolo di vetreria/attrezzatura resta "Attrezzature"
anche se nel nome compare una bevanda. Esempio reale:
  "Conf 6 Calici Riserva Grappa"  →  Attrezzature (è un set di calici, non grappa).
"""

import re

# ── ATTREZZATURE (vetreria + attrezzatura bar) — hanno la PRIORITA' ───────────
# Termini non ambigui (evitati di proposito "coppa", "martini", "shot" da soli,
# perché collidono con salumi/vermouth). Match a parola intera.
ATTREZZATURE = {
    "Bicchieri": [
        "bicchiere", "bicchieri", "bicchierino", "bicchierini",
        "calice", "calici", "tumbler", "dumbler",
        "old fashioned", "old-fashioned",
        "flute", "flutes", "flûte",
        "ballon", "balloon", "snifter",
        "highball", "high ball", "collins",
        "boccale", "boccali", "coppa champagne", "coppa cocktail",
        "sottobicchiere", "sottobicchieri",
    ],
    "Attrezzatura bar": [
        "shaker", "jigger", "apribottiglie", "cavatappi", "stappabottiglie",
        "secchiello ghiaccio", "secchiello del ghiaccio", "porta ghiaccio",
        "pinza ghiaccio", "pestello", "muddler", "colino", "strainer",
        "caraffa", "caraffe", "decanter", "brocca", "dosatore",
        "vassoio", "vassoi",
    ],
}

# ── BEVANDE: tassonomia con marchi (estende le parole-chiave base) ────────────
BEVANDE = {
    "Whisky": [
        "whisky", "whiskey", "bourbon", "scotch", "single malt",
        "jack daniel", "jack daniel's", "gentleman jack",
        "johnnie walker", "j.walker", "j. walker", "jw",
        "red label", "black label", "blue label", "gold label",
        "green label", "double black", "etichetta rossa", "etichetta nera",
        "etichetta blu", "etichetta oro", "etichetta verde",
        "jameson", "jb", "ballantine", "ballantine's", "chivas", "chivas regal",
        "glenfiddich", "glenlivet", "glen grant", "macallan", "talisker",
        "lagavulin", "laphroaig", "oban", "bushmills", "four roses",
        "jim beam", "maker's mark", "bulleit", "dewar", "grant's",
        "famous grouse", "cutty sark", "tullamore", "wild turkey", "canadian club",
    ],
    "Rum": [
        "rum", "ron", "cachaca", "cachaça",
        "havana", "havana club", "bacardi", "zacapa", "diplomatico",
        "pampero", "brugal", "santa teresa", "appleton", "kraken",
        "captain morgan", "malibu", "don papa",
    ],
    "Gin": [
        "gin", "bombay", "bombay sapphire", "tanqueray", "hendrick",
        "hendrick's", "gordon", "gordon's", "beefeater", "gin mare",
        "malfy", "roku", "monkey 47", "bulldog", "bosford", "portofino",
        "martin miller", "elephant",
    ],
    "Vodka": [
        "vodka", "absolut", "smirnoff", "belvedere", "grey goose",
        "beluga", "stolichnaya",
    ],
    "Grappa e distillati": [
        "grappa", "nardini", "nonino", "sibona", "poli", "candolini",
        "marzadro", "la trentina",
    ],
    "Brandy e cognac": [
        "brandy", "cognac", "hennessy", "remy martin", "courvoisier",
        "martell", "vecchia romagna", "stock 84", "cardenal mendoza",
        "vsop", "armagnac",
    ],
    "Tequila": [
        "tequila", "jose cuervo", "jose'cuervo", "patron", "olmeca", "sierra",
    ],
    "Liquori e amari": [
        "liquore", "amaro", "amari", "montenegro", "ramazzotti", "averna",
        "fernet", "branca", "jagermeister", "jagermaister", "baileys",
        "sambuca", "limoncello", "aperol", "campari", "vermouth", "martini bianco",
        "martini rosso", "cynar", "select", "lucano", "borsci", "unicum",
        "disaronno", "amaretto", "cointreau", "grand marnier", "drambuie",
        "passoa", "midori", "kahlua", "vov", "luxardo", "maraschino",
        "punt e mes", "punt & mes", "braulio", "petrus", "jefferson", "zucca",
        "pastis", "pernod", "st germain", "st. germain", "triple sec", "curacao",
    ],
    "Birre": [
        "birra", "beck", "ceres", "ichnusa", "leffe", "menabrea", "peroni",
        "nastro azzurro", "tennent", "tourtel", "moretti", "heineken",
        "corona", "dreher",
    ],
    "Bibite e soft drink": [
        "coca cola", "fanta", "sprite", "schweppes", "tonica", "acqua tonica",
        "red bull", "energy drink", "estathe", "crodino", "sanbitter",
        "lemonsoda", "oransoda", "chinotto", "cedrata", "gassosa", "gazzosa",
        "ginger beer", "fever tree",
    ],
    "Acqua": [
        "acqua minerale", "acqua naturale", "acqua frizzante", "ferrarelle",
        "lete", "san benedetto", "sant'anna", "panna", "levissima", "vitasnella",
        "sorgesana", "natia",
    ],
    "Succhi": [
        "succo", "succhi", "nettare", "yoga", "polpa di frutta",
    ],
    "Vino e spumante": [
        "vino", "spumante", "prosecco", "champagne", "valdobbiadene",
        "pecorino doc", "cuvee",
    ],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _contiene_parola(testo: str, termine: str) -> bool:
    """Match a confine di parola (evita falsi positivi tipo 'gin' dentro 'origine')."""
    return re.search(r"(?<![a-zàèéìòù])" + re.escape(termine) + r"(?![a-zàèéìòù])", testo) is not None


def classifica(nome: str):
    """Ritorna (categoria_merce, sottocategoria) oppure None se non riconosciuto.

    Le Attrezzature/vetreria hanno priorità: un set di calici è attrezzatura
    anche se il nome contiene 'grappa'.
    """
    n = _norm(nome)
    if not n:
        return None
    # 1) Attrezzature / vetreria — priorità assoluta
    for sottocat, termini in ATTREZZATURE.items():
        for t in termini:
            if _contiene_parola(n, t):
                return ("Attrezzature", sottocat)
    # 2) Bevande con marchi/sinonimi
    for sottocat, termini in BEVANDE.items():
        for t in termini:
            if _contiene_parola(n, t):
                return ("Bevande e Bottiglie", sottocat)
    return None
