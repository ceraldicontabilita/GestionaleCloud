"""
Parser per Libro Unico del Lavoro (Buste Paga) - Zucchetti Format.

Questo modulo parsifica i PDF delle buste paga Zucchetti ed estrae:
- Dati salariali (netto, acconto, differenza)
- Dati presenze (ore ordinarie, ferie, permessi, malattia)
- Dati contratto (scadenza, mansione)
- Mese di competenza
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Italian month names for parsing
ITALIAN_MONTHS = {
    'gennaio': '01', 'febbraio': '02', 'marzo': '03', 'aprile': '04',
    'maggio': '05', 'giugno': '06', 'luglio': '07', 'agosto': '08',
    'settembre': '09', 'ottobre': '10', 'novembre': '11', 'dicembre': '12'
}


class ParsingError(Exception):
    """Eccezione per errori di parsing."""
    pass


def safe_float(value: str, default: float = 0.0) -> float:
    """Converte stringa in float in modo sicuro."""
    try:
        return float(value.replace(',', '.').replace(' ', ''))
    except (ValueError, AttributeError):
        return default


def safe_int(value: str, default: int = 0) -> int:
    """Converte stringa in int in modo sicuro."""
    try:
        return int(value.replace(' ', ''))
    except (ValueError, AttributeError):
        return default


def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalizza date da DD/MM/YYYY o DD-MM-YYYY a YYYY-MM-DD.
    """
    if not date_str:
        return None

    try:
        date_str = date_str.replace('/', '-')
        parts = date_str.split('-')

        if len(parts) != 3:
            return None

        day, month, year = parts

        if len(year) == 2:
            year = '20' + year

        day_int = int(day)
        month_int = int(month)
        year_int = int(year)

        if not (1 <= day_int <= 31 and 1 <= month_int <= 12 and 1900 <= year_int <= 2100):
            return None

        return f"{year_int:04d}-{month_int:02d}-{day_int:02d}"

    except (ValueError, AttributeError):
        return None


def extract_competenza_month(text: str) -> Tuple[Optional[str], bool]:
    """
    Estrae il mese di competenza dal testo PDF.
    
    Returns:
        Tuple (mese_anno, alta_confidenza)
    """
    if not text:
        return None, False

    text_lower = text.lower()
    header_text = text_lower[:1000]

    # PRIORITY 1: Range di date (dal ... al ...)
    range_patterns = [
        (r'dal\s+\d{1,2}[/-](\d{2})[/-](\d{4})\s+al\s+\d{1,2}[/-](\d{2})[/-](\d{4})', 'date range'),
    ]

    for pattern, desc in range_patterns:
        match = re.search(pattern, header_text)
        if match:
            month1, year1, month2, year2 = match.groups()
            if month1 == month2 and year1 == year2 and 1 <= int(month1) <= 12:
                logger.info(f"✓ HIGH CONFIDENCE: {desc}: {year1}-{month1}")
                return f"{year1}-{month1}", True

    # PRIORITY 2: Keyword COMPETENZA o PERIODO DI PAGA con date
    competenza_patterns = [
        (r'competenza[:\s]+(\d{2})[/-](\d{4})', 'competenza'),
        (r'periodo\s+di\s+paga[:\s]+(\d{2})[/-](\d{4})', 'periodo di paga'),
        (r'mese[:\s]+(\d{2})[/-](\d{4})', 'mese'),
        (r'retribuzione[:\s]+(\d{2})[/-](\d{4})', 'retribuzione')
    ]

    for pattern, desc in competenza_patterns:
        match = re.search(pattern, header_text)
        if match:
            month = match.group(1)
            year = match.group(2)
            if 1 <= int(month) <= 12:
                logger.info(f"✓ HIGH CONFIDENCE: {desc}: {year}-{month}")
                return f"{year}-{month}", True

    # PRIORITY 3: Nome mese italiano + anno
    for keyword in ['competenza', 'periodo di paga', 'mese di', 'retribuzione', 'periodo']:
        for month_name, month_num in ITALIAN_MONTHS.items():
            pattern = rf'{keyword}\s+.*?{month_name}\s+(\d{{4}})'
            match = re.search(pattern, header_text)
            if match:
                year = match.group(1)
                logger.info(f"✓ HIGH CONFIDENCE: {keyword}+{month_name}: {year}-{month_num}")
                return f"{year}-{month_num}", True

    # PRIORITY 4: Nome mese italiano da solo (bassa confidenza)
    for month_name, month_num in ITALIAN_MONTHS.items():
        pattern = rf'{month_name}\s+(\d{{4}})'
        match = re.search(pattern, header_text)
        if match:
            year = match.group(1)
            logger.warning(f"⚠️ LOW CONFIDENCE: {month_name}: {year}-{month_num}")
            return f"{year}-{month_num}", False

    # PRIORITY 5: Pattern generico MM/YYYY (bassa confidenza)
    match = re.search(r'(\d{2})[/-](\d{4})', header_text[:400])
    if match:
        month = match.group(1)
        year = match.group(2)
        if 1 <= int(month) <= 12:
            logger.warning(f"⚠️ LOW CONFIDENCE: Generic MM/YYYY: {year}-{month}")
            return f"{year}-{month}", False

    return None, False


