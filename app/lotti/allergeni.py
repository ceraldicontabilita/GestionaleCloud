"""Motore unico per la rilevazione degli allergeni nelle ricette.

Le ricette storiche non hanno tutte la stessa forma: alcune usano
``ingredienti_dettaglio``, altre la lista legacy ``ingredienti`` e le ricette
composte possono avere anche ``componenti``.  Questo modulo normalizza le tre
fonti e restituisce sempre i nomi ufficiali usati dall'interfaccia.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


ALLERGENI_14 = [
    "Glutine",
    "Crostacei",
    "Uova",
    "Pesce",
    "Arachidi",
    "Soia",
    "Latte",
    "Frutta a guscio",
    "Sedano",
    "Senape",
    "Sesamo",
    "Anidride solforosa",
    "Lupini",
    "Molluschi",
]


# L'asterisco finale indica una radice intenzionale (biscott* = biscotto,
# biscotti, biscotteria). Le altre voci sono cercate come parole/frasi intere:
# così, per esempio, ``pan`` non trasforma erroneamente ``panna`` in glutine.
MAPPA_ALLERGENI = {
    "Anidride solforosa": [
        "vino", "aceto", "solfiti", "solfito", "anidride solforosa",
        "metabisolfito", "frutta disidratata", "uva passa", "albicocche secche",
    ],
    "Arachidi": ["arachidi", "arachide", "burro di arachidi", "olio di arachidi", "groundnut"],
    "Crostacei": ["gamberi", "gambero", "gamberetti", "scampi", "aragosta", "granchio", "granchi", "astice", "mazzancolle"],
    "Frutta a guscio": [
        "mandorle", "mandorla", "nocciole", "nocciola", "noci", "noce",
        "pistacchi", "pistacchio", "anacardi", "anacardio", "pinoli", "pinolo",
        "noci pecan", "noci del brasile", "macadamia", "gianduia", "nutella",
        "pasta di nocciole", "nuppy nocciola",
    ],
    "Glutine": [
        "farina", "frumento", "grano", "glutine", "semola", "orzo", "segale",
        "avena", "farro", "kamut", "spelta", "pasta alimentare", "pasta di semola",
        "pasta all'uovo", "pane", "panino",
        "pan di spagna", "pangrattato", "biscott*", "crackers", "cereali",
        "amido di frumento", "malto", "lievito madre", "sfoglia", "brioche",
        "pizza", "caputo", "cornett*", "croissant", "crostat*", "grissini",
        "tarall*", "mix cake", "tappi per ricce", "wurstel", "wrustel",
        "bucatini", "spaghetti", "rigatoni", "penne", "fusilli", "focaccia",
        "prussiana", "treccia", "baba", "babà", "frittatin*",
    ],
    "Latte": [
        "latte", "lattosio", "panna", "burro", "formaggio", "mozzarella",
        "ricotta", "yogurt", "yoghurt", "mascarpone", "grana", "parmigiano",
        "pecorino", "provolone", "brie", "emmental", "scamorza", "stracchino",
        "besciamella", "crema", "latticini", "caseina", "siero di latte",
        "provola", "caciocavallo", "fiordilatte", "margarina", "wienercreme",
        "plunder", "nuppy", "sottilette",
    ],
    "Lupini": ["lupini", "lupino", "farina di lupino", "farina di lupini"],
    "Molluschi": [
        "cozze", "cozza", "ostriche", "ostrica", "vongole", "vongola", "polpo",
        "calamari", "calamaro", "seppie", "seppia", "lumache", "frutti di mare",
    ],
    "Pesce": [
        "pesce", "baccalà", "merluzzo", "salmone", "tonno", "acciughe", "acciuga",
        "alice", "sardine", "sgombro", "branzino", "orata", "spigola", "colatura",
    ],
    "Sedano": ["sedano", "sedano rapa"],
    "Senape": ["senape", "mostarda"],
    "Sesamo": ["sesamo", "tahina", "tahini", "semi di sesamo"],
    "Soia": ["soia", "soja", "soy", "tofu", "tempeh", "edamame", "latte di soia", "salsa di soia", "lecitina di soia", "proteine di soia"],
    "Uova": [
        "uova", "uovo", "albume", "tuorlo", "ovoprodotti", "maionese", "meringa",
        "frittata", "pasta all'uovo", "pasta uovo", "crema pasticcera",
        "creme brulee", "crème brûlée", "zabaione", "meringhe", "frittatin*",
        "crocche", "crocchè", "polpett*",
    ],
}


_ALIAS = {
    "cereali contenenti glutine": "Glutine",
    "cereali/glutine": "Glutine",
    "frutta_guscio": "Frutta a guscio",
    "frutta a guscio": "Frutta a guscio",
    "solfiti": "Anidride solforosa",
    "anidride solforosa e solfiti": "Anidride solforosa",
}
_CANONICI = {nome.casefold(): nome for nome in ALLERGENI_14}


def normalizza_allergene(valore: Any) -> str:
    testo = str(valore or "").strip()
    if not testo:
        return ""
    chiave = testo.casefold()
    return _ALIAS.get(chiave) or _CANONICI.get(chiave) or testo


def normalizza_allergeni(valori: Iterable[Any] | None) -> list[str]:
    risultato: list[str] = []
    for valore in valori or []:
        nome = normalizza_allergene(valore)
        if nome and nome not in risultato:
            risultato.append(nome)
    return risultato


def _nome_ingrediente(voce: Any) -> str:
    if isinstance(voce, str):
        return voce.strip()
    if isinstance(voce, dict):
        for campo in ("nome", "nome_canonico", "nome_normalizzato", "descrizione"):
            valore = str(voce.get(campo) or "").strip()
            if valore:
                return valore
    return ""


def estrai_nomi_ingredienti(ricetta: dict, override: Iterable[Any] | None = None) -> list[str]:
    """Legge gli ingredienti da ogni formato noto, senza usare il nome ricetta.

    Usare il nome della ricetta produce falsi positivi: ``Coda d'aragosta`` è un
    dolce, non prova la presenza del crostaceo. L'eventuale ``override`` serve al
    frontend per analizzare la bozza prima del salvataggio.
    """
    fonti: list[Iterable[Any]] = []
    if override is not None:
        fonti.append(override)
    else:
        fonti.extend([
            ricetta.get("ingredienti_dettaglio") or [],
            ricetta.get("ingredienti") or [],
            ricetta.get("componenti") or [],
        ])

    risultato: list[str] = []
    visti: set[str] = set()
    for fonte in fonti:
        for voce in fonte or []:
            nome = _nome_ingrediente(voce)
            chiave = nome.casefold()
            if nome and chiave not in visti:
                visti.add(chiave)
                risultato.append(nome)
    return risultato


def _corrisponde(testo: str, parola: str) -> bool:
    radice = parola.endswith("*")
    parola = parola[:-1] if radice else parola
    if not parola:
        return False
    finale = "" if radice else r"(?![a-zà-öø-ÿ])"
    pattern = r"(?<![a-zà-öø-ÿ])" + re.escape(parola.casefold()) + finale
    return re.search(pattern, testo.casefold()) is not None


def rileva_allergeni(nomi_ingredienti: Iterable[Any]) -> tuple[list[str], dict[str, list[str]]]:
    nomi = [n for n in (_nome_ingrediente(v) for v in nomi_ingredienti or []) if n]
    trovati: list[str] = []
    trovati_da: dict[str, list[str]] = {}
    for allergene in ALLERGENI_14:
        parole = MAPPA_ALLERGENI.get(allergene, [])
        corrispondenze = [nome for nome in nomi if any(_corrisponde(nome, p) for p in parole)]
        if corrispondenze:
            trovati.append(allergene)
            trovati_da[allergene] = corrispondenze
    return trovati, trovati_da
