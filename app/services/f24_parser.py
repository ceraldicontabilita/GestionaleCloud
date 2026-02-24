"""
Parser Quietanze F24
Estrazione automatica dati da PDF quietanze F24 Agenzia delle Entrate
"""
import os
import re
import fitz  # PyMuPDF
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


def parse_importo(value: str) -> float:
    """Converte stringa importo italiano in float."""
    if not value or value.strip() == "":
        return 0.0
    # Rimuovi spazi e sostituisci separatori
    value = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(value)
    except:
        return 0.0


def parse_data(value: str) -> Optional[str]:
    """Converte data italiana DD/MM/YYYY in ISO format."""
    if not value or value.strip() == "":
        return None
    value = value.strip()
    # Prova vari formati
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except:
            continue
    return value


def extract_text_from_pdf(pdf_path: str = None, pdf_content: bytes = None) -> str:
    """
    Estrae tutto il testo da un PDF.
    Supporta sia filepath (legacy) che bytes (architettura MongoDB-only).
    """
    try:
        if pdf_content:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
        elif pdf_path:
            doc = fitz.open(pdf_path)
        else:
            return ""
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"Errore estrazione PDF: {e}")
        return ""


def parse_quietanza_f24(pdf_path: str = None, pdf_content: bytes = None) -> Dict[str, Any]:
    """
    Parsa una quietanza F24 ed estrae tutti i dati strutturati.
    Supporta sia filepath (legacy) che bytes (MongoDB-only).
    
    Args:
        pdf_path: Percorso file PDF (legacy)
        pdf_content: Contenuto PDF in bytes (architettura MongoDB-only)
    
    Returns:
        Dict con:
        - dati_generali: codice_fiscale, ragione_sociale, data_pagamento, etc.
        - sezione_erario: lista tributi erario
        - sezione_inps: lista contributi INPS
        - sezione_inail: lista contributi INAIL
        - sezione_regioni: lista tributi regionali
        - sezione_tributi_locali: lista tributi locali
        - totali: importo_debito, importo_credito, saldo
    """
    text = extract_text_from_pdf(pdf_path=pdf_path, pdf_content=pdf_content)
    
    if not text:
        return {"error": "Impossibile estrarre testo dal PDF"}
    
    result = {
        "dati_generali": {},
        "sezione_erario": [],
        "sezione_inps": [],
        "sezione_inail": [],
        "sezione_regioni": [],
        "sezione_tributi_locali": [],
        "totali": {},
        "raw_text_preview": text[:200]  # Solo per debug
    }
    
    # ============================================
    # DATI GENERALI
    # ============================================
    
    # Codice Fiscale - dopo "Soggetto:" o "CODICE FISCALE"
    cf_patterns = [
        r'Soggetto:\s*[A-Z\s\.]+\(\s*(\d{11})\s*\)',
        r'Utente:\s*(\d{11})',
        r'\(\s*(\d{11})\s*\)',
    ]
    for pattern in cf_patterns:
        cf_match = re.search(pattern, text, re.IGNORECASE)
        if cf_match:
            result["dati_generali"]["codice_fiscale"] = cf_match.group(1)
            break
    
    # Ragione Sociale - dopo "Soggetto:"
    rs_match = re.search(r'Soggetto:\s*([A-Z][A-Z\s\.]+(?:S\.R\.L\.|S\.P\.A\.|S\.N\.C\.|S\.A\.S\.))', text)
    if rs_match:
        result["dati_generali"]["ragione_sociale"] = rs_match.group(1).strip()
    else:
        # Fallback: cerca CERALDI GROUP S.R.L. o simili
        rs_match2 = re.search(r'([A-Z][A-Z\s]+(?:S\.R\.L\.|S\.P\.A\.|S\.N\.C\.|S\.A\.S\.))', text)
        if rs_match2:
            result["dati_generali"]["ragione_sociale"] = rs_match2.group(1).strip()
    
    # Protocollo Telematico - numero di 17 cifre
    pt_match = re.search(r'(\d{17})', text)
    if pt_match:
        result["dati_generali"]["protocollo_telematico"] = pt_match.group(1)
    
    # Data e Ora documento
    data_ora_match = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})\s*-\s*Ore:\s*(\d{2}:\d{2}:\d{2})', text)
    if data_ora_match:
        result["dati_generali"]["data_documento"] = parse_data(data_ora_match.group(1))
        result["dati_generali"]["ora_documento"] = data_ora_match.group(2)
    
    # Data del versamento - pattern con cifre separate
    # Pattern: 1 7 0 1 2 0 2 5 (17/01/2025)
    data_vers_match = re.search(r'(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+05034', text)
    if data_vers_match:
        giorno = data_vers_match.group(1) + data_vers_match.group(2)
        mese = data_vers_match.group(3) + data_vers_match.group(4)
        anno = data_vers_match.group(5) + data_vers_match.group(6) + data_vers_match.group(7) + data_vers_match.group(8)
        result["dati_generali"]["data_pagamento"] = f"{anno}-{mese}-{giorno}"
    
    # Saldo Delega - pattern: 5.498,79 o simile prima di ABI
    saldo_patterns = [
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*05034',  # Prima di data e ABI
        r'Saldo\s*delega\s*[\n\s]*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})',
        r',\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*\n',
    ]
    for pattern in saldo_patterns:
        saldo_match = re.search(pattern, text)
        if saldo_match:
            result["dati_generali"]["saldo_delega"] = parse_importo(saldo_match.group(1))
            break
    
    # ABI e CAB
    abi_match = re.search(r'\b(05034|03069|01030|03002|02008)\b', text)
    if abi_match:
        result["dati_generali"]["abi"] = abi_match.group(1)
    
    cab_match = re.search(r'05034\s*\n?\s*(\d{5})', text)
    if cab_match:
        result["dati_generali"]["cab"] = cab_match.group(1)
    
    # ============================================
    # SEZIONE ERARIO
    # ============================================
    # Pattern: ERARIO 1001 12 2024 2.610,51 0,00
    
    erario_pattern = r'ERARIO\s+(\d{4})\s+(\d{0,2})\s*(\d{4})\s+([0-9.,]+)\s+([0-9.,]+)'
    for match in re.finditer(erario_pattern, text):
        codice = match.group(1)
        mese = match.group(2) or "00"
        anno = match.group(3)
        debito = parse_importo(match.group(4))
        credito = parse_importo(match.group(5))
        
        periodo = f"{mese}/{anno}" if mese != "00" else anno
        
        result["sezione_erario"].append({
            "codice_tributo": codice,
            "periodo_riferimento": periodo,
            "importo_debito": debito,
            "importo_credito": credito,
            "descrizione": get_descrizione_tributo_erario(codice)
        })
    
    # ============================================
    # SEZIONE INPS
    # ============================================
    # Pattern: INPS 5100 DM10 5124776507 12 2024 3.628,00 0,00
    
    inps_pattern = r'INPS\s+(\d{4})\s+(DM10|CXX|RC01|C10|CF10)\s+([A-Z0-9]+)\s+(\d{1,2})\s+(\d{4})\s+([0-9.,]+)\s+([0-9.,]+)'
    for match in re.finditer(inps_pattern, text):
        result["sezione_inps"].append({
            "codice_sede": match.group(1),
            "causale": match.group(2),
            "matricola": match.group(3),
            "periodo_riferimento": f"{match.group(4)}/{match.group(5)}",
            "importo_debito": parse_importo(match.group(6)),
            "importo_credito": parse_importo(match.group(7)),
            "descrizione": get_descrizione_causale_inps(match.group(2))
        })
    
    # ============================================
    # SEZIONE INAIL
    # ============================================
    # Pattern: INAIL con codice ufficio e atto
    
    inail_pattern = r'INAIL\s+(\d{5})\s+(\d+)\|([A-Z0-9\s]+)\s+([0-9.,]+)\s+([0-9.,]+)'
    for match in re.finditer(inail_pattern, text):
        result["sezione_inail"].append({
            "codice_ufficio": match.group(1),
            "codice_atto": match.group(2),
            "estremi_identificativi": match.group(3).strip(),
            "importo_debito": parse_importo(match.group(4)),
            "importo_credito": parse_importo(match.group(5))
        })
    
    # ============================================
    # SEZIONE REGIONI
    # ============================================
    # Pattern: REGIONI 05 3802 00/12 2024 142,55 0,00
    
    regioni_pattern = r'REGIONI\s+(\d{2})\s+(\d{4})\s+(\d{2}/\d{2})\s*(\d{4})\s+([0-9.,]+)\s+([0-9.,]+)'
    for match in re.finditer(regioni_pattern, text):
        result["sezione_regioni"].append({
            "codice_regione": match.group(1),
            "codice_tributo": match.group(2),
            "periodo_riferimento": f"{match.group(3)} {match.group(4)}",
            "importo_debito": parse_importo(match.group(5)),
            "importo_credito": parse_importo(match.group(6)),
            "descrizione": get_descrizione_tributo_regioni(match.group(2))
        })
    
    # ============================================
    # SEZIONE TRIBUTI LOCALI (IMU, TARI, etc.)
    # ============================================
    # Pattern: TRIB.LOCALI F839 1671 2024 0,00 32,73
    
    locali_pattern = r'TRIB\.LOCALI\s+([A-Z]\d{3})\s+(\d{4})\s+(\d{4})\s+([0-9.,]+)\s+([0-9.,]+)'
    for match in re.finditer(locali_pattern, text):
        result["sezione_tributi_locali"].append({
            "codice_comune": match.group(1),
            "codice_tributo": match.group(2),
            "periodo_riferimento": match.group(3),
            "importo_debito": parse_importo(match.group(4)),
            "importo_credito": parse_importo(match.group(5)),
            "descrizione": get_descrizione_tributo_locale(match.group(2))
        })
    
    # ============================================
    # CALCOLO TOTALI
    # ============================================
    
    totale_debito = 0.0
    totale_credito = 0.0
    
    for sezione in [result["sezione_erario"], result["sezione_inps"], 
                    result["sezione_inail"], result["sezione_regioni"], 
                    result["sezione_tributi_locali"]]:
        for item in sezione:
            totale_debito += item.get("importo_debito", 0)
            totale_credito += item.get("importo_credito", 0)
    
    result["totali"] = {
        "totale_debito": round(totale_debito, 2),
        "totale_credito": round(totale_credito, 2),
        "saldo_netto": round(totale_debito - totale_credito, 2),
        "saldo_delega": result["dati_generali"].get("saldo_delega", 0)
    }
    
    # Rimuovi raw_text prima di restituire
    del result["raw_text_preview"]
    
    return result