def normalize_pdf_text(text: str) -> str:
    """Normalizza il testo PDF sostituendo separatori comuni."""
    text = text.replace('sE', ' E')
    text = text.replace('sI', ' I')
    text = text.replace('sA', ' A')
    text = text.replace('sO', ' O')
    text = text.replace('sD', ' D')
    text = text.replace('s ', ' ')
    return text


def detect_pdf_type(page_text: str) -> str:
    """
    Rileva il tipo di busta paga.
    
    Returns:
        'amministratore': Busta paga amministratore/tirocinante (singola pagina)
        'dipendente': Busta paga dipendente normale
    """
    if any(keyword in page_text for keyword in [
        'Compenso Amministratore',
        '*000003',
        'Compenso Tirocinante',
        '000004'
    ]):
        return 'amministratore'

    if 'COGNOME NOME' in page_text and 'INDIRIZZO' in page_text:
        return 'dipendente'

    return 'dipendente'


def parse_amministratore_page(page_text: str) -> Optional[Dict[str, Any]]:
    """Parsifica una busta paga di amministratore/tirocinante."""
    page_text = normalize_pdf_text(page_text)
    lines = page_text.split('\n')

    employee_name: Optional[str] = None
    netto_mese: Optional[float] = None
    acconto = 0.0
    mansione: Optional[str] = None
    contratto_scadenza: Optional[str] = None

    # Estrai nome dipendente
    for line in lines:
        match = re.match(r'(\d{7})\s+([A-Z]+\s+[A-Z]+)(?:\s+([A-Z]{16}))?', line)
        if match:
            employee_name = match.group(2).strip()
            logger.info(f"👤 Amministratore: {employee_name}")
            break

    if not employee_name:
        return None

    # Determina mansione
    for line in lines:
        if '*000003' in line or '000003' in line or 'Compenso Amministratore' in line:
            mansione = "Amministratore"
            break
        elif '000004' in line or 'Compenso Tirocinante' in line:
            mansione = "Tirocinante"
            break

    # Estrai scadenza contratto
    for line in lines:
        if 'T.Deter.' in line or 'Tir./Stag.' in line or 'Co.Co.Co' in line:
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', line)
            if date_match:
                contratto_scadenza = normalize_date(date_match.group(1))
                break

    # Estrai acconto
    for line in lines:
        if 'Recupero' in line and 'acconto' in line:
            amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', line)
            if amounts:
                for amt in amounts:
                    amt_clean = amt.replace('.', '').replace(',', '.')
                    val = safe_float(amt_clean, 0.0)
                    if val > acconto:
                        acconto = val
            break

    # Estrai NETTO DEL MESE
    for i, line in enumerate(lines):
        if 'NETTO' in line and ('MESE' in line or 'DEL' in line):
            for j in range(i, min(i+5, len(lines))):
                search_line = lines[j]
                amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*€?', search_line)
                if amounts:
                    for amt in amounts:
                        amt_clean = amt.replace('.', '').replace(',', '.')
                        val = safe_float(amt_clean, 0.0)
                        if 0 <= val <= 50000:
                            netto_mese = val
                            break
                if netto_mese:
                    break
            break

    if not netto_mese:
        logger.warning(f"⚠️ No netto found for {employee_name}")
        return None

    return {
        "nome": employee_name,
        "netto": acconto + netto_mese,
        "acconto": acconto,
        "differenza": netto_mese,
        "note": f"Acconto: €{acconto:.2f}" if acconto > 0 else "Nessun acconto",
        "ore_ordinarie": 0.0,
        "mansione": mansione,
        "contratto_scadenza": contratto_scadenza
    }


