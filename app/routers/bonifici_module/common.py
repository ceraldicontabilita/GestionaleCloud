"""
Bonifici Module - Costanti e utility condivise per parsing PDF bonifici.
"""
import re
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Directory upload
UPLOAD_DIR = Path("/tmp/bonifici_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# NB: le collezioni bonifici reali sono "bonifici_jobs" e "bonifici_transfers",
# usate direttamente in jobs.py/transfers.py. Le vecchie costanti COL_JOBS/
# COL_TRANSFERS/COL_RICONCILIAZIONE_TASKS puntavano a nomi mai usati e sono
# state rimosse (audit mappa lug 2026) per non trarre in inganno.

# Regex patterns
IBAN_RE = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}\b")
DATE_RE = [
    re.compile(r"(\d{2})[\/-](\d{2})[\/-](\d{4})"),
    re.compile(r"(\d{4})[\/-](\d{2})[\/-](\d{2})"),
]
AMOUNT_RE = re.compile(r"([+-]?)\s?(\d{1,3}(?:[\.,]\d{3})*|\d+)([\.,]\d{2})")


def parse_date(text: str) -> Optional[datetime]:
    """Estrae data da testo."""
    for rx in DATE_RE:
        m = rx.search(text)
        if m:
            try:
                if rx is DATE_RE[0]:
                    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y, mth, d, tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def parse_amount(text: str) -> Optional[float]:
    """Estrae importo da testo."""
    t = text.replace("€", " ").replace("EUR", " ").replace("EURO", " ")
    m = AMOUNT_RE.search(t.replace(" ", ""))
    if not m:
        return None
    sign = -1.0 if m.group(1) == '-' else 1.0
    integer = m.group(2).replace('.', '').replace(',', '')
    cents = m.group(3).replace(',', '.').replace(' ', '')
    try:
        base = float(integer)
        cent_val = float(cents)
        return sign * (base + cent_val)
    except Exception:
        return None


def normalize_str(s: Optional[str]) -> Optional[str]:
    """Normalizza stringa rimuovendo spazi multipli."""
    if not s:
        return None
    return " ".join(s.split())


def safe_filename(name: str) -> str:
    """Genera nome file sicuro."""
    name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    return name[:200]


def build_dedup_key(t: Dict[str, Any]) -> str:
    """Costruisce chiave per deduplicazione bonifici."""
    parts = []
    if t.get("iban_beneficiario"):
        parts.append(t["iban_beneficiario"])
    if t.get("importo") is not None:
        parts.append(f"{t['importo']:.2f}")
    if t.get("data_esecuzione"):
        d = t["data_esecuzione"]
        if isinstance(d, datetime):
            parts.append(d.strftime("%Y%m%d"))
        else:
            parts.append(str(d)[:10].replace("-", ""))
    if t.get("causale"):
        c = normalize_str(t["causale"])
        if c:
            parts.append(c[:50])
    key = "|".join(parts)
    return hashlib.md5(key.encode()).hexdigest()
