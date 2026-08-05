"""Parser deterministico per estratti conto correnti Banco BPM in PDF.

Il layout testuale BPM presenta ogni movimento come:
data contabile, data valuta, descrizione, importo con segno, data disponibile
e, spesso, una o piu' righe di dettaglio (beneficiario/causale). Il parser
non interpreta il segno: negativo e' uscita, positivo e' entrata.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, List

import fitz
import pdfplumber


_DATE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
_AMOUNT = re.compile(r"^-?\s*\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\s*\d+,\d{2}$")
_CARD_ROW = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+"
    r"(\d{2}:\d{2}:\d{2})\s+"
    r"(-?\s*[\d.]+,\d{2})\s+([A-Z]{3})\s+"
    r"(.+?)\s+"
    r"(PAGAMENTO|PRELIEVO|RIMBORSO|ACCREDITO|STORNO|COMMISSIONE)$",
    re.IGNORECASE,
)
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


def parse_bpm_card_movements_text(text: str) -> List[Dict[str, Any]]:
    """Parsa l'export PDF ``Carta di debito`` del portale Banco BPM.

    Il documento non e' l'estratto conto corrente: contiene una riga per
    operazione con data/ora, importo firmato, valuta, descrizione e tipo.
    Accettiamo soltanto la tabella riconoscibile e tipi operazione chiusi.
    """
    if (
        "CARTA DI DEBITO" not in text.upper()
        or "DATA E ORA IMPORTO DESCRIZIONE TIPO OPERAZIONE" not in text.upper()
    ):
        return []

    rows: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        match = _CARD_ROW.match(re.sub(r"\s+", " ", raw_line.strip()))
        if not match:
            continue
        amount = _amount(match.group(3))
        operation = match.group(6).upper()
        rows.append({
            "data": datetime.strptime(match.group(1), "%d/%m/%Y").strftime("%Y-%m-%d"),
            "data_ora": (
                datetime.strptime(
                    f"{match.group(1)} {match.group(2)}",
                    "%d/%m/%Y %H:%M:%S",
                ).isoformat()
            ),
            "descrizione": match.group(5).strip(),
            "importo": amount,
            "tipo": "uscita" if amount < 0 else "entrata",
            "tipo_operazione": operation.lower(),
            "banca": "Banco BPM",
            "divisa": match.group(4).upper(),
            "strumento": "carta_debito",
        })
    return rows


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
        card_text = text
        if "CARTA DI DEBITO" in text.upper():
            # PyMuPDF espone questo specifico layout per colonne (importi,
            # descrizioni e date separati). pdfplumber conserva invece la
            # riga visiva completa, necessaria per non associare dati di righe
            # diverse quando il report contiene piu' operazioni.
            with pdfplumber.open(io.BytesIO(pdf_content)) as card_pdf:
                card_text = "\n".join(
                    page.extract_text() or "" for page in card_pdf.pages
                )
        card_transactions = parse_bpm_card_movements_text(card_text)
        if card_transactions:
            circuito_match = re.search(r"Circuito:\s*([^\n]+?)(?:\s+Conto Appoggio:|$)", card_text, re.I)
            account_match = re.search(r"Conto Appoggio:\s*(\S+)", card_text, re.I)
            return {
                "success": True,
                "tipo_documento": "movimenti_carta_debito_banco_bpm",
                "banca": "Banco BPM",
                "metadata": {
                    "circuito": circuito_match.group(1).strip() if circuito_match else None,
                    "numero_conto": account_match.group(1) if account_match else None,
                },
                "transazioni": card_transactions,
                "totale_transazioni": len(card_transactions),
            }
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