def get_descrizione_tributo_erario(codice: str) -> str:
    """Descrizione codici tributo Erario."""
    descrizioni = {
        "1001": "Ritenute su redditi di lavoro dipendente",
        "1040": "Ritenute su redditi di lavoro autonomo",
        "1038": "Ritenute su interessi e altri redditi di capitale",
        "1627": "Eccedenza di versamenti di ritenute",
        "1631": "Credito d'imposta art. 3 DL 73/2021",
        "1701": "Credito per prestazioni lavoro dipendente",
        "1703": "Credito d'imposta per canoni di locazione",
        "1704": "TFR pagato dal datore di lavoro",
        "1712": "Acconto addizionale comunale IRPEF",
        "1713": "Saldo addizionale comunale IRPEF",
        "6001": "IVA mensile gennaio",
        "6002": "IVA mensile febbraio",
        "6013": "IVA acconto",
        "6015": "IVA 1° trimestre",
        "6099": "IVA annuale",
        "3843": "Addizionale comunale IRPEF - Autotassazione",
        "3844": "Addizionale regionale IRPEF - Autotassazione",
    }
    return descrizioni.get(codice, f"Tributo {codice}")


def get_descrizione_causale_inps(causale: str) -> str:
    """Descrizione causali INPS."""
    descrizioni = {
        "DM10": "Contributi previdenziali dipendenti",
        "CXX": "Contributi gestione separata",
        "RC01": "Contributi artigiani/commercianti",
        "C10": "Contributi cassa edile",
        "CF10": "Contributi fondo pensione",
    }
    return descrizioni.get(causale, f"Contributo {causale}")


