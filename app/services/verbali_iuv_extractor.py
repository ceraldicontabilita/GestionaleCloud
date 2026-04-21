"""
Estrazione IUV (Identificativo Univoco Versamento) da verbali e documenti PagoPA.
IUV = 18 cifre che iniziano per 0 o 3.
"""
import os
import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
IUV_PATTERN = re.compile(r'\b([03]\d{17})\b')


def extract_iuv_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    m = IUV_PATTERN.search(filename)
    return m.group(1) if m else None


def extract_iuv_from_pdf(pdf_path: str) -> Optional[str]:
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = IUV_PATTERN.search(text)
        return m.group(1) if m else None
    except Exception as e:
        logger.warning("Errore estrazione IUV da %s: %s", pdf_path, e)
        return None


def get_iuv_from_verbale(verbale: Dict[str, Any]) -> Optional[str]:
    """Ricerca IUV nei vari campi del verbale: campo diretto, filename, PDF content."""
    iuv = verbale.get("iuv") or verbale.get("codice_avviso")
    if iuv and IUV_PATTERN.match(str(iuv)):
        return str(iuv)
    for a in verbale.get("allegati", []) or []:
        nome = a.get("filename") or a.get("nome_file") or ""
        iuv = extract_iuv_from_filename(nome)
        if iuv:
            return iuv
        path = a.get("path") or a.get("filepath")
        if path:
            iuv = extract_iuv_from_pdf(path)
            if iuv:
                return iuv
    # Fallback: nome pdf allegato
    pdf_filename = verbale.get("pdf_filename") or ""
    iuv = extract_iuv_from_filename(pdf_filename)
    if iuv:
        return iuv
    return None
