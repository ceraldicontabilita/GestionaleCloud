"""
unita_misura.py
════════════════════════════════════════════════════════════════════
Normalizzazione unità di misura per la VISUALIZZAZIONE
(magazzino/rimanenze/schede): unica funzione superstite del vecchio
modulo (dizionario conversioni + endpoint /unita-misura/*), rimosso
nell'audit del 03/07/2026 perché mai chiamato da frontend/scheduler.
La logica di conversione peso/prezzo vive in xml_helpers.calcola_prezzo_quantita_kg.
"""



# ══════════════════════════════════════════════════════════════════
# NORMALIZZAZIONE UNITÀ DI VISUALIZZAZIONE (magazzino / rimanenze)
# Le unità delle fatture arrivano eterogenee: maiuscole/minuscole
# (kg/KG, pz/PZ), sinonimi (KAR/CAR/cartone/cassa, NUMERO/PEZZI,
# bottiglia/bot) e codici imballo fornitore (c5/b4/c6/c7 di SIRO per
# bevande a cassa). Qui le riconduco a un set canonico pulito SOLO per
# la visualizzazione. NB: per le unità non di peso/volume l'etichetta
# non incide su food cost o giacenze.
# ══════════════════════════════════════════════════════════════════

_UNITA_CANON_DISPLAY = {"KG", "G", "L", "ML", "CL", "PZ", "BT", "CT", "CF", "RT", "FUSTO", "MQ"}

_UNITA_ALIAS_DISPLAY = {
    "kg": "KG", "kg.": "KG", "kilogrammi": "KG", "kilogrammo": "KG", "chilogrammi": "KG", "chilo": "KG",
    "g": "G", "gr": "G", "grammi": "G", "grammo": "G", "g.": "G",
    "l": "L", "lt": "L", "lt.": "L", "litri": "L", "litro": "L",
    "ml": "ML", "cl": "CL",
    "pz": "PZ", "pz.": "PZ", "pezzi": "PZ", "pezzo": "PZ", "pc": "PZ", "pcs": "PZ",
    "nr": "PZ", "nr.": "PZ", "n": "PZ", "n.": "PZ", "numero": "PZ", "num": "PZ",
    "un": "PZ", "u": "PZ", "st": "PZ", "p1": "PZ", "unita": "PZ", "unità": "PZ", "confezioni": "CF",
    "bt": "BT", "bottiglia": "BT", "bottiglie": "BT", "bot": "BT", "b": "BT", "br": "BT", "bs": "BT", "fs": "BT",
    "ct": "CT", "cartone": "CT", "cartoni": "CT", "cassa": "CT", "casse": "CT", "car": "CT", "kar": "CT",
    "crt": "CT", "cfn": "CT", "cs": "CT", "sc": "CT", "box": "CT", "ca": "CT", "scatola": "CT", "scatole": "CT",
    "cf": "CF", "confezione": "CF", "conf": "CF", "conf.": "CF",
    "rotolo": "RT", "rotoli": "RT", "rt": "RT",
    "fus": "FUSTO", "fusto": "FUSTO", "fusti": "FUSTO", "mq": "MQ",
}

# Codici imballo (bevande a cassa) -> cartone/cassa
_UNITA_IMBALLO_DISPLAY = {"c3", "c5", "c6", "c7", "c8", "b4"}
# Artefatti di parsing -> pezzo neutro
_UNITA_JUNK_DISPLAY = {"000", "oma", "ztu", "ora", "euro"}


def normalizza_unita_display(u, default: str = "PZ") -> str:
    """Unità canonica per la visualizzazione in magazzino/rimanenze/schede.

    Per valori vuoti/None restituisce `default` (KG per le materie prime,
    PZ per i prodotti bar): non si forza un'unità dove il dato manca.
    """
    if u is None:
        return default
    s = str(u).strip()
    if not s:
        return default
    low = s.lower()
    if low in _UNITA_ALIAS_DISPLAY:
        return _UNITA_ALIAS_DISPLAY[low]
    if low in _UNITA_IMBALLO_DISPLAY:
        return "CT"
    if low in _UNITA_JUNK_DISPLAY:
        return "PZ"
    up = s.upper()
    if up in _UNITA_CANON_DISPLAY:
        return up
    return up[:5]
