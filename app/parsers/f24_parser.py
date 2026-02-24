"""
F24 PDF Parser - Extract tax payment data from F24 PDF forms
"""
import re
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_f24_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parse F24 PDF and extract payment data.
    
    Returns:
        Dict with: scadenza, codice_fiscale, contribuente, tributi (list), totale
    """
    import pdfplumber
    import io
    
    result = {
        "scadenza": None,
        "codice_fiscale": None,
        "contribuente": None,
        "banca": None,
        "tributi_erario": [],
        "tributi_inps": [],
        "tributi_regioni": [],
        "tributi_imu": [],
        "tributi_inail": [],
        "totale_debito": 0,
        "totale_credito": 0,
        "saldo_finale": 0,
        "raw_text": ""
    }
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                result["raw_text"] += text + "\n"
                
                # Extract scadenza (data pagamento)
                scadenza_match = re.search(r'Scadenza\s+(\d{2}/\d{2}/\d{4})', text)
                if scadenza_match:
                    result["scadenza"] = scadenza_match.group(1)
                else:
                    # Try alternative format from bottom
                    date_match = re.search(r'(\d{2})\s*(\d{2})\s*(\d{4})\s*$', text, re.MULTILINE)
                    if date_match:
                        result["scadenza"] = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
                
                # Extract codice fiscale
                cf_match = re.search(r'CODICE FISCALE\s*([0-9]{11}|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
                if cf_match:
                    result["codice_fiscale"] = cf_match.group(1)
                else:
                    # Try extracting from structured section
                    cf_match2 = re.search(r'(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)\s*barrare', text)
                    if cf_match2:
                        result["codice_fiscale"] = ''.join(cf_match2.groups())
                
                # Extract contribuente (ragione sociale)
                contrib_match = re.search(r'denominazione o ragione sociale\s+nome\s+.*?DATI ANAGRAFICI\s+([A-Z0-9\s\.]+?)(?:\s+data di nascita|$)', text, re.DOTALL)
                if contrib_match:
                    result["contribuente"] = contrib_match.group(1).strip()
                else:
                    # Try to find company name
                    company_match = re.search(r'CERALDI GROUP\s+S\.R\.L\.|[A-Z]+\s+[A-Z]+\s+S\.R\.L\.', text)
                    if company_match:
                        result["contribuente"] = company_match.group(0)
                
                # Extract banca
                banca_match = re.search(r'(BANCO\s+BPM|UNICREDIT|INTESA\s+SANPAOLO|BNL|BPER|MPS)[^\n]*', text, re.IGNORECASE)
                if banca_match:
                    result["banca"] = banca_match.group(0).strip()
                
                # Extract ERARIO tributes - MIGLIORATO
                # Supporta tutti i codici: 1xxx, 2xxx, 6xxx (IVA)
                # Pattern più flessibile per diversi formati F24
                
                # Pattern 1: codice_tributo rateazione/regione mese/anno importo_debito importo_credito
                erario_patterns = [
                    # Pattern standard: 1001 0101 2022 48,00
                    r'([1-6]\d{3})\s+(\d{4})\s+(\d{4})\s+([\d.,]+)\s*([\d.,]*)',
                    # Pattern con spazi: 1 0 0 1  0 1 0 1  2 0 2 2  4 8 , 0 0
                    r'([1-6])\s*(\d)\s*(\d)\s*(\d)\s+(\d)\s*(\d)\s*(\d)\s*(\d)\s+(\d)\s*(\d)\s*(\d)\s*(\d)\s+([\d\s.,]+)',
                    # Pattern con mese/anno separati: 2501 12 2022 48,00
                    r'([1-6]\d{3})\s+(\d{1,2})\s+(\d{4})\s+([\d.,]+)',
                ]
                
                seen_tributi = set()
                
                for pattern in erario_patterns:
                    matches = re.findall(pattern, text)
                    for match in matches:
                        if len(match) >= 4:
                            if len(match[0]) == 1:
                                # Pattern con cifre separate
                                codice = ''.join(match[:4])
                                mese_rif = ''.join(match[4:8])
                                anno = ''.join(match[8:12])
                                debito = match[12].replace(' ', '') if len(match) > 12 else '0'
                                credito = '0'
                            elif len(match) == 4:
                                codice, mese_rif, anno, debito = match
                                credito = '0'
                            else:
                                codice, mese_rif, anno, debito, credito = match[:5]
                            
                            # Evita duplicati
                            key = f"{codice}_{mese_rif}_{anno}"
                            if key in seen_tributi:
                                continue
                            seen_tributi.add(key)
                            
                            tributo = {
                                "codice": codice,
                                "mese_riferimento": mese_rif,
                                "anno": anno,
                                "debito": parse_amount(debito),
                                "credito": parse_amount(credito) if credito else 0,
                                "tipo": get_tributo_name(codice)
                            }
                            if tributo["debito"] > 0 or tributo["credito"] > 0:
                                result["tributi_erario"].append(tributo)
                
                # Extract INPS contributions (5100, DM10, etc.)
                # Pattern: sede codice causale matricola periodo importo
                inps_pattern = re.findall(r'(5100|DM10|CXX)\s+(?:([A-Z0-9]+)\s+)?(?:(\d+NAPOLI|\d+[A-Z]+)\s+)?(\d{2})\s+(\d{4})\s+([\d,.]+)', text)
                for match in inps_pattern:
                    causale, matricola, sede, mese, anno, debito = match
                    tributo = {
                        "codice": causale,
                        "causale": causale,
                        "matricola": matricola or "",
                        "sede": sede or "",
                        "mese": mese,
                        "anno": anno,
                        "debito": parse_amount(debito),
                        "credito": 0
                    }
                    if tributo["debito"] > 0:
                        result["tributi_inps"].append(tributo)
                
                # Extract Regioni tributes (3802, etc.)
                regioni_pattern = re.findall(r'(3\d{3})\s+(\d{4})\s+(\d{4})\s+([\d,.]+)', text)
                for match in regioni_pattern:
                    codice, mese_rif, anno, debito = match
                    tributo = {
                        "codice": codice,
                        "mese_riferimento": mese_rif,
                        "anno": anno,
                        "debito": parse_amount(debito),
                        "credito": 0
                    }
                    if tributo["debito"] > 0:
                        result["tributi_regioni"].append(tributo)
                
                # Extract IMU tributes (3847, 3848, etc.)
                imu_pattern = re.findall(r'([BF]\s*\d+\s*\d*)\s+(3\d{3})\s+(\d{4})\s+(\d{4})\s+([\d,.]+)', text)
                for match in imu_pattern:
                    comune, codice, mese_rif, anno, debito = match
                    tributo = {
                        "codice_comune": comune.replace(" ", ""),
                        "codice": codice,
                        "mese_riferimento": mese_rif,
                        "anno": anno,
                        "debito": parse_amount(debito),
                        "credito": 0
                    }
                    if tributo["debito"] > 0:
                        result["tributi_imu"].append(tributo)
                
                # Extract saldo finale
                saldo_match = re.search(r'SALDO\s+FINALE\s*EURO\s*\+?\s*([\d,.]+)', text)
                if saldo_match:
                    result["saldo_finale"] = parse_amount(saldo_match.group(1))
                else:
                    # Try to find just the final amount near FIRMA
                    final_match = re.search(r'([\d,.]+)\s*\n.*FIRMA', text)
                    if final_match:
                        result["saldo_finale"] = parse_amount(final_match.group(1))
        
        # Calculate totals
        result["totale_debito"] = (
            sum(t["debito"] for t in result["tributi_erario"]) +
            sum(t["debito"] for t in result["tributi_inps"]) +
            sum(t["debito"] for t in result["tributi_regioni"]) +
            sum(t["debito"] for t in result["tributi_imu"])
        )
        result["totale_credito"] = sum(t["credito"] for t in result["tributi_erario"])
        
        if result["saldo_finale"] == 0:
            result["saldo_finale"] = result["totale_debito"] - result["totale_credito"]
        
    except Exception as e:
        logger.error(f"Error parsing F24 PDF: {e}")
        result["error"] = str(e)
    
    return result


def parse_amount(amount_str: str) -> float:
    """Parse Italian number format to float."""
    if not amount_str:
        return 0.0
    try:
        # Remove spaces and handle Italian format (1.234,56 or 1.234, 56)
        clean = amount_str.strip().replace(" ", "")
        clean = clean.replace(".", "").replace(",", ".")
        return float(clean)
    except:
        return 0.0


def get_tributo_name(codice: str) -> str:
    """Get tributo description from code."""
    codici = {
        # Ritenute lavoro dipendente e autonomo (1xxx)
        "1001": "Ritenute su redditi di lavoro dipendente",
        "1002": "Ritenute su redditi assimilati a lavoro dipendente",
        "1012": "Ritenute su indennità per cessazione rapporto lavoro",
        "1040": "Ritenute su redditi di lavoro autonomo",
        "1053": "Ritenute su dividendi",
        "1100": "Imposta sostitutiva su plusvalenze",
        
        # Addizionali IRPEF (17xx)
        "1701": "Addizionale regionale IRPEF",
        "1704": "Addizionale comunale IRPEF - Acconto",
        "1705": "Addizionale comunale IRPEF - Saldo",
        "1712": "Acconto IRPEF su trattamento fine rapporto",
        "1713": "Saldo IRPEF su trattamento fine rapporto",
        "1714": "IRPEF su rivalutazione TFR",
        
        # IRES (2xxx)
        "2001": "IRES - Acconto prima rata",
        "2002": "IRES - Acconto seconda rata",
        "2003": "IRES - Saldo",
        "2004": "Addizionale IRES",
        
        # Imposte sostitutive TFR (25xx) - IMPORTANTE
        "2501": "Imposta sostitutiva rivalutazione TFR 17% - Acconto",
        "2502": "Imposta sostitutiva rivalutazione TFR 17% - Saldo",
        "2503": "Imposta sostitutiva TFR a forme pensionistiche",
        
        # Addizionali regionali e comunali (3xxx)
        "3801": "Addizionale regionale IRPEF",
        "3802": "Addizionale comunale IRPEF - Autotassazione",
        "3843": "Addizionale comunale IRPEF - Acconto",
        "3844": "Addizionale comunale IRPEF - Saldo",
        "3847": "IMU - Immobili gruppo D - Stato",
        "3848": "IMU - Immobili gruppo D - Incremento comune",
        "3850": "Diritto camerale",
        "3852": "Sanzioni diritto camerale",
        
        # IVA (6xxx)
        "6001": "IVA - Versamento mensile gennaio",
        "6002": "IVA - Versamento mensile febbraio",
        "6003": "IVA - Versamento mensile marzo",
        "6004": "IVA - Versamento mensile aprile",
        "6005": "IVA - Versamento mensile maggio",
        "6006": "IVA - Versamento mensile giugno",
        "6007": "IVA - Versamento mensile luglio",
        "6008": "IVA - Versamento mensile agosto",
        "6009": "IVA - Versamento mensile settembre",
        "6010": "IVA - Versamento mensile ottobre",
        "6011": "IVA - Versamento mensile novembre",
        "6012": "IVA - Versamento mensile dicembre",
        "6013": "IVA - Versamento acconto",
        "6031": "IVA - Versamento trimestrale I",
        "6032": "IVA - Versamento trimestrale II",
        "6033": "IVA - Versamento trimestrale III",
        "6034": "IVA - Versamento trimestrale IV",
        "6035": "IVA - Versamento trimestrale soggetti speciali",
        "6099": "IVA - Versamento annuale",
        "6494": "IVA - Credito anno precedente",
        
        # INPS (5xxx)
        "5100": "Contributi INPS",
    }
    return codici.get(codice, f"Tributo {codice}")


def extract_f24_data_for_import(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extract F24 data ready for database import.
    
    Returns list of F24 records, one per tributo.
    """
    parsed = parse_f24_pdf(pdf_bytes)
    
    if "error" in parsed:
        return [{"error": parsed["error"]}]
    
    records = []
    base_data = {
        "scadenza": parsed["scadenza"],
        "codice_fiscale": parsed["codice_fiscale"],
        "contribuente": parsed["contribuente"],
        "banca": parsed["banca"],
        "saldo_finale": parsed["saldo_finale"]
    }
    
    # Convert scadenza to ISO format
    if parsed["scadenza"]:
        try:
            dt = datetime.strptime(parsed["scadenza"], "%d/%m/%Y")
            base_data["data_scadenza"] = dt.strftime("%Y-%m-%d")
        except:
            base_data["data_scadenza"] = None
    
    # Add ERARIO tributes
    for t in parsed["tributi_erario"]:
        record = {**base_data, **t, "sezione": "ERARIO"}
        records.append(record)
    
    # Add INPS tributes
    for t in parsed["tributi_inps"]:
        record = {**base_data, **t, "sezione": "INPS"}
        records.append(record)
    
    # Add REGIONI tributes
    for t in parsed["tributi_regioni"]:
        record = {**base_data, **t, "sezione": "REGIONI"}
        records.append(record)
    
    # Add IMU tributes
    for t in parsed["tributi_imu"]:
        record = {**base_data, **t, "sezione": "IMU"}
        records.append(record)
    
    return records
