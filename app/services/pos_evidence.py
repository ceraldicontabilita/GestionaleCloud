"""Riconoscimento canonico e privo di scritture delle evidenze POS bancarie."""

import re


_GIORNO_POS_RE = re.compile(r"DEL\s+(\d{2})/(\d{2})/(\d{2})\b", re.IGNORECASE)
_CAUSALE_ACCREDITO_POS_PATTERN = (
    r"(?:"
    r"INC\s*\.\s*POS\s+CARTE\s+CREDIT"
    r"|INCAS\s*\.\s*TRAMITE\s+P\s*\.\s*O\s*\.\s*S"
    r"|(?:NUMIA|NEXI)\s*-\s*(?:AMEX|INTER|BNCMT|PGBNT)"
    r")"
)
_CAUSALE_ACCREDITO_POS_RE = re.compile(
    _CAUSALE_ACCREDITO_POS_PATTERN,
    re.IGNORECASE,
)
ACCREDITO_POS_BANK_QUERY_PATTERN = (
    rf"{_CAUSALE_ACCREDITO_POS_PATTERN}.*"
    r"DEL\s+[0-9]{2}/[0-9]{2}/[0-9]{2}\b"
)
_CAUSALI_NUMIA_ESCLUSE = (
    "REMUNERAZIONE DCC",
    "COMMISSION",
    "FATTURA NUMIA",
    "SPESA CON CARTA",
)

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
    NEXI) e per le causali operative Banco BPM realmente osservate, anche
    quando non hanno il prefisso storico ``INC.POS``/``INCAS. TRAMITE P.O.S``::

        NUMIA-INTER DEL 30/03/26 ...
        NUMIA-AMEX DEL 30/03/26 ...
        NUMIA-BNCMT DEL 30/03/26 ...
        NUMIA-PGBNT DEL 12/01/26 ...

    Commissioni, fatture del gestore e spese carta restano escluse.
    """
    testo = descrizione or ""
    testo_upper = testo.upper()
    return bool(
        any(marchio in testo_upper for marchio in _MARCHI_ACCREDITO_POS)
        and _GIORNO_POS_RE.search(testo)
        and _CAUSALE_ACCREDITO_POS_RE.search(testo)
        and not any(voce in testo_upper for voce in _CAUSALI_NUMIA_ESCLUSE)
    )
