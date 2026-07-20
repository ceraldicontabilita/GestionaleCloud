"""Riconoscimento canonico e privo di scritture delle evidenze POS bancarie."""

import re


_GIORNO_POS_RE = re.compile(r"DEL\s+(\d{2})/(\d{2})/(\d{2})\b", re.IGNORECASE)
_CAUSALE_ACCREDITO_POS_RE = re.compile(
    r"(?:INC\s*\.\s*POS\s+CARTE\s+CREDIT|INCAS\s*\.\s*TRAMITE\s+P\s*\.\s*O\s*\.\s*S)",
    re.IGNORECASE,
)
_CAUSALI_NUMIA_ESCLUSE = ("REMUNERAZIONE DCC", "COMMISSION", "FATTURA NUMIA")


def _giorno_operazione_pos(descrizione: str, data_accredito: str) -> str:
    match = _GIORNO_POS_RE.search(descrizione or "")
    if match:
        giorno, mese, anno = match.groups()
        return f"20{anno}-{mese}-{giorno}"
    return (data_accredito or "")[:10]


def _e_accredito_pos_numia_con_giorno(descrizione: str) -> bool:
    """Accetta solo un accredito reale NUMIA con giorno operativo esplicito."""
    testo = descrizione or ""
    testo_upper = testo.upper()
    return bool(
        "NUMIA" in testo_upper
        and _GIORNO_POS_RE.search(testo)
        and _CAUSALE_ACCREDITO_POS_RE.search(testo)
        and not any(voce in testo_upper for voce in _CAUSALI_NUMIA_ESCLUSE)
    )