def parse_libro_unico_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parsifica un PDF Libro Unico ed estrae dati stipendi/presenze.
    
    Args:
        pdf_bytes: Bytes del file PDF
        
    Returns:
        Dict con:
            - competenza_month_year: Mese di competenza (YYYY-MM)
            - competenza_detected: True se rilevato automaticamente
            - presenze: Lista record presenze
            - salaries: Lista dati stipendi
            - employees: Lista metadati dipendenti
    """
    try:
        import pdfplumber
    except ImportError:
        raise ParsingError("pdfplumber non installato. Esegui: pip install pdfplumber")
    
    if not pdf_bytes:
        raise ParsingError("Empty PDF bytes provided")

    try:
        salaries_data: List[Dict[str, Any]] = []
        presenze_data: List[Dict[str, Any]] = []
        employees_found: Dict[str, Dict[str, Any]] = {}
        competenza_month: Optional[str] = None
        competenza_detected = False

        logger.info(f"📦 Received PDF bytes: {len(pdf_bytes)} bytes")

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            logger.info(f"📄 Processing PDF with {len(pdf.pages)} pages")

            pdf_type = 'dipendente'

            if len(pdf.pages) > 0:
                first_page_text = pdf.pages[0].extract_text() or ""
                first_page_text = normalize_pdf_text(first_page_text)
                competenza_month, competenza_detected = extract_competenza_month(first_page_text)

            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                page_text = normalize_pdf_text(page_text)

                logger.info(f"📄 Processing page {page_num+1}")

                pdf_type = detect_pdf_type(page_text)
                logger.info(f"📋 PDF Type: {pdf_type}")

                if pdf_type == 'amministratore':
                    emp_data = parse_amministratore_page(page_text)
                    if emp_data and emp_data["nome"] not in employees_found:
                        employees_found[emp_data["nome"]] = emp_data
                else:
                    # Dipendente normale
                    lines = page_text.split('\n')

                    employee_name: Optional[str] = None
                    netto_mese: Optional[float] = None
                    acconto = 0.0
                    ore_ordinarie = 0.0
                    mansione: Optional[str] = None
                    contratto_scadenza: Optional[str] = None

                    # Estrai nome
                    for line in lines:
                        match = re.match(r'(\d{7})\s+([A-Z]+\s+[A-Z]+)(?:\s+([A-Z]{16}))?', line)
                        if match:
                            employee_name = match.group(2).strip()
                            logger.info(f"👤 Employee: {employee_name}")
                            break

                    if not employee_name:
                        continue

                    # Estrai mansione
                    for line in lines:
                        for keyword in ['CAMERIERE', 'CUOCO', 'BARISTA', 'AIUTO', 'LAVAPIATTI', 'PASTICCERE', 'PIZZAIOLO', 'COMMESSO']:
                            if keyword in line:
                                mansione = keyword
                                break
                        if mansione:
                            break

                    # Estrai scadenza contratto
                    for line in lines:
                        if 'T.Deter.' in line or 'Contratto' in line or 'Scadenza' in line:
                            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', line)
                            if date_match:
                                contratto_scadenza = normalize_date(date_match.group(1))
                                break

                    # Estrai ore
                    for line in lines:
                        if 'Ore ordinarie' in line or ('Ore' in line and 'ordinarie' in line):
                            hours_match = re.search(r'(\d+[.,]\d+)', line)
                            if hours_match:
                                ore_ordinarie = safe_float(hours_match.group(1).replace(',', '.'), 0.0)
                            break

                        if re.search(r'\d+\s+(\d+,\d{2})\s*$', line):
                            parts = line.split()
                            if len(parts) >= 2:
                                try:
                                    candidate_hours = safe_float(parts[-1].replace(',', '.'), 0.0)
                                    if 1 <= candidate_hours <= 250:
                                        ore_ordinarie = candidate_hours
                                        break
                                except:
                                    pass

                    # Estrai stipendio
                    for i, line in enumerate(lines):
                        if ('Recupero' in line and 'acconto' in line) or '000306' in line:
                            amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', line)
                            if amounts:
                                max_val = 0.0
                                for amt in amounts:
                                    amt_clean = amt.replace('.', '').replace(',', '.')
                                    val = safe_float(amt_clean, 0.0)
                                    if val > max_val:
                                        max_val = val
                                if max_val > 0:
                                    acconto = max_val

                        if 'NETTO' in line and 'MESE' in line:
                            for j in range(i, min(i+5, len(lines))):
                                search_line = lines[j]
                                amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*€?', search_line)
                                if amounts:
                                    max_val = 0.0
                                    for amt in amounts:
                                        amt_clean = amt.replace('.', '').replace(',', '.')
                                        val = safe_float(amt_clean, 0.0)
                                        if 0 <= val <= 10000 and val >= max_val:
                                            max_val = val
                                    if max_val >= 0:
                                        netto_mese = max_val
                            if netto_mese is not None:
                                break

                    # Salva dati
                    if employee_name and netto_mese is not None:
                        if employee_name not in employees_found:
                            employees_found[employee_name] = {
                                "nome": employee_name,
                                "netto": acconto + netto_mese,
                                "acconto": acconto,
                                "differenza": netto_mese,
                                "note": f"Acconto: €{acconto:.2f}" if acconto > 0 else "Nessun acconto",
                                "ore_ordinarie": ore_ordinarie,
                                "mansione": mansione,
                                "contratto_scadenza": contratto_scadenza
                            }

        # Converti in liste
        employees_list: List[Dict[str, Any]] = []
        for emp_data in employees_found.values():
            salaries_data.append({
                "nome": emp_data["nome"],
                "netto": emp_data["netto"],
                "acconto": emp_data["acconto"],
                "differenza": emp_data["differenza"],
                "note": emp_data["note"]
            })

            presenze_data.append({
                "nome": emp_data["nome"],
                "ore_ordinarie": emp_data["ore_ordinarie"],
                "assenze_ingiustificate": 0,
                "ferie": 0,
                "permessi": 0,
                "malattia": 0
            })

            employees_list.append({
                "full_name": emp_data["nome"],
                "mansione": emp_data.get("mansione"),
                "contratto_scadenza": emp_data.get("contratto_scadenza")
            })

        logger.info(f"✅ Successfully parsed: {len(salaries_data)} employees")

        return {
            'competenza_month_year': competenza_month,
            'competenza_detected': competenza_detected,
            'presenze': presenze_data,
            'salaries': salaries_data,
            'employees': employees_list
        }

    except Exception as e:
        logger.error(f"❌ Parsing error: {str(e)}")
        raise ParsingError(f"Failed to parse Libro Unico PDF: {str(e)}") from e
