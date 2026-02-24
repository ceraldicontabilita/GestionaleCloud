"""
Bonifici Module - PDF extraction e parsing.
"""
from typing import List, Dict, Any
from pathlib import Path
import re

from pdfminer.high_level import extract_text
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

from .common import parse_date, normalize_str, IBAN_RE, logger


def read_pdf_text(pdf_path: Path) -> str:
    """Estrae testo da PDF usando pdfminer o PyMuPDF."""
    try:
        text = extract_text(str(pdf_path)) or ""
        if text.strip():
            return text
    except Exception as e:
        logger.warning(f"pdfminer failed for {pdf_path}: {e}")
    try:
        if fitz:
            doc = fitz.open(str(pdf_path))
            parts = []
            for page in doc:
                parts.append(page.get_text("text"))
            doc.close()
            return "\n".join(parts)
    except Exception as e:
        logger.exception(f"PyMuPDF parse failed for {pdf_path}: {e}")
    return ""


def extract_transfers_from_text(text: str) -> List[Dict[str, Any]]:
    """Estrae bonifici dal testo PDF."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    
    results: List[Dict[str, Any]] = []
    
    # Parsing base
    dt = parse_date(text)
    amt = None
    
    # Cerca importo
    m_amt = re.search(r"\b(EUR|EURO)?\s*([+-]?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2}))\b", text, re.IGNORECASE)
    if m_amt:
        try:
            amt = float(m_amt.group(2).replace('.', '').replace(',', '.'))
        except Exception:
            pass
    
    # Cerca CRO/TRN
    mcro = re.search(r"\b(?:CRO|TRN|NS\s*RIF\.?|RIF\.?\s*(?:OPERAZIONE)?)[:\s]*([A-Z0-9]*[0-9][A-Z0-9]{3,39})\b", text, re.IGNORECASE)
    cro = mcro.group(1).strip() if mcro else None
    
    # Cerca causale
    caus = None
    mca = re.search(r"causale[:\s]*([^\n]+)", text, re.IGNORECASE)
    if mca:
        caus = normalize_str(mca.group(1))
    
    # Cerca IBAN
    ibans = IBAN_RE.findall(text.replace(' ', ''))
    ben_iban = ibans[0] if ibans else None
    ord_iban = ibans[1] if len(ibans) > 1 else None
    
    # Cerca nomi
    ord_nome = None
    ben_nome = None
    for idx, line in enumerate(lines):
        if re.search(r"beneficiario", line, re.IGNORECASE):
            after = re.sub(r"(?i).*beneficiario[:\s]*", "", line).strip()
            if after and len(after) > 2:
                ben_nome = normalize_str(after)
        if re.search(r"ordinante", line, re.IGNORECASE):
            after = re.sub(r"(?i).*ordinante[:\s]*", "", line).strip()
            if after and len(after) > 2:
                ord_nome = normalize_str(after)
    
    results.append({
        'data': dt,
        'importo': amt,
        'valuta': 'EUR',
        'ordinante': {'nome': ord_nome, 'iban': ord_iban},
        'beneficiario': {'nome': ben_nome, 'iban': ben_iban},
        'causale': caus,
        'cro_trn': cro,
        'banca': None,
        'note': None,
    })
    
    return results
