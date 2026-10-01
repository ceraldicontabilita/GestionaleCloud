"""Dizionario ingredienti: categorie, bevande fuori lista, associazione automatica.

Un solo posto per:

* ``CATEGORIE``: l'elenco delle categorie merceologiche della tendina del
  Dizionario (il frontend lo legge da ``GET /food-cost/dizionario/categorie``,
  non ne tiene una copia);
* ``RINOMINE_CATEGORIE``: le categorie cambiate o tolte (Latticini e Grassi →
  Latticini, Aromi → Bagne e Aromi) e ``riallinea_categorie``, che le migra per
  id e senza cancellare niente;
* ``e_bevanda``: le bibite (acqua, birre, vino, liquori, succhi...) non sono
  ingredienti e escono dalla lista «da associare»; la riga **non si cancella**;
* ``associa_automatico``: per le righe senza categoria (o ferme su «Varie
  Alimentari») propone la categoria giusta dal nome, solo quando e' certa.

Il runtime non fa ricerche sul web: la certezza viene da parole del nome di
fattura, dal nome canonico gia' associato e dalla lettura AI
(``articoli_letti_ai``: marca e prodotto), che devono **concordare**. Una
categoria scritta da una persona (``categoria_fonte = "manuale"``) non si tocca.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

CATEGORIE: List[str] = [
    "Farine e Cereali", "Pasta", "Zuccheri", "Dolcificanti",
    "Latticini", "Burro o margarina", "Formaggi", "Uova", "Olio",
    "Condimenti", "Conserve e Condimenti", "Frutta e Verdura", "Frutta Secca",
    "Carni e Salumi", "Salumi", "Pesce",
    "Semilavorati Pasticceria", "Bagne e Aromi", "Lieviti e Addensanti",
    "Cioccolato e Cacao", "Decorazioni",
    "Bevande", "Alcolici e Liquori",
    "Varie Alimentari", "Non Alimentare",
]

# categoria vecchia (minuscolo) -> categoria nuova
RINOMINE_CATEGORIE: Dict[str, str] = {
    "latticini e grassi": "Latticini",
    "aromi": "Bagne e Aromi",
}

CATEGORIE_BEVANDE = {"Bevande", "Alcolici e Liquori"}

# Famiglie di bevande: stesse parole dell'esclusione in blocco della pagina
# (`/food-cost/dizionario/escludi-famiglia`), piu' i marchi che compaiono da soli.
FAMIGLIE_ESCLUSIONE_DIZIONARIO: Dict[str, List[str]] = {
    "bevande": ["acqua", "bibita", "bibite", "succo", "succhi", "sciroppo",
                "coca", "cola", "aranciata", "gassosa", "chinotto", "tonica",
                "cedrata", "limonata", "spremuta", "energy", "red bull",
                "redbull", "ginger", "estathe", "the freddo", "te freddo",
                "sanpellegrino", "san pellegrino", "perrier", "ferrarelle",
                "fanta", "sprite", "schweppes", "sanbitter"],
    "alcolici": ["birra", "birre", "liquore", "liquori", "amaro", "amari",
                 "rum", "gin", "vodka", "whisky", "whiskey", "grappa",
                 "aperol", "campari", "sambuca", "limoncello", "brandy",
                 "cognac", "vermouth", "vermut", "bitter", "aperitivo",
                 "tourtel", "heineken", "peroni", "moretti"],
    "vini": ["vino", "vini", "spumante", "prosecco", "champagne",
             "franciacorta", "lambrusco", "falanghina", "aglianico",
             "moscato", "brut", "greco di tufo"],
}

_RX_BEVANDA = re.compile(
    "|".join(rf"\b{re.escape(p)}\b" for gruppo in FAMIGLIE_ESCLUSIONE_DIZIONARIO.values() for p in gruppo),
    re.IGNORECASE,
)

# (categoria, parole): la prima regola che scatta vince, quindi le piu'
# specifiche stanno in alto («pasta di pistacchio» non e' pasta). Una parola
# vale all'inizio di parola: «spaghett» prende «spaghettoni».
_REGOLE: List[tuple] = [
    ("Semilavorati Pasticceria", ["pasta di", "pasta pistacch", "pasta nocc", "pasta sfoglia", "pasta frolla",
                                 "crema", "ripieno", "farcitura", "glassa", "nuppy", "pan di spagna"]),
    ("Cioccolato e Cacao", ["cioccolat", "cacao", "gianduia", "fondente"]),
    ("Pasta", ["pasta", "pas.", "spaghett", "penne", "rigaton", "fusilli", "fettuccin", "mezzani", "mezziti", "mezze",
               "mafaldin", "vermicell", "tagliatell", "paccheri", "linguine", "tortellin", "gnocch", "ziti",
               "candele", "orecchiett", "pappardell", "lasagn", "bucatini", "farfalle", "conchigli", "fregola"]),
    ("Burro o margarina", ["burro", "margarina", "olva", "ilva"]),
    ("Olio", ["olio"]),
    ("Salumi", ["prosciutt", "salame", "mortadell", "speck", "bresaola", "pancetta", "bacon", "guanciale",
                "wurstel", "culatello", "nduja"]),
    ("Carni e Salumi", ["cotolett", "pollo", "birbe", "cordon bleu", "hamburger", "salsiccia", "carne", "manzo",
                        "maiale", "tacchino", "arrosto", "polpett"]),
    ("Formaggi", ["mozzarell", "ricotta", "mascarpone", "parmigian", "grana", "pecorino", "provola", "scamorz",
                  "gorgonzola", "formagg", "emmental"]),
    ("Latticini", ["panna", "latte", "yogurt", "feta"]),
    ("Zuccheri", ["zucchero", "glucosio", "destrosio", "fruttosio", "saccarosio"]),
    ("Farine e Cereali", ["farina", "semola", "riso", "amido", "fecola", "cereali", "couscous", "orzo", "avena"]),
    ("Uova", ["uovo", "uova", "tuorlo", "albume"]),
    ("Lieviti e Addensanti", ["lievito", "pectina", "agar"]),
    ("Frutta Secca", ["nocciol", "mandorl", "pistacch", "noci", "pinoli", "arachid", "granella"]),
]


def _rx(parole: Iterable[str]):
    return re.compile(r"(?<![a-zà-ÿ])(?:" + "|".join(re.escape(p) for p in parole) + ")", re.IGNORECASE)


_REGOLE_RX = [(cat, _rx(parole)) for cat, parole in _REGOLE]


def _testo(valore: Any) -> str:
    return re.sub(r"\s+", " ", str(valore or "").split("\n", 1)[0]).strip().lower()


def categoria_da_testo(testo: Any) -> Optional[str]:
    """La categoria che il nome dice con certezza, altrimenti None."""
    t = _testo(testo)
    if not t:
        return None
    for cat, rx in _REGOLE_RX:
        if rx.search(t):
            return cat
    return None


def categoria_normalizzata(categoria: Any) -> str:
    """La categoria dopo le rinomine; vuota resta vuota."""
    c = str(categoria or "").strip()
    return RINOMINE_CATEGORIE.get(c.lower(), c)


def e_bevanda(riga: Dict[str, Any]) -> bool:
    """La riga e' una bibita (non un ingrediente)?

    Si' se la categoria e' Bevande / Alcolici e Liquori. Le parole di bevanda
    nel nome valgono solo per le righe che nessuno ha ancora classificato
    (categoria vuota o «Varie Alimentari») e che non hanno una categoria
    alimentare certa dal nome: «cacao amaro» e' cacao, «sciroppo di glucosio»
    e' zucchero.
    """
    categoria = categoria_normalizzata(riga.get("categoria_canonica") or riga.get("categoria"))
    if categoria in CATEGORIE_BEVANDE:
        return True
    if categoria not in ("", "Varie Alimentari"):
        return False
    nome = _testo(riga.get("nome_originale") or riga.get("nome_normalizzato"))
    if not nome or categoria_da_testo(nome):
        return False
    return bool(_RX_BEVANDA.search(nome))


def categoria_proposta(riga: Dict[str, Any], lettura: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Categoria certa per la riga: le fonti che parlano devono concordare."""
    fonti = [riga.get("nome_originale"), riga.get("nome_canonico"), riga.get("ingrediente_canonico"),
             (lettura or {}).get("prodotto")]
    trovate = {c for c in (categoria_da_testo(f) for f in fonti) if c}
    return next(iter(trovate)) if len(trovate) == 1 else None


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def riallinea_categorie(db) -> Dict[str, int]:
    """Migra le categorie rinominate o tolte sui record esistenti, per id.

    Idempotente: al secondo giro non trova piu' niente."""
    esito = {"dizionario": 0, "mapping": 0}
    for vecchia, nuova in RINOMINE_CATEGORIE.items():
        rx = {"$regex": f"^{re.escape(vecchia)}$", "$options": "i"}
        for r in await db.dizionario_prodotti.find({"categoria_canonica": rx}, {"_id": 0, "id": 1}).to_list(None):
            if r.get("id"):
                await db.dizionario_prodotti.update_one({"id": r["id"]}, {"$set": {"categoria_canonica": nuova}})
                esito["dizionario"] += 1
        for r in await db.nome_mapping.find({"categoria": rx}, {"_id": 0, "descrizione_key": 1}).to_list(None):
            if r.get("descrizione_key"):
                await db.nome_mapping.update_one({"descrizione_key": r["descrizione_key"]},
                                                 {"$set": {"categoria": nuova}})
                esito["mapping"] += 1
    return esito


