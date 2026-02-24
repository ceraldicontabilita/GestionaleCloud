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

# Collections
COL_JOBS = "archivio_bonifici_jobs"
COL_TRANSFERS = "archivio_bonifici"
COL_RICONCILIAZIONE_TASKS = "bonifici_riconciliazione_tasks"

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


def parse_filename_data(filename: str) -> Optional[Dict[str, Any]]:
    """
    Estrae dati dal nome file (pattern: IBAN_IMPORTO_DATA_CAUSALE.pdf).
    Es: IT60X0542811101000000123456_1234.56_20240115_STIPENDIO.pdf
    """
    name = Path(filename).stem
    parts = name.split('_')
    
    if len(parts) < 3:
        return None
    
    result = {}
    
    # IBAN
    if IBAN_RE.match(parts[0]):
        result["iban_beneficiario"] = parts[0]
        parts = parts[1:]
    
    # Importo
    for i, p in enumerate(parts):
        try:
            amt = float(p.replace(',', '.'))
            result["importo"] = amt
            parts = parts[:i] + parts[i+1:]
            break
        except Exception:
            pass
    
    # Data (YYYYMMDD o DDMMYYYY)
    for i, p in enumerate(parts):
        if len(p) == 8 and p.isdigit():
            try:
                if int(p[:4]) > 1900:
                    result["data_esecuzione"] = datetime(int(p[:4]), int(p[4:6]), int(p[6:8]), tzinfo=timezone.utc)
                else:
                    result["data_esecuzione"] = datetime(int(p[4:8]), int(p[2:4]), int(p[:2]), tzinfo=timezone.utc)
                parts = parts[:i] + parts[i+1:]
                break
            except Exception:
                pass
    
    # Resto è causale
    if parts:
        result["causale"] = " ".join(parts).replace("_", " ")
    
    return result if result else None
