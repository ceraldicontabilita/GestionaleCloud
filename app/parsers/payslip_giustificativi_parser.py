"""
Parser per estrazione giustificativi da buste paga (Libro Unico).

Estrae:
- Nome dipendente
- Codice fiscale
- Periodo (mese/anno)
- Ore per tipo di giustificativo (FE=Ferie, RL=ROL, MA=Malattia, AI=Assenza, etc.)

Questo parser legge i PDF del "Libro Unico del Lavoro" che contengono
il dettaglio giornaliero e il riepilogo dei giustificativi utilizzati.
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Mappatura codici giustificativi dal Libro Unico ai codici standard
CODICI_GIUSTIFICATIVI_MAP = {
    'FE': 'FER',      # Ferie
    'RL': 'ROL',      # Riduzione Orario Lavoro
    'MA': 'MAL',      # Malattia
    'AI': 'AI',       # Assenza Ingiustificata
    'PE': 'PER',      # Permesso
    'PNR': 'PNR',     # Permesso Non Retribuito
    'EF': 'EXF',      # Ex Festività
    'IN': 'INF',      # Infortunio
    'CP': 'CP',       # Congedo Parentale
    'CM': 'CMAT',     # Congedo Maternità/Matrimonio
    'CL': 'CLUT',     # Congedo Lutto
    'DO': 'DON',      # Donazione Sangue
    'L1': 'L104',     # Legge 104
    'ST': 'STUD',     # Studio
    'TR': 'TRAS',     # Trasferta
    'SM': 'SMART',    # Smart Working
    'VS': 'VIS',      # Visita Medica
    'MF': 'MALF',     # Malattia Figlio
    'AS': 'AS',       # Aspettativa
}

# Mesi italiani
MESI_ITALIANI = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
}


def parse_importo(s: str) -> float:
    """Converte stringa in float (gestisce formato italiano con hm = ore minuti)."""
    if not s:
        return 0.0
    s = s.strip().replace(' ', '').replace('hm', '').replace('h', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_periodo_libro_unico(text: str) -> Tuple[Optional[int], Optional[int], str]:
    """Estrae mese e anno dal Libro Unico."""
    text_lower = text.lower()
    
    # Pattern: "PERIODO DI RIFERIMENTO" seguito da "Mese Anno"
    for mese_nome, mese_num in MESI_ITALIANI.items():
        pattern = rf'{mese_nome}\s+(\d{{4}})'
        match = re.search(pattern, text_lower)
        if match:
            anno = int(match.group(1))
            return mese_num, anno, f"{mese_num:02d}/{anno}"
    
    # Fallback: MM/YYYY
    match = re.search(r'\b(\d{1,2})[/\-](\d{4})\b', text)
    if match:
        mese = int(match.group(1))
        anno = int(match.group(2))
        if 1 <= mese <= 12:
            return mese, anno, f"{mese:02d}/{anno}"
    
    return None, None, ""


def extract_dipendente_info(text: str) -> Dict[str, Any]:
    """Estrae nome dipendente e CF dal Libro Unico."""
    result = {"nome": None, "cognome": None, "nome_completo": None, "codice_fiscale": None}
    
    lines = text.split('\n')
    
    # Cerca "COGNOME NOME e INDIRIZZO" header
    for i, line in enumerate(lines):
        if 'COGNOME' in line.upper() and 'NOME' in line.upper():
            # Il nome è solitamente 1-2 righe dopo
            for j in range(i + 1, min(i + 5, len(lines))):
                next_line = lines[j].strip()
                # Skip linee con numeri/codici iniziali
                if re.match(r'^\d+/', next_line):
                    continue
                # Nome valido: 2+ parole, lettere
                if re.match(r'^[A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+', next_line):
                    parts = next_line.split()
                    if len(parts) >= 2:
                        result["cognome"] = parts[0].title()
                        result["nome"] = " ".join(parts[1:]).title()
                        result["nome_completo"] = f"{result['cognome']} {result['nome']}"
                        break
    
    # Estrai CF
    cf_match = re.search(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', text)
    if cf_match:
        result["codice_fiscale"] = cf_match.group(1)
    
    return result


def extract_giustificativi_riepilogo(text: str) -> Dict[str, float]:
    """
    Estrae i giustificativi dalla sezione riepilogo del Libro Unico.
    
    Pattern cercato:
    "CODICE GIUSTIFICATIVI QUANTITA'"
    "FE Ferie 33,20hm"
    """
    giustificativi = {}
    
    # Pattern: CODICE (2-4 lettere) + descrizione + numero con hm
    # Es: "FE Ferie 33,20hm" o "AI Ass.za ingiustif. 53,20hm"
    pattern = r'([A-Z]{2,4})\s+([A-Za-z\.\'\s]+?)\s+(\d+[,\.]\d+)\s*h'
    
    matches = re.findall(pattern, text)
    
    # Codici da escludere (parole che matchano per errore)
    ESCLUDI = {'DICE', 'ARIE', 'ARIO', 'DINA', 'ORDI'}
    
    for code, desc, qty in matches:
        code = code.strip().upper()
        
        # Skip codici invalidi
        if code in ESCLUDI:
            continue
        
        ore = parse_importo(qty)
        
        # Mappa al codice standard se esiste
        standard_code = CODICI_GIUSTIFICATIVI_MAP.get(code, code)
        
        if ore > 0:
            giustificativi[standard_code] = ore
            logger.debug(f"Giustificativo trovato: {code} -> {standard_code} = {ore}h")
    
    # Estrai anche "Ore ordinarie"
    ore_ord_match = re.search(r'[Oo]re\s+ordinarie\s+(\d+[,\.]\d+)', text)
    if ore_ord_match:
        giustificativi['ORE_ORDINARIE'] = parse_importo(ore_ord_match.group(1))
    
    return giustificativi


def parse_libro_unico_pdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parser per Libro Unico del Lavoro.
    
    Estrae per ogni dipendente:
    - Dati anagrafici (nome, CF)
    - Periodo (mese/anno)
    - Giustificativi utilizzati con ore
    
    Args:
        pdf_bytes: Contenuto binario del PDF
        
    Returns:
        Lista di dict con i dati estratti per ogni dipendente
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
            logger.info(f"Parsing Libro Unico con {len(pdf.pages)} pagine")
            
            # Ogni dipendente può avere 1+ pagine nel Libro Unico
            current_dipendente = None
            current_text = ""
            
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                
                # Identifica nuova sezione dipendente (cerca header con nome)
                is_new_section = 'COGNOME NOME' in page_text.upper() or 'INFORMAZIONI AGGIUNTIVE' in page_text
                
                if is_new_section:
                    # Processa dipendente precedente se esiste
                    if current_text and current_dipendente:
                        giust = extract_giustificativi_riepilogo(current_text)
                        if giust:
                            current_dipendente["giustificativi"] = giust
                            results.append(current_dipendente)
                    
                    # Estrai info nuovo dipendente
                    dip_info = extract_dipendente_info(page_text)
                    mese, anno, periodo_str = extract_periodo_libro_unico(page_text)
                    
                    if dip_info.get("nome_completo"):
                        current_dipendente = {
                            **dip_info,
                            "mese": mese,
                            "anno": anno,
                            "periodo": periodo_str,
                            "giustificativi": {}
                        }
                        current_text = page_text
                    else:
                        current_dipendente = None
                        current_text = ""
                else:
                    # Aggiungi testo alla sezione corrente
                    current_text += "\n" + page_text
            
            # Processa ultimo dipendente
            if current_text and current_dipendente:
                giust = extract_giustificativi_riepilogo(current_text)
                if giust:
                    current_dipendente["giustificativi"] = giust
                    results.append(current_dipendente)
    
    except Exception as e:
        logger.error(f"Errore parsing Libro Unico: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return [{"error": str(e)}]
    
    if not results:
        logger.warning("Nessun dipendente trovato nel Libro Unico")
        return [{"error": "Nessun dipendente trovato nel PDF"}]
    
    logger.info(f"Estratti {len(results)} dipendenti dal Libro Unico")
    return results


def parse_riepilogo_paghe_pdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parser per Riepilogo Paghe (formato più semplice, solo totali).
    """
    # Per ora usa lo stesso parser del Libro Unico
    # Potrebbe essere esteso per formati specifici
    return parse_libro_unico_pdf(pdf_bytes)


def parse_payslip_with_giustificativi(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parser unificato che tenta di estrarre giustificativi da qualsiasi formato PDF.
    
    Prova prima il parser Libro Unico, poi quello semplice.
    """
    # Prova parser Libro Unico
    results = parse_libro_unico_pdf(pdf_bytes)
    
    # Se ha trovato giustificativi, restituisci i risultati
    if results and not results[0].get("error"):
        has_giust = any(r.get("giustificativi") for r in results)
        if has_giust:
            return results
    
    # Fallback: parser semplice (senza giustificativi)
    from app.parsers.payslip_parser_simple import parse_payslip_simple
    simple_results = parse_payslip_simple(pdf_bytes)
    
    # Aggiungi struttura giustificativi vuota per compatibilità
    for r in simple_results:
        if not r.get("error"):
            r["giustificativi"] = {}
    
    return simple_results