def get_descrizione_tributo_regioni(codice: str) -> str:
    """Descrizione codici tributo regionali."""
    descrizioni = {
        "3801": "Addizionale regionale IRPEF - sostituto d'imposta",
        "3802": "Addizionale regionale IRPEF",
        "3805": "Addizionale regionale IRPEF - rata",
        "3843": "Addizionale regionale IRPEF - autotassazione",
    }
    return descrizioni.get(codice, f"Tributo regionale {codice}")


def get_descrizione_tributo_locale(codice: str) -> str:
    """Descrizione codici tributo locali."""
    descrizioni = {
        "1671": "Addizionale comunale IRPEF - sostituto d'imposta",
        "3914": "IMU - terreni",
        "3916": "IMU - aree fabbricabili",
        "3917": "IMU - quota Stato",
        "3918": "IMU - altri fabbricati",
        "3919": "IMU - interessi",
    }
    return descrizioni.get(codice, f"Tributo locale {codice}")


def process_multiple_f24(pdf_paths: List[str]) -> List[Dict[str, Any]]:
    """Processa multiple quietanze F24."""
    results = []
    for path in pdf_paths:
        try:
            result = parse_quietanza_f24(path)
            result["file_path"] = path
            result["file_name"] = os.path.basename(path)
            results.append(result)
        except Exception as e:
            results.append({
                "file_path": path,
                "file_name": os.path.basename(path),
                "error": str(e)
            })
    return results


