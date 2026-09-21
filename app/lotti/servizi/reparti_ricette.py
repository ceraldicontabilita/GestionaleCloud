"""Classificazione canonica dei reparti delle ricette."""

import re
from typing import List, Optional


# ─── Helper reparti e nomi ────────────────────────────────────────────────────
_PASTICCERIA_KW = [
    "torta",
    "crema",
    "mousse",
    "cheesecake",
    "mille foglie",
    "profitterol",
    "cannolo",
    "sfogliatella",
    "babà",
    "baba",
    "frolla",
    "crostata",
    "macaron",
    "eclair",
    "choux",
    "gelato",
    "semifreddo",
    "tiramisu",
    "tiramisù",
    "panna cotta",
    "pannacotta",
    "crèpe",
    "crepe",
    "waffle",
    "donut",
    "muffin",
    "cupcake",
    "brownie",
    "cookies",
    "biscotto",
    "biscotti",
    "meringhe",
    "meringa",
    "ganache",
    "glassa",
    "confettura",
    "marmellata",
    "namelaka",
    "cremoso",
    "cornetto",
    "brioche",
    "pasticceria",
    "dolce",
    "dessert",
    "budino",
    "flan",
    "strudel",
    "paris-brest",
    "tronchetto",
    "charlotte",
    "cassata",
    "pastiera",
    "struffoli",
    "zeppole",
    "ciambella",
    "ciambellone",
    "pandoro",
    "panettone",
    "colomba",
    "frittelle",
    "bombolone",
    "maritozzo",
    "diplomatico",
    "zuccotto",
    "gianduja",
    "cremino",
    "mignon",
    "savarin",
    "cassatin",
    "coda di aragosta",
    "crostatin",
    "croccantin",
    "delizia",
    "fiocco di neve",
    "francesina",
    "krans",
    "kranz",
    "pan di spagna",
    "pasta di mandorle",
    "pasta sfoglia",
    "pasticcin",
    "prussian",
    "zuccherat",
    "savoiard",
    "chantilly",
    "caprese cioccolato",
    "caprese limone",
    "caprese al cioccolato",
    "caprese al limone",
    "panna",
    "nocciol",
    "cioccol",
    # Nomi tradizionali presenti nel ricettario Ceraldi. Non contengono una
    # parola dolce generica, ma sono prodotti di pasticceria (alcuni sono
    # varianti di brioche/pasta choux importate da Cartel1).
    "buondì",
    "buondi",
    "via col vento",
    "vesuvio",
]
_ROSTICCERIA_KW = [
    "pizza",
    "focaccia",
    "calzone",
    "piadina",
    "panino",
    "sandwich",
    "burger",
    "tramezzino",
    "bruschetta",
    "crostino",
    "arancino",
    "arancina",
    "arancini",
    "supplì",
    "frittata",
    "quiche",
    "mozzarella in carrozza",
    "impanata",
    "fritto",
    "frittura",
    "lasagna",
    "lasagne",
    "gnocchi",
    "risotto",
    "polenta",
    "polpetta",
    "polpette",
    "cotoletta",
    "scaloppina",
    "arrosto",
    "pollo",
    "carne",
    "pesce",
    "baccalà",
    "alici",
    "acciughe",
    "polpo",
    "calamari",
    "gamberi",
    "cozze",
    "vongole",
    "frittella salata",
    "torta salata",
    "rustici",
    "panzerotti",
    "vol-au-vent",
    "croissant salato",
]


_SAVORY_OVERRIDE = (
    "salat", "rustic", "casatiell", "tortano", "scarole", "parmigian",
    "gattò", "gatto di patate", "gateau di patate", "panzerott", "salsiccia",
    "ragù", "ragu", "grissin", "ciabatta",
)

_INGREDIENTI_DOLCI = (
    "zucchero", "cioccol", "cacao", "confettura", "marmellata", "panna",
    "crema pasticc", "fragolin", "amarena", "mandorl", "nocciol", "pistac",
    "aroma croissant", "granella di zucchero", "candit", "vaniglia",
)

_INGREDIENTI_SALATI = (
    "prosciutto", "salame", "mozzarella", "pomodoro", "tonno", "acciug",
    "wurstel", "wrustel", "carne", "ragù", "ragu", "salsiccia", "friariell",
    "melanz", "peperon", "scarol", "parmigian", "provol", "mortadella",
)

_BAR_KW = (
    "spritz", "caffe", "caffè", "cappuccino", "schiumato", "aperitivo",
    "amaro", "whisky", "whiskey", "rum", "vodka", "gin", "cocktail",
    "birra", "prosecco", "spumante", "vino", "liquore", "grappa",
    "succo", "spremuta", "bibita", "acqua tonica", "soda", "cola",
    "the freddo", "tè freddo", "te freddo",
)

_BAR_OVERRIDE = (
    "crema di caffe", "crema di caffè",
)


def _categorizza_reparto(
    nome: str,
    ingredienti: Optional[List[str]] = None,
    ricetta_base_nome: Optional[str] = None,
) -> str:
    """Classifica solo quando esistono segnali sufficienti.

    Cartel1 contiene anche nomi tradizionali poco descrittivi (per esempio
    ``Treccia``) e varianti collegate a una base. Per questi casi usiamo base e
    ingredienti; se il risultato resta incerto ritorniamo ``altro`` invece di
    spostare automaticamente tutto in rosticceria.
    """
    n = (nome or "").lower()
    # Solo le preparazioni inequivocabilmente da bar precedono i dolci. Gli
    # aromi (rum, liquore, caffe) non devono trasformare Babà/Torte in bevande.
    if any(kw in n for kw in _BAR_OVERRIDE):
        return "bar"
    # «Casatiello dolce», «pizza dolce» e nomi analoghi sono dolci anche se
    # contengono una parola normalmente salata. Richiediamo la parola intera
    # per non confondere per esempio «agrodolce».
    if re.search(r"(?<!\w)dolce(?!\w)", n):
        return "pasticceria"
    if any(kw in n for kw in _SAVORY_OVERRIDE):
        return "rosticceria"
    for kw in _PASTICCERIA_KW:
        if kw in n:
            return "pasticceria"
    # I termini del bar devono coincidere con parole/frasi complete: un
    # semplice ``kw in n`` classificava per esempio "cioccolato" come bar
    # perché contiene accidentalmente la sequenza "cola".
    if any(re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", n) for kw in _BAR_KW):
        return "bar"
    for kw in _ROSTICCERIA_KW:
        # Anche qui servono confini: "cozze" non deve coincidere con
        # "scozzesi" (Croccantini scozzesi e un dolce).
        if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", n):
            return "rosticceria"

    base = (ricetta_base_nome or "").lower().strip()
    if base and base != n:
        reparto_base = _categorizza_reparto(base)
        if reparto_base != "altro":
            return reparto_base

    testo_ingredienti = " ".join(str(value or "").lower() for value in (ingredienti or []))
    if testo_ingredienti:
        segnali_salati = sum(kw in testo_ingredienti for kw in _INGREDIENTI_SALATI)
        segnali_dolci = sum(kw in testo_ingredienti for kw in _INGREDIENTI_DOLCI)
        if segnali_salati:
            return "rosticceria"
        if segnali_dolci >= 2:
            return "pasticceria"
    return "altro"


def _reparto_finale_auto(reparto_corrente: str, reparto_calcolato: str) -> str:
    """Applica la classificazione automatica senza cancellare scelte esplicite."""
    corrente = (reparto_corrente or "").lower().strip()
    if reparto_calcolato == "altro":
        return corrente
    return reparto_calcolato


