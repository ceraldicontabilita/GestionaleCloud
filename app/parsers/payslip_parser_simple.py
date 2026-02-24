"""
Parser semplificato per buste paga (cedolini).

Estrae SOLO:
- Nome dipendente
- Periodo (mese/anno)
- Importo netto

Questo parser è più robusto e meno sensibile ai diversi layout dei PDF.
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Mesi italiani
MESI_ITALIANI = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
}


def parse_importo(s: str) -> float:
    """Converte stringa in float (gestisce formato italiano)."""
    if not s:
        return 0.0
    # Rimuovi spazi e caratteri non numerici (eccetto . e ,)
    s = s.strip().replace(' ', '')
    # Formato italiano: 1.234,56 -> 1234.56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_periodo(text: str) -> Tuple[Optional[int], Optional[int], str]:
    """
    Estrae mese e anno dal testo del PDF.
    
    Cerca pattern comuni:
    - "Gennaio 2025", "FEBBRAIO 2025"
    - "01/2025", "12/2025"
    - "competenza: 01/2025"
    - "periodo di paga: 01/2025"
    - "dal 01/01/2025 al 31/01/2025"
    
    Returns:
        Tuple[mese, anno, periodo_str]
    """
    text_lower = text.lower()
    
    # Pattern 1: Mese italiano + anno (es. "Gennaio 2025")
    for mese_nome, mese_num in MESI_ITALIANI.items():
        pattern = rf'\b{mese_nome}\s*[:\-]?\s*(\d{{4}})\b'
        match = re.search(pattern, text_lower)
        if match:
            anno = int(match.group(1))
            return mese_num, anno, f"{mese_num:02d}/{anno}"
    
    # Pattern 2: MM/YYYY o MM-YYYY (es. "01/2025")
    match = re.search(r'\b(\d{1,2})[/\-](\d{4})\b', text)
    if match:
        mese = int(match.group(1))
        anno = int(match.group(2))
        if 1 <= mese <= 12:
            return mese, anno, f"{mese:02d}/{anno}"
    
    # Pattern 3: dal DD/MM/YYYY al DD/MM/YYYY
    match = re.search(r'dal\s+\d{1,2}/(\d{1,2})/(\d{4})\s+al', text_lower)
    if match:
        mese = int(match.group(1))
        anno = int(match.group(2))
        if 1 <= mese <= 12:
            return mese, anno, f"{mese:02d}/{anno}"
    
    return None, None, ""


def extract_nome(text: str) -> Optional[str]:
    """
    Estrae il nome del dipendente dal testo del PDF.
    
    Cerca pattern comuni:
    - Dopo "COGNOME NOME"
    - Matricola + Nome
    - Nome in maiuscolo su linea singola
    """
    lines = text.split('\n')
    
    # Pattern 1: Matricola (7 cifre) + NOME COGNOME
    for line in lines:
        match = re.match(r'^\d{7}\s+([A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+)', line)
        if match:
            return match.group(1).strip()
    
    # Pattern 2: COGNOME tutto maiuscolo + Nome
    for i, line in enumerate(lines):
        line = line.strip()
        # Linea con solo nome in maiuscolo (2+ parole)
        if re.match(r'^[A-Z]{2,}\s+[A-Z]{2,}$', line):
            # Verifica che non sia un'intestazione
            if not any(kw in line for kw in ['COGNOME', 'NOME', 'INDIRIZZO', 'DATA', 'PERIODO', 'TOTALE']):
                return line.title()  # Converte in Title Case
    
    # Pattern 3: Cerca CF e prendi il nome dalla riga precedente
    for i, line in enumerate(lines):
        # Codice fiscale italiano (16 caratteri)
        if re.search(r'\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b', line):
            # Cerca nome nella stessa riga o riga precedente
            name_match = re.search(r'([A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+)\s+[A-Z]{6}\d{2}', line)
            if name_match:
                return name_match.group(1)
            if i > 0:
                prev = lines[i-1].strip()
                if re.match(r'^[A-Za-z]+\s+[A-Za-z]+$', prev):
                    return prev.title()
    
    return None


def extract_netto(text: str) -> float:
    """
    Estrae l'importo netto dal testo del PDF.
    
    Cerca pattern comuni:
    - "NETTO DEL MESE" seguito da importo
    - "NETTO A PAGARE" seguito da importo
    - "TOTALE NETTO" seguito da importo
    - Importo con "+" finale (formato Smart Forms)
    
    IMPORTANTE: Esclude valori in LIRE (vecchia valuta italiana)
    """
    lines = text.split('\n')
    text_upper = text.upper()
    
    # Pattern 1: NETTO DEL MESE / NETTO A PAGARE / TOTALE NETTO
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if 'NETTO' in line_upper and any(kw in line_upper for kw in ['MESE', 'PAGARE', 'TOTALE', 'DEL']):
            # SKIP se è la riga delle LIRE (vecchia valuta)
            if 'LIRE' in line_upper or 'LIT' in line_upper:
                continue
            # Cerca importo nella stessa riga o nelle righe successive
            for j in range(i, min(i + 5, len(lines))):
                # SKIP linee che contengono "LIRE"
                if 'LIRE' in lines[j].upper() or 'LIT' in lines[j].upper():
                    continue
                # Cerca importi nel formato italiano (1.234,56 o 1234,56)
                amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', lines[j])
                for amt in amounts:
                    val = parse_importo(amt)
                    # Range ragionevole per stipendio EURO (non LIRE)
                    # Stipendi italiani tipicamente tra 500€ e 10.000€ netti
                    if 100 <= val <= 15000:
                        return val
    
    # Pattern 2: Importo con "+" finale (Smart Forms) - ma NON in LIRE
    for line in reversed(lines):
        # SKIP linee con LIRE
        if 'LIRE' in line.upper() or 'LIT' in line.upper():
            continue
        match = re.search(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\+', line)
        if match:
            val = parse_importo(match.group(1))
            # Range realistico per Euro
            if 100 <= val <= 15000:
                return val
    
    # Pattern 3: Cerca "EURO" + importo esplicito
    for i, line in enumerate(lines):
        if 'EURO' in line.upper() or '€' in line:
            amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', line)
            for amt in amounts:
                val = parse_importo(amt)
                if 100 <= val <= 15000:
                    return val
    
    # Pattern 4: Ultima riga con importo significativo (fallback)
    for line in reversed(lines):
        if 'LIRE' in line.upper():
            continue
        amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', line)
        for amt in reversed(amounts):
            val = parse_importo(amt)
            if 500 <= val <= 8000:  # Range ristretto per fallback
                return val
    
    return 0.0


def extract_codice_fiscale(text: str) -> Optional[str]:
    """Estrae il codice fiscale dal testo."""
    match = re.search(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', text)
    return match.group(1) if match else None


def parse_payslip_simple(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parser semplificato per buste paga.
    
    Estrae solo: nome, periodo (mese/anno), netto.
    
    Args:
        pdf_bytes: Contenuto binario del PDF
        
    Returns:
        Lista di dict con i dati estratti per ogni dipendente trovato
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber non installato")
        return [{"error": "pdfplumber non installato"}]
    
    if not pdf_bytes:
        return [{"error": "PDF vuoto"}]
    
    results = []
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            logger.info(f"Parsing PDF con {len(pdf.pages)} pagine")
            
            # Estrai tutto il testo
            full_text = ""
            page_texts = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_texts.append(page_text)
                full_text += page_text + "\n"
            
            # Estrai periodo (di solito uguale per tutto il documento)
            mese, anno, periodo_str = extract_periodo(full_text[:2000])
            logger.info(f"Periodo estratto: {periodo_str}")
            
            # Analizza ogni pagina per trovare dipendenti
            # Usa nome UPPERCASE per evitare duplicati da case diverso
            processed_names = set()
            
            for page_num, page_text in enumerate(page_texts):
                nome = extract_nome(page_text)
                
                if not nome:
                    continue
                
                # Normalizza nome per confronto (uppercase)
                nome_key = nome.upper().strip()
                if nome_key in processed_names:
                    continue
                
                # Evita di processare lo stesso nome due volte
                processed_names.add(nome_key)
                
                # Estrai CF e netto dalla pagina
                cf = extract_codice_fiscale(page_text)
                netto = extract_netto(page_text)
                
                if netto == 0:
                    # Prova a cercare nelle pagine successive (alcuni formati hanno dati su più pagine)
                    for next_page in page_texts[page_num + 1:page_num + 3]:
                        netto = extract_netto(next_page)
                        if netto > 0:
                            break
                
                if netto > 0:
                    # Normalizza nome in Title Case
                    nome_normalized = nome.title()
                    logger.info(f"Trovato: {nome_normalized} - {periodo_str} - €{netto:.2f}")
                    results.append({
                        "nome_completo": nome_normalized,
                        "cognome": nome_normalized.split()[0] if nome_normalized else "",
                        "nome": " ".join(nome_normalized.split()[1:]) if nome_normalized and len(nome_normalized.split()) > 1 else "",
                        "codice_fiscale": cf or "",
                        "periodo": periodo_str,
                        "mese": str(mese) if mese else "",
                        "anno": str(anno) if anno else "",
                        "retribuzione_netta": netto,
                        "netto": netto,  # Alias per compatibilità
                        "acconto": 0.0,
                        "differenza": netto
                    })
    
    except Exception as e:
        logger.error(f"Errore parsing PDF: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return [{"error": str(e)}]
    
    if not results:
        logger.warning("Nessun cedolino estratto dal PDF")
        return [{"error": "Nessun cedolino trovato nel PDF. Verifica il formato del file."}]
    
    return results


def extract_payslips_from_pdf_simple(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Wrapper per compatibilità - legge PDF da percorso file.
    
    Args:
        pdf_path: Percorso del file PDF
        
    Returns:
        Lista di cedolini estratti
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        return parse_payslip_simple(pdf_bytes)
    except Exception as e:
        logger.error(f"Errore lettura file {pdf_path}: {e}")
        return [{"error": f"Errore lettura file: {e}"}]
