"""Riconoscimento canonico e privo di scritture delle evidenze POS bancarie."""

import re


_GIORNO_POS_RE = re.compile(r"DEL\s+(\d{2})/(\d{2})/(\d{2})\b", re.IGNORECASE)
_CAUSALE_ACCREDITO_POS_RE = re.compile(
    r"(?:INC\s*\.\s*POS\s+CARTE\s+CREDIT|INCAS\s*\.\s*TRAMITE\s+P\s*\.\s*O\s*\.\s*S)",
    re.IGNORECASE,
)
_CAUSALI_NUMIA_ESCLUSE = ("REMUNERAZIONE DCC", "COMMISSION", "FATTURA NUMIA")

# In estratto conto lo stesso circuito compare con due marchi: NUMIA e' la
# societa' che esegue l'accredito, NEXI il gestore del terminale. Pretendere
# solo "NUMIA" faceva ignorare in silenzio le righe etichettate NEXI, che
# restavano senza riconciliazione. Le altre condizioni (causale POS + giorno
# operativo "DEL gg/mm/aa" + esclusione di commissioni e fatture) restano e
# sono quelle che escludono i falsi positivi.
_MARCHI_ACCREDITO_POS = ("NUMIA", "NEXI")


def _giorno_operazione_pos(descrizione: str, data_accredito: str) -> str:
    match = _GIORNO_POS_RE.search(descrizione or "")
    if match:
        giorno, mese, anno = match.groups()
        return f"20{anno}-{mese}-{giorno}"
    return (data_accredito or "")[:10]


def _e_accredito_pos_numia_con_giorno(descrizione: str) -> bool:
    """Accetta solo un accredito reale del circuito, con giorno esplicito.

    Vale per entrambi i marchi con cui compare in estratto conto (NUMIA e
    NEXI): sono lo stesso circuito, e scartarne uno lascerebbe trasferimenti
    POS eternamente non riconciliati.
    """
    testo = descrizione or ""
    testo_upper = testo.upper()
    return bool(
        any(marchio in testo_upper for marchio in _MARCHI_ACCREDITO_POS)
        and _GIORNO_POS_RE.search(testo)
        and _CAUSALE_ACCREDITO_POS_RE.search(testo)
        and not any(voce in testo_upper for voce in _CAUSALI_NUMIA_ESCLUSE)
    )