def generate_f24_summary(parsed_data: Dict[str, Any]) -> str:
    """Genera un riepilogo testuale della quietanza F24."""
    dg = parsed_data.get("dati_generali", {})
    totali = parsed_data.get("totali", {})
    
    summary = []
    summary.append(f"QUIETANZA F24 - {dg.get('ragione_sociale', 'N/A')}")
    summary.append(f"Codice Fiscale: {dg.get('codice_fiscale', 'N/A')}")
    summary.append(f"Data Pagamento: {dg.get('data_pagamento', 'N/A')}")
    summary.append(f"Protocollo: {dg.get('protocollo_telematico', 'N/A')}")
    summary.append("")
    summary.append(f"TOTALE PAGATO: € {totali.get('saldo_delega', 0):,.2f}")
    summary.append(f"  - Debiti: € {totali.get('totale_debito', 0):,.2f}")
    summary.append(f"  - Crediti: € {totali.get('totale_credito', 0):,.2f}")
    summary.append("")
    
    # Sezione Erario
    if parsed_data.get("sezione_erario"):
        summary.append("SEZIONE ERARIO:")
        for item in parsed_data["sezione_erario"]:
            summary.append(f"  {item['codice_tributo']} - {item['descrizione']}: € {item['importo_debito']:,.2f}")
    
    # Sezione INPS
    if parsed_data.get("sezione_inps"):
        summary.append("SEZIONE INPS:")
        for item in parsed_data["sezione_inps"]:
            summary.append(f"  {item['causale']} ({item['matricola']}): € {item['importo_debito']:,.2f}")
    
    # Sezione Regioni
    if parsed_data.get("sezione_regioni"):
        summary.append("SEZIONE REGIONI:")
        for item in parsed_data["sezione_regioni"]:
            summary.append(f"  {item['codice_tributo']} - {item['descrizione']}: € {item['importo_debito']:,.2f}")
    
    # Sezione Tributi Locali
    if parsed_data.get("sezione_tributi_locali"):
        summary.append("SEZIONE TRIBUTI LOCALI:")
        for item in parsed_data["sezione_tributi_locali"]:
            summary.append(f"  {item['codice_tributo']} - {item['descrizione']}: € {item['importo_debito']:,.2f}")
    
    return "\n".join(summary)
