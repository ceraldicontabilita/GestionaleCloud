"""
Conversione docx → PDF — Ceraldi Group
======================================
Punto UNICO per trasformare un documento .docx in PDF (serve all'iter di firma
digitale dei contratti: il PDF è poi marcato/firmato/PEC via OpenAPI).

Render gira in ``env: python`` e NON include LibreOffice, quindi la conversione
in produzione passa da un servizio cloud: **ConvertAPI** (docx → pdf, alta
fedeltà, una sola chiamata REST con file in base64 e PDF in risposta).

Strategia (un solo sistema, con fallback locale per lo sviluppo):
  1. se ``CONVERTAPI_TOKEN`` è impostato  → ConvertAPI (produzione);
  2. altrimenti, se ``soffice``/``libreoffice`` è presente → LibreOffice headless
     (utile in locale dove LibreOffice c'è);
  3. altrimenti → errore chiaro e azionabile.

Credenziali SOLO da env Render:
  CONVERTAPI_TOKEN   token (Secret) dell'account ConvertAPI
  CONVERTAPI_BASE    opzionale, default https://v2.convertapi.com

La funzione è sincrona apposta: viene invocata dentro ``asyncio.to_thread`` dal
router contratti (che converte e unisce più documenti in un ciclo).
"""
from __future__ import annotations

import os
import base64
import logging

import httpx

logger = logging.getLogger(__name__)


class DocxConversionError(RuntimeError):
    """Conversione docx → PDF non riuscita o non configurata."""


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _convertapi_docx_to_pdf(docx_bytes: bytes, filename: str) -> bytes:
    """Converte via ConvertAPI: POST /convert/docx/to/pdf con file in base64."""
    token = _env("CONVERTAPI_TOKEN")
    base = _env("CONVERTAPI_BASE", "https://v2.convertapi.com").rstrip("/")
    url = f"{base}/convert/docx/to/pdf"
    payload = {
        "Parameters": [
            {
                "Name": "File",
                "FileValue": {
                    "Name": filename or "documento.docx",
                    "Data": base64.b64encode(docx_bytes).decode("ascii"),
                },
            },
            # base64 nella risposta (niente StoreFile: nessun file lasciato sul cloud)
            {"Name": "StoreFile", "Value": False},
        ]
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=120) as http:
            resp = http.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise DocxConversionError(f"ConvertAPI irraggiungibile: {e}") from e
    if resp.status_code >= 400:
        raise DocxConversionError(
            f"ConvertAPI errore {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    files = data.get("Files") or []
    if not files or not files[0].get("FileData"):
        raise DocxConversionError(f"ConvertAPI: PDF assente nella risposta: {str(data)[:300]}")
    return base64.b64decode(files[0]["FileData"])


def _libreoffice_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Fallback locale: LibreOffice headless (solo dove `soffice` è installato)."""
    import shutil
    import tempfile
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return b""  # segnala "non disponibile" al chiamante
    workdir = tempfile.mkdtemp(prefix="docx2pdf_")
    src = os.path.join(workdir, "documento.docx")
    with open(src, "wb") as f:
        f.write(docx_bytes)
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", workdir, src],
            check=True, capture_output=True, timeout=120)
        pdf_path = os.path.join(workdir, "documento.pdf")
        if not os.path.exists(pdf_path):
            raise DocxConversionError("LibreOffice: output PDF assente.")
        with open(pdf_path, "rb") as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        raise DocxConversionError(
            f"LibreOffice: conversione fallita: {e.stderr.decode('utf-8', 'ignore')[:300]}") from e
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def docx_to_pdf(docx_bytes: bytes, filename: str = "documento.docx") -> bytes:
    """Converte un .docx in PDF. ConvertAPI in produzione, LibreOffice in locale."""
    if _env("CONVERTAPI_TOKEN"):
        return _convertapi_docx_to_pdf(docx_bytes, filename)
    pdf = _libreoffice_docx_to_pdf(docx_bytes)
    if pdf:
        return pdf
    raise DocxConversionError(
        "Conversione docx→PDF non disponibile: imposta CONVERTAPI_TOKEN nelle env "
        "di Render (oppure installa LibreOffice in locale per lo sviluppo).")
