"""
Bonifici Module - PDF extraction e parsing.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import io
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


def read_pdf_bytes(content: bytes) -> str:
    """Estrae testo da un PDF gia' disponibile in memoria.

    Il flusso ``Import documenti`` conserva i file in Drive/Sheets e non deve
    dipendere dalla vita breve di ``/tmp``. Per questo il parser accetta
    direttamente i byte e usa PyMuPDF soltanto come fallback.
    """
    try:
        text = extract_text(io.BytesIO(content)) or ""
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("pdfminer failed for in-memory bonifico: %s", exc)
    try:
        if fitz:
            doc = fitz.open(stream=content, filetype="pdf")
            parts = [page.get_text("text") for page in doc]
            doc.close()
            return "\n".join(parts)
    except Exception as exc:
        logger.warning("PyMuPDF failed for in-memory bonifico: %s", exc)
    return ""


_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def extract_filename_metadata(filename: str) -> Dict[str, Any]:
    """Ricava identita' e mese del pagamento dal nome del PDF.

    Sono supportati entrambi gli ordini usati operativamente, ad esempio
    ``Cognome Nome bonifico marzo.pdf`` e ``bonifico marzo Cognome Nome.pdf``.
    Il mese scritto nel nome (es. ``bonifico marzo``) indica il mese in cui
    e' stato disposto il bonifico, non il mese di competenza del cedolino.
    Il nome file non viene mai usato come prova dell'importo.
    """
    stem = Path(filename or "").stem
    pulito = re.sub(r"[_-]+", " ", stem)
    pulito = re.sub(r"\bbonific[oi]\b", " ", pulito, flags=re.I)
    mese = None
    for nome_mese, numero in _MESI.items():
        if re.search(rf"\b{nome_mese}\b", pulito, re.I):
            mese = numero
            pulito = re.sub(rf"\b{nome_mese}\b", " ", pulito, flags=re.I)
            break
    anno_match = re.search(r"\b(20\d{2})\b", pulito)
    anno = int(anno_match.group(1)) if anno_match else None
    if anno_match:
        pulito = pulito[:anno_match.start()] + " " + pulito[anno_match.end():]
    # Suffissi copia generati dal browser/scanner: Emanuele1, (2), copia.
    pulito = re.sub(r"\bcopia\b|\(\d+\)", " ", pulito, flags=re.I)
    pulito = re.sub(r"(?<=[A-Za-zÀ-ÿ])\d+$", "", pulito.strip())
    nome = normalize_str(re.sub(r"[^A-Za-zÀ-ÿ' ]+", " ", pulito))
    if nome and len(nome.split()) < 2:
        nome = None
    return {
        "beneficiario_nome": nome,
        "mese_pagamento_file": mese,
        "anno_pagamento_file": anno,
    }


def _extract_payroll_period(causale: str) -> Dict[str, Optional[int]]:
    """Estrae la competenza solo se dichiarata nella causale del bonifico."""
    text = (normalize_str(causale or "") or "").casefold()
    if not re.search(r"\b(stipend|salari|emolument|competenz|mensilit)", text):
        return {"periodo_mese": None, "periodo_anno": None}
    mese = None
    for nome_mese, numero in _MESI.items():
        if re.search(rf"\b{nome_mese}\b", text):
            mese = numero
            break
    numerico = re.search(r"\b(0?[1-9]|1[0-2])[/\-](20\d{2})\b", text)
    if numerico:
        return {"periodo_mese": int(numerico.group(1)), "periodo_anno": int(numerico.group(2))}
    anno_match = re.search(r"\b(20\d{2})\b", text)
    return {
        "periodo_mese": mese,
        "periodo_anno": int(anno_match.group(1)) if anno_match else None,
    }


def _value_after_label(lines: List[str], labels: str) -> Optional[str]:
    """Valore sulla stessa riga o sulla prima riga utile successiva."""
    for idx, line in enumerate(lines):
        match = re.search(rf"(?:{labels})\s*[:\-]?\s*(.*)$", line, re.I)
        if not match:
            continue
        value = normalize_str(match.group(1))
        if value and len(value) > 1:
            return value
        for next_line in lines[idx + 1:idx + 4]:
            if re.search(r"^(?:importo|data|iban|causale|descrizione\s+causale|ordinante|beneficiario|cro|trn)\b", next_line, re.I):
                continue
            value = normalize_str(next_line)
            if value:
                return value
    return None


def _parse_euro(value: str) -> Optional[float]:
    if not value:
        return None
    matches = re.findall(r"(?<!\d)(\d{1,3}(?:[. ]\d{3})*,\d{2}|\d+[.,]\d{2})(?!\d)", value)
    if not matches:
        return None
    raw = matches[0].replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        return round(abs(float(raw)), 2)
    except ValueError:
        return None


def _parse_amount_from_document(text: str) -> Optional[float]:
    """Legge anche i PDF BPM con valore prima di ``EUR`` e layout a colonne."""
    pattern = re.compile(
        r"(?:(?:EUR|EURO|â‚¬)\s*)?"
        r"(\d{1,3}(?:[. ]\d{3})*,\d{2}|\d+[.,]\d{2})"
        r"(?:\s*(?:EUR|EURO|â‚¬))?",
        re.I,
    )
    candidati: List[float] = []
    for match in pattern.finditer(text or ""):
        # Accetta soltanto valori accompagnati dalla valuta oppure vicini alla
        # parola Importo/Totale; evita numeri casuali del CRO e delle date.
        start, end = match.span()
        contesto = (text[max(0, start - 90): min(len(text), end + 40)]).casefold()
        token = match.group(0)
        if not re.search(r"EUR|EURO|â‚¬", token, re.I) and not re.search(r"importo|totale", contesto):
            continue
        valore = _parse_euro(match.group(1))
        if valore is not None and valore > 0:
            candidati.append(valore)
    return max(candidati) if candidati else None


def _extract_transfer_table_row(lines: List[str]) -> Dict[str, Any]:
    """Legge la riga della distinta stipendi esportata da Banco BPM.

    Nel PDF le quattro intestazioni sono estratte prima dei quattro valori;
    cercare semplicemente la riga successiva a ``Beneficiario`` o ``Causale``
    finirebbe quindi per scambiare i campi tra loro.
    """
    for idx, line in enumerate(lines):
        if normalize_str(line).casefold() != "beneficiario":
            continue
        # Layout Banco BPM reale: il valore del beneficiario compare subito
        # dopo la prima intestazione; seguono le altre tre intestazioni e poi
        # i rispettivi valori. Esempio:
        # Beneficiario, Mario Rossi, IBAN beneficiario,
        # Descrizione causale, Importo, <iban>, stipendio marzo, 900,00 EUR.
        blocco = lines[idx:idx + 8]
        if len(blocco) == 8 and [
            (normalize_str(value) or "").casefold()
            for value in (blocco[0], blocco[2], blocco[3], blocco[4])
        ] == [
            "beneficiario", "iban beneficiario", "descrizione causale", "importo",
        ]:
            iban = re.sub(r"\s+", "", blocco[5]).upper()
            return {
                "beneficiario_nome": normalize_str(blocco[1]),
                "beneficiario_iban": iban if IBAN_RE.fullmatch(iban) else None,
                "causale": normalize_str(blocco[6]),
                "importo": _parse_euro(blocco[7]),
            }
        headers = [
            (normalize_str(value) or "").casefold()
            for value in lines[idx:idx + 4]
        ]
        if len(headers) < 4 or headers != [
            "beneficiario", "iban beneficiario", "descrizione causale", "importo",
        ]:
            continue
        values = lines[idx + 4:idx + 8]
        if len(values) < 4:
            continue
        iban = re.sub(r"\s+", "", values[1]).upper()
        return {
            "beneficiario_nome": normalize_str(values[0]),
            "beneficiario_iban": iban if IBAN_RE.fullmatch(iban) else None,
            "causale": normalize_str(values[2]),
            "importo": _parse_euro(values[3]),
        }
    return {}


def _is_invalid_person_value(value: Optional[str]) -> bool:
    """Valida un nome senza intervalli Unicode dipendenti dalla codifica."""
    if not value:
        return True
    normalized = normalize_str(value).casefold()
    if normalized in {
        "descrizione causale", "causale", "beneficiario", "dati beneficiario",
        "importo", "importo bonifico", "iban",
    }:
        return True
    if re.search(r"\d|\b(?:EUR|EURO)\b", value, re.I) or "\u20ac" in value:
        return True
    parole = re.findall(r"[^\W\d_']+(?:'[^\W\d_']+)?", value, re.UNICODE)
    return len(parole) < 2


def extract_transfers_from_text(text: str, filename: str = "") -> List[Dict[str, Any]]:
    """Estrae bonifici dal testo PDF."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    table_row = _extract_transfer_table_row(lines)

    results: List[Dict[str, Any]] = []

    metadata_file = extract_filename_metadata(filename)

    # Parsing base: privilegia i campi etichettati del documento bancario.
    data_value = _value_after_label(
        lines, r"data\s+(?:esecuzione|operazione|disposizione|bonifico)|eseguito\s+il"
    )
    dt = parse_date(data_value or text)
    amt = None

    # Cerca importo
    amount_value = _value_after_label(
        lines, r"importo(?:\s+(?:bonifico|operazione|disposto))?|totale\s+bonifico"
    )
    amt = table_row.get("importo") or _parse_euro(amount_value or "")
    if amt is None:
        m_amt = re.search(
            r"\b(?:EUR|EURO|€)\s*([+-]?\d{1,3}(?:[. ]\d{3})*(?:,\d{2})|[+-]?\d+[.,]\d{2})\b",
            text, re.IGNORECASE,
        )
        if m_amt:
            amt = _parse_euro(m_amt.group(1))
    if amt is None:
        amt = _parse_amount_from_document(text)

    # Cerca CRO/TRN
    mcro = re.search(r"\b(?:CRO|TRN|NS\s*RIF\.?|RIF\.?\s*(?:OPERAZIONE)?)[:\s]*([A-Z0-9]*[0-9][A-Z0-9]{3,39})\b", text, re.IGNORECASE)
    cro = mcro.group(1).strip() if mcro else None

    # Cerca causale
    caus = table_row.get("causale") or _value_after_label(
        lines, r"causale(?:\s+del\s+bonifico)?|motivazione"
    )
    if caus and (IBAN_RE.search(caus.replace(" ", "")) or _parse_euro(caus) is not None):
        caus = None

    # Cerca IBAN
    ibans = IBAN_RE.findall(text.replace(' ', ''))
    ben_iban = table_row.get("beneficiario_iban") or (ibans[0] if ibans else None)
    ord_iban = ibans[1] if len(ibans) > 1 else None

    # Cerca nomi
    ord_nome = None
    ben_nome = None
    ben_nome = table_row.get("beneficiario_nome") or _value_after_label(
        lines, r"beneficiario|a\s+favore\s+di|destinatario|intestatario\s+beneficiario"
    )
    if _is_invalid_person_value(ben_nome):
        ben_nome = metadata_file.get("beneficiario_nome")
    ord_nome = _value_after_label(lines, r"ordinante|disponente|intestatario\s+conto")

    periodo = _extract_payroll_period(caus or "")
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
        'periodo_mese': periodo.get('periodo_mese'),
        'periodo_anno': periodo.get('periodo_anno'),
        'mese_pagamento_file': metadata_file.get('mese_pagamento_file'),
        'anno_pagamento_file': metadata_file.get('anno_pagamento_file'),
    })

    return results