async def associa_automatico(db, limite: int = 200) -> Dict[str, int]:
    """Categoria certa alle righe del Dizionario che non ce l'hanno.

    Tocca solo righe con categoria vuota o «Varie Alimentari» e non scritte da
    una persona, mai le bibite. Scrive ``categoria_fonte = "auto"``: una
    persona la cambia dalla tendina e da quel momento e' ``manuale``.
    A lotti di ``limite``; senza proposta certa la riga resta com'e'.
    """
    from app.lotti.servizi.confronto_fornitori import impronta_descrizione

    righe = await db.dizionario_prodotti.find(
        {"categoria_fonte": {"$ne": "manuale"},
         "$or": [{"categoria_canonica": {"$in": [None, "", "Varie Alimentari"]}},
                 {"categoria_canonica": {"$exists": False}}]},
        {"_id": 0, "id": 1, "nome_originale": 1, "nome_normalizzato": 1, "nome_canonico": 1,
         "ingrediente_canonico": 1, "categoria_canonica": 1, "escluso_ricette": 1},
    ).to_list(None)
    esito = {"viste": len(righe), "assegnate": 0, "bevande": 0, "dubbie": 0}
    letture = {str(d.get("id")): d for d in await db.articoli_letti_ai.find(
        {}, {"_id": 0, "id": 1, "prodotto": 1}).to_list(None)}
    for r in righe:
        if esito["assegnate"] >= limite:
            break
        if not r.get("id") or r.get("escluso_ricette") is True:
            continue
        if e_bevanda(r):
            esito["bevande"] += 1
            continue
        lettura = letture.get(impronta_descrizione(r.get("nome_originale") or ""))
        cat = categoria_proposta(r, lettura)
        if not cat or cat == (r.get("categoria_canonica") or ""):
            esito["dubbie"] += 1
            continue
        await db.dizionario_prodotti.update_one(
            {"id": r["id"]},
            {"$set": {"categoria_canonica": cat, "categoria_fonte": "auto", "categoria_auto_il": _adesso()}},
        )
        esito["assegnate"] += 1
    return esito


async def giro_dizionario(db) -> Dict[str, Any]:
    """Il giro dello scheduler: rinomine, poi categorie certe. Idempotente."""
    return {"rinomine": await riallinea_categorie(db), "categorie": await associa_automatico(db)}
