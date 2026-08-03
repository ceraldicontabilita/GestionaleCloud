"""Parser deterministico per estratti conto correnti Banco BPM in PDF.

Il layout testuale BPM presenta ogni movimento come:
data contabile, data valuta, descrizione, importo con segno, data disponibile
e, spesso, una o piu' righe di dettaglio (beneficiario/causale). Il parser
non interpreta il segno: negativo e' uscita, positivo e' entrata.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

import fitz


_DATE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
_AMOUNT = re.compile(r"^-?\s*\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\s*\d+,\d{2}$")
_STOP_PREFIXES = (
    "INDEX:", "PAGINA ", "DATA DI RIFERIMENTO", "DEL CONTO",
    "SWIFT", "COORDINATE BANCARIE", "CONTO CORRENTE", "INTESTATO A",
    "ESTRATTO CONTO CORRENTE", "DIVISA EUR", "AL 31.", "INVIO N.",
)
_HEADER_LINES = {
    "DATA", "ATM", "WEB", "APP", "DESCRIZIONE DELLE OPERAZIONI",
    "USCITE", "ENTRATE", "CONTABILE", "VALUTA", "DISPONIBILE",
    "*1", "*2", "*3",
}


def _iso(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%y").strftime("%Y-%m-%d")


def _amount(value: str) -> float:
    return float(value.replace(" ", "").replace(".", "").replace(",", "."))


def parse_bpm_text(text: str) -> List[Dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    out: List[Dict[str, Any]] = []
    i = 0
    while i + 3 < len(lines):
        if not (_DATE.match(lines[i]) and _DATE.match(lines[i + 1])):
            i += 1
            continue

        data_contabile, data_valuta = lines[i], lines[i + 1]
        j = i + 2
        descrizione: List[str] = []
        while j < len(lines) and not _AMOUNT.match(lines[j]):
            if _DATE.match(lines[j]) or lines[j].upper() in _HEADER_LINES:
                break
            descrizione.append(lines[j])
            j += 1
        if j >= len(lines) or not descrizione or not _AMOUNT.match(lines[j]):
            i += 1
            continue

        importo = _amount(lines[j])
        j += 1
        data_disponibile = None
        if j < len(lines) and _DATE.match(lines[j]):
            data_disponibile = lines[j]
            j += 1

        # Beneficiario/causale possono essere sulla riga successiva
        # all'importo. Ci fermiamo prima dell'inizio del movimento seguente.
        dettagli: List[str] = []
        while j < len(lines) and len(dettagli) < 5:
            if j + 1 < len(lines) and _DATE.match(lines[j]) and _DATE.match(lines[j + 1]):
                break
            upper = lines[j].upper()
            if upper in _HEADER_LINES or upper.startswith(_STOP_PREFIXES):
                break
            if not _DATE.match(lines[j]) and not _AMOUNT.match(lines[j]):
                dettagli.append(lines[j])
            j += 1

        testo = " ".join(descrizione + dettagli).strip()
        if "SALDO INIZIALE" not in testo.upper() and importo != 0:
            out.append({
                "data": _iso(data_contabile),
                "data_valuta": _iso(data_valuta),
                "data_disponibile": _iso(data_disponibile) if data_disponibile else None,
                "descrizione": re.sub(r"\s+", " ", testo),
                "importo": importo,
                "tipo": "uscita" if importo < 0 else "entrata",
                "banca": "Banco BPM",
                "divisa": "EUR",
            })
        i = max(j, i + 1)
    return out


def parse_estratto_conto_bpm(pdf_content: bytes) -> Dict[str, Any]:
    if not pdf_content.startswith(b"%PDF"):
        return {"success": False, "error": "PDF non valido", "transazioni": []}
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in doc)
        doc.close()
        if "ESTRATTO CONTO" not in text.upper() or "05034" not in text:
            return {"success": False, "error": "Formato Banco BPM non riconosciuto", "transazioni": []}
        transazioni = parse_bpm_text(text)
        if not transazioni:
            return {"success": False, "error": "Nessun movimento BPM riconosciuto", "transazioni": []}
        return {
            "success": True,
            "tipo_documento": "estratto_conto_banco_bpm",
            "transazioni": transazioni,
            "totale_transazioni": len(transazioni),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "transazioni": []}
