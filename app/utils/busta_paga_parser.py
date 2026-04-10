"""
Parser per estrarre dati dalle buste paga PDF.
Supporta 3 formati:
- 2017-2021: Formato CSC/Zucchetti vecchio
- 2022: Formato Teamsystem
- 2023+: Formato Zucchetti nuovo

Estrae: Paga Base, Contingenza, TFR, Ferie, Permessi, ROL
"""
import pdfplumber
import re
import os
from datetime import datetime
from typing import Dict, List, Any

# Mapping mesi italiano -> numero
MESI_MAP = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
    'tredicesima': 12, 'quattordicesima': 7
}

def parse_italian_number(value: str) -> float:
    """Converte numero italiano (1.234,56) in float."""
    if not value:
        return 0.0
    try:
        # Rimuove spazi e caratteri non numerici eccetto . e ,
        clean = re.sub(r'[^\d.,\-]', '', str(value))
        # Gestisce il formato italiano
        if ',' in clean and '.' in clean:
            # Formato 1.234,56
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            # Formato 1234,56
            clean = clean.replace(',', '.')
        return float(clean) if clean else 0.0
    except:
        return 0.0


def detect_format(text: str) -> str:
    """Rileva il formato del PDF dalla struttura del testo."""
    if 'CodicesAzienda' in text or 'CodicesFiscale' in text:
        return 'zucchetti_2023'
    elif 'Voce/i di tariffa' in text or 'MESE RETRIBUITO' in text:
        return 'teamsystem_2022'
    elif 'BOLLO ISTITUTO' in text or 'LIBRO UNICO DEL LAVORO' in text:
        return 'csc_2017'
    else:
        return 'unknown'


def parse_format_csc_2017(text: str, lines: List[str]) -> Dict[str, Any]:
    """Parser per formato CSC 2017-2021."""
    result = {
        'format': 'csc_2017',
        'paga_base_oraria': 0.0,
        'paga_base_mensile': 0.0,
        'contingenza_oraria': 0.0,
        'contingenza_mensile': 0.0,
        'tfr_fondo': 0.0,
        'ferie_maturate': 0.0,
        'ferie_godute': 0.0,
        'ferie_saldo': 0.0,
        'permessi_maturati': 0.0,
        'permessi_goduti': 0.0,
        'permessi_saldo': 0.0,
        'rol_maturati': 0.0,
        'rol_goduti': 0.0,
        'rol_saldo': 0.0,
        'netto_mese': 0.0,
    }
    
    for i, line in enumerate(lines):
        # Paga base e contingenza
        # Formato: "1) PAGA BASE X" con X che può essere orario (4-10) o mensile (700-1500)
        if 'PAGA BASE' in line:
            match = re.search(r'PAGA BASE\s+([\d,]+)', line)
            if match:
                val = parse_italian_number(match.group(1))
                # Se il valore è > 100, è già mensile
                if val > 100:
                    result['paga_base_mensile'] = val
                else:
                    result['paga_base_oraria'] = val
        
        if 'CONTINGENZA' in line:
            match = re.search(r'CONTINGENZA\s+([\d,]+)', line)
            if match:
                val = parse_italian_number(match.group(1))
                # Se il valore è > 100, è già mensile
                if val > 100:
                    result['contingenza_mensile'] = val
                else:
                    result['contingenza_oraria'] = val
        
        # Progressivi - formato su righe separate:
        # Mat. X+Mat. Y+Mat. Z+ (Maturato)
        # God. X+God. Y+God. Z+ (Goduto)
        # Sal. X+Sal. Y+Sal. Z+ (Saldo)
        
        # Riga Mat. (maturato)
        if line.startswith('Mat.') or 'Mat.' in line[:10]:
            mat_matches = re.findall(r'Mat\.\s*([\d.,]+)\+?', line)
            if len(mat_matches) >= 1:
                result['ferie_maturate'] = parse_italian_number(mat_matches[0])
            if len(mat_matches) >= 2:
                result['permessi_maturati'] = parse_italian_number(mat_matches[1])
            if len(mat_matches) >= 3:
                result['rol_maturati'] = parse_italian_number(mat_matches[2])
        
        # Riga God. (goduto)
        if line.startswith('God.') or 'God.' in line[:10]:
            god_matches = re.findall(r'God\.\s*([\d.,]+)\+?', line)
            if len(god_matches) >= 1:
                result['ferie_godute'] = parse_italian_number(god_matches[0])
            if len(god_matches) >= 2:
                result['permessi_goduti'] = parse_italian_number(god_matches[1])
            if len(god_matches) >= 3:
                result['rol_goduti'] = parse_italian_number(god_matches[2])
        
        # Riga Sal. (saldo)
        if line.startswith('Sal.') or 'Sal.' in line[:10]:
            sal_matches = re.findall(r'Sal\.\s*([\d.,]+)\+?', line)
            if len(sal_matches) >= 1:
                result['ferie_saldo'] = parse_italian_number(sal_matches[0])
            if len(sal_matches) >= 2:
                result['permessi_saldo'] = parse_italian_number(sal_matches[1])
            if len(sal_matches) >= 3:
                result['rol_saldo'] = parse_italian_number(sal_matches[2])
        
        # TFR - cerca RETRIBUZIONE T.F.R.
        if 'T.F.R.' in line or 'T._F._R' in line:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            # Prende il numero più grande che potrebbe essere il TFR accumulato
            for num_str in numbers:
                val = parse_italian_number(num_str)
                if val > result['tfr_fondo'] and val > 100:
                    result['tfr_fondo'] = val
        
        # Netto - riga con numeri grandi alla fine
        if i >= len(lines) - 5:  # Ultime 5 righe
            # Cerca un numero che potrebbe essere il netto (tra 500 e 5000)
            numbers = re.findall(r'([\d.,]+)', line)
            for num_str in numbers:
                val = parse_italian_number(num_str)
                if 200 < val < 5000 and val > result['netto_mese']:
                    # Verifica che non sia un progressivo
                    if 'Mat.' not in line and 'God.' not in line and 'Sal.' not in line:
                        result['netto_mese'] = val
    
    # Calcola paga mensile (173.33 ore/mese standard) solo se non già calcolata
    if result.get('paga_base_oraria', 0) > 0 and result.get('paga_base_mensile', 0) == 0:
        result['paga_base_mensile'] = round(result['paga_base_oraria'] * 173.33, 2)
    if result.get('contingenza_oraria', 0) > 0 and result.get('contingenza_mensile', 0) == 0:
        result['contingenza_mensile'] = round(result['contingenza_oraria'] * 173.33, 2)
    
    return result


def parse_format_teamsystem_2022(text: str, lines: List[str]) -> Dict[str, Any]:
    """Parser per formato Teamsystem 2022."""
    result = {
        'format': 'teamsystem_2022',
        'paga_base_oraria': 0.0,
        'contingenza_oraria': 0.0,
        'tfr_fondo': 0.0,
        'ferie_maturate': 0.0,
        'ferie_godute': 0.0,
        'ferie_saldo': 0.0,
        'permessi_maturati': 0.0,
        'permessi_goduti': 0.0,
        'permessi_saldo': 0.0,
        'rol_maturati': 0.0,
        'rol_goduti': 0.0,
        'rol_saldo': 0.0,
        'netto_mese': 0.0,
    }
    
    for i, line in enumerate(lines):
        # Paga base nella riga con "PAGA BASE CONTINGEN."
        if 'PAGA BASE' in line and 'CONTINGEN' in line:
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                numbers = re.findall(r'[\d]+[,.][\d]+', next_line)
                if len(numbers) >= 1:
                    result['paga_base_oraria'] = parse_italian_number(numbers[0])
                if len(numbers) >= 2:
                    result['contingenza_oraria'] = parse_italian_number(numbers[1])
        
        # Ferie - riga con FERIE A.P. FERIE MAT. etc
        if 'FERIE A.P.' in line or 'FERIE MAT' in line:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 4:
                result['ferie_maturate'] = parse_italian_number(numbers[1])
                result['ferie_godute'] = parse_italian_number(numbers[2])
                result['ferie_saldo'] = parse_italian_number(numbers[3])
        
        # Cerca Ferie nella forma "Ferie X Y Z W"
        if line.startswith('Ferie') or 'FERIE' in line[:20]:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 4:
                result['ferie_maturate'] = parse_italian_number(numbers[1])
                result['ferie_godute'] = parse_italian_number(numbers[2])
                result['ferie_saldo'] = parse_italian_number(numbers[3])
        
        # Permessi
        if 'PERM.' in line or line.startswith('Permessi'):
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 3:
                result['permessi_maturati'] = parse_italian_number(numbers[0])
                result['permessi_goduti'] = parse_italian_number(numbers[1])
                if len(numbers) >= 4:
                    result['permessi_saldo'] = parse_italian_number(numbers[3])
        
        # ROL
        if 'ROL' in line[:20]:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 4:
                result['rol_maturati'] = parse_italian_number(numbers[1])
                result['rol_goduti'] = parse_italian_number(numbers[2])
                result['rol_saldo'] = parse_italian_number(numbers[3])
        
        # TFR
        if 'T.F.R.' in line or 'TFR' in line:
            if 'F.DO' in line.upper() or 'FONDO' in line.upper():
                numbers = re.findall(r'[\d]+[,.][\d]+', line)
                if numbers:
                    result['tfr_fondo'] = parse_italian_number(numbers[0])
        
        # Netto busta
        if 'NETTO BUSTA' in line or 'NETTO DEL MESE' in line.upper():
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                amount_match = re.search(r'([\d.,]+)\s*€?', next_line)
                if amount_match:
                    result['netto_mese'] = parse_italian_number(amount_match.group(1))
    
    # Calcola paga mensile solo se non già calcolata
    if result.get('paga_base_oraria', 0) > 0 and result.get('paga_base_mensile', 0) == 0:
        result['paga_base_mensile'] = round(result['paga_base_oraria'] * 173.33, 2)
    if result.get('contingenza_oraria', 0) > 0 and result.get('contingenza_mensile', 0) == 0:
        result['contingenza_mensile'] = round(result['contingenza_oraria'] * 173.33, 2)
    
    return result


def parse_format_zucchetti_2023(text: str, lines: List[str]) -> Dict[str, Any]:
    """Parser per formato Zucchetti 2023+."""
    result = {
        'format': 'zucchetti_2023',
        'paga_base_oraria': 0.0,
        'paga_base_mensile': 0.0,
        'contingenza_oraria': 0.0,
        'contingenza_mensile': 0.0,
        'tfr_fondo': 0.0,
        'tfr_quota_anno': 0.0,
        'ferie_maturate': 0.0,
        'ferie_godute': 0.0,
        'ferie_saldo': 0.0,
        'permessi_maturati': 0.0,
        'permessi_goduti': 0.0,
        'permessi_saldo': 0.0,
        'rol_maturati': 0.0,
        'rol_goduti': 0.0,
        'rol_saldo': 0.0,
        'netto_mese': 0.0,
    }
    
    for i, line in enumerate(lines):
        # Paga base, scatti, contingenza
        if 'PAGA BASE' in line and ('SCATTI' in line or 'CONTING' in line):
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Pattern per catturare numeri come 937,80000 o 5,72826
                numbers = re.findall(r'[\d]+[,.][\d]+', next_line)
                if len(numbers) >= 1:
                    val = parse_italian_number(numbers[0])
                    # Se il valore è > 100, è già mensile
                    # Se ha molti decimali (es. 937,80000) è mensile
                    raw_num = numbers[0]
                    decimal_part = raw_num.split(',')[-1] if ',' in raw_num else raw_num.split('.')[-1]
                    if val > 100 or (len(decimal_part) >= 4 and val > 50):
                        result['paga_base_mensile'] = val
                    else:
                        result['paga_base_oraria'] = val
                
                # Se c'è SCATTI, contingenza è il terzo numero, altrimenti è il secondo
                cont_idx = 2 if 'SCATTI' in line else 1
                if len(numbers) > cont_idx:
                    val = parse_italian_number(numbers[cont_idx])
                    raw_num = numbers[cont_idx]
                    decimal_part = raw_num.split(',')[-1] if ',' in raw_num else raw_num.split('.')[-1]
                    if val > 100 or (len(decimal_part) >= 4 and val > 50):
                        result['contingenza_mensile'] = val
                    else:
                        result['contingenza_oraria'] = val
        
        # TFR
        if 'T.F.R.' in line and 'F.do' in line:
            # La riga successiva contiene i valori
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Pattern per numeri italiani come 9.914,01 o 1159,73
                numbers = re.findall(r'[\d]+(?:\.[\d]{3})*[,][\d]+|[\d]+[,][\d]+', next_line)
                if numbers:
                    # Il primo numero è il TFR Fondo
                    result['tfr_fondo'] = parse_italian_number(numbers[0])
                    if len(numbers) >= 4:
                        result['tfr_quota_anno'] = parse_italian_number(numbers[3])
        
        # Ferie
        if line.startswith('Ferie') or ('FERIE' in line[:15] and 'A.P.' not in line):
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 4:
                result['ferie_maturate'] = parse_italian_number(numbers[1])
                result['ferie_godute'] = parse_italian_number(numbers[2])
                result['ferie_saldo'] = parse_italian_number(numbers[3])
            elif len(numbers) >= 3:
                result['ferie_maturate'] = parse_italian_number(numbers[0])
                result['ferie_godute'] = parse_italian_number(numbers[1])
                result['ferie_saldo'] = parse_italian_number(numbers[2])
        
        # Permessi
        if line.startswith('Permessi') or 'PERMESSI' in line[:15]:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 3:
                result['permessi_maturati'] = parse_italian_number(numbers[0])
                result['permessi_goduti'] = parse_italian_number(numbers[1])
                result['permessi_saldo'] = parse_italian_number(numbers[2])
        
        # ROL
        if 'ROL' in line[:10]:
            numbers = re.findall(r'[\d]+[,.][\d]+', line)
            if len(numbers) >= 3:
                result['rol_maturati'] = parse_italian_number(numbers[0])
                result['rol_goduti'] = parse_italian_number(numbers[1])
                result['rol_saldo'] = parse_italian_number(numbers[2])
        
        # Netto del mese
        if 'NETTO' in line.upper() and 'MESE' in line.upper():
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                amount_match = re.search(r'([\d.,]+)\s*€?', next_line)
                if amount_match:
                    result['netto_mese'] = parse_italian_number(amount_match.group(1))
    
    # Calcola paga mensile solo se non già calcolata
    if result.get('paga_base_oraria', 0) > 0 and result.get('paga_base_mensile', 0) == 0:
        result['paga_base_mensile'] = round(result['paga_base_oraria'] * 173.33, 2)
    if result.get('contingenza_oraria', 0) > 0 and result.get('contingenza_mensile', 0) == 0:
        result['contingenza_mensile'] = round(result['contingenza_oraria'] * 173.33, 2)
    
    return result


def extract_busta_paga_data(pdf_path: str) -> Dict[str, Any]:
    """
    Estrae i dati principali da una busta paga PDF.
    Rileva automaticamente il formato e usa il parser appropriato.
    """
    result = {
        'file': os.path.basename(pdf_path),
        'dipendente': None,
        'codice_fiscale': None,
        'mese': None,
        'anno': None,
        'paga_base_oraria': 0.0,
        'contingenza_oraria': 0.0,
        'paga_base_mensile': 0.0,
        'contingenza_mensile': 0.0,
        'tfr_fondo': 0.0,
        'tfr_quota_anno': 0.0,
        'ferie_residuo_ap': 0.0,
        'ferie_maturate': 0.0,
        'ferie_godute': 0.0,
        'ferie_saldo': 0.0,
        'permessi_residuo_ap': 0.0,
        'permessi_maturati': 0.0,
        'permessi_goduti': 0.0,
        'permessi_saldo': 0.0,
        'rol_residuo_ap': 0.0,
        'rol_maturati': 0.0,
        'rol_goduti': 0.0,
        'rol_saldo': 0.0,
        'netto_mese': 0.0,
        'format_detected': 'unknown',
        'parsed_at': datetime.now().isoformat()
    }
    
    try:
        # Estrae mese e anno dal nome file
        filename = os.path.basename(pdf_path).lower()
        for mese_nome, mese_num in MESI_MAP.items():
            if mese_nome in filename:
                result['mese'] = mese_num
                break
        
        year_match = re.search(r'20\d{2}', filename)
        if year_match:
            result['anno'] = int(year_match.group())
        
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            lines = full_text.split('\n')
            
            # Rileva il formato
            format_type = detect_format(full_text)
            result['format_detected'] = format_type
            
            # Estrae codice fiscale
            cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', full_text)
            if cf_match:
                result['codice_fiscale'] = cf_match.group(1)
            
            # Estrae nome dipendente
            for line in lines:
                if 'VESPA' in line or (result['codice_fiscale'] and result['codice_fiscale'] in line):
                    # Cerca nome prima del CF
                    parts = line.split()
                    for j, p in enumerate(parts):
                        if re.match(r'[A-Z]{6}\d{2}', p):
                            result['dipendente'] = ' '.join(parts[max(0,j-2):j])
                            break
                    break
            
            # Usa il parser appropriato
            if format_type == 'csc_2017':
                parsed = parse_format_csc_2017(full_text, lines)
            elif format_type == 'teamsystem_2022':
                parsed = parse_format_teamsystem_2022(full_text, lines)
            elif format_type == 'zucchetti_2023':
                parsed = parse_format_zucchetti_2023(full_text, lines)
            else:
                # Prova tutti i parser e usa quello che estrae più dati
                parsed_csc = parse_format_csc_2017(full_text, lines)
                parsed_ts = parse_format_teamsystem_2022(full_text, lines)
                parsed_zuc = parse_format_zucchetti_2023(full_text, lines)
                
                # Conta i campi non zero per ogni parser
                def count_nonzero(d):
                    return sum(1 for v in d.values() if isinstance(v, (int, float)) and v > 0)
                
                if count_nonzero(parsed_zuc) >= count_nonzero(parsed_ts) and count_nonzero(parsed_zuc) >= count_nonzero(parsed_csc):
                    parsed = parsed_zuc
                elif count_nonzero(parsed_ts) >= count_nonzero(parsed_csc):
                    parsed = parsed_ts
                else:
                    parsed = parsed_csc
            
            # Merge risultati
            for key, value in parsed.items():
                if key in result:
                    result[key] = value
                elif key == 'paga_base_mensile':
                    result['paga_base_mensile'] = value
                elif key == 'contingenza_mensile':
                    result['contingenza_mensile'] = value
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def scan_dipendente_folder(folder_path: str) -> List[Dict]:
    """
    Scansiona una cartella di un dipendente e estrae i dati da tutte le buste paga.
    Restituisce la lista ordinata per data (più recente prima).
    """
    results = []
    
    if not os.path.exists(folder_path):
        return results
    
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(folder_path, filename)
            data = extract_busta_paga_data(pdf_path)
            if data.get('anno') and data.get('mese'):
                results.append(data)
    
    # Ordina per anno e mese decrescente
    results.sort(key=lambda x: (x.get('anno', 0), x.get('mese', 0)), reverse=True)
    
    return results


def get_latest_progressivi(folder_path: str) -> Dict[str, Any]:
    """
    Ottiene i progressivi più recenti da una cartella dipendente.
    Prende preferibilmente dicembre o l'ultimo mese disponibile.
    """
    buste = scan_dipendente_folder(folder_path)
    
    if not buste:
        return {}
    
    # Cerca prima dicembre dell'anno più recente con dati validi
    for busta in buste:
        if busta.get('mese') == 12:
            # Verifica che abbia almeno alcuni dati
            if (busta.get('tfr_fondo', 0) > 0 or 
                busta.get('ferie_saldo', 0) > 0 or 
                busta.get('paga_base_mensile', 0) > 0 or
                busta.get('paga_base_oraria', 0) > 0):
                return _build_progressivi(busta)
    
    # Se non c'è dicembre con dati, prende il primo con dati validi
    for busta in buste:
        if (busta.get('tfr_fondo', 0) > 0 or 
            busta.get('ferie_saldo', 0) > 0 or 
            busta.get('paga_base_mensile', 0) > 0 or
            busta.get('paga_base_oraria', 0) > 0):
            return _build_progressivi(busta)
    
    # Altrimenti prende il più recente comunque
    return _build_progressivi(buste[0]) if buste else {}


def _build_progressivi(busta: Dict) -> Dict[str, Any]:
    """Costruisce il dizionario progressivi da una busta paga."""
    paga_base = busta.get('paga_base_mensile', 0)
    if paga_base == 0 and busta.get('paga_base_oraria', 0) > 0:
        paga_base = round(busta['paga_base_oraria'] * 173.33, 2)
    
    contingenza = busta.get('contingenza_mensile', 0)
    if contingenza == 0 and busta.get('contingenza_oraria', 0) > 0:
        contingenza = round(busta['contingenza_oraria'] * 173.33, 2)
    
    return {
        'tfr_accantonato': busta.get('tfr_fondo', 0),
        'tfr_quota_anno': busta.get('tfr_quota_anno', 0),
        'ferie_maturate': busta.get('ferie_maturate', 0),
        'ferie_godute': busta.get('ferie_godute', 0),
        'ferie_residue': busta.get('ferie_saldo', 0),
        'permessi_maturati': busta.get('permessi_maturati', 0),
        'permessi_goduti': busta.get('permessi_goduti', 0),
        'permessi_residui': busta.get('permessi_saldo', 0),
        'rol_maturati': busta.get('rol_maturati', 0),
        'rol_goduti': busta.get('rol_goduti', 0),
        'rol_residui': busta.get('rol_saldo', 0),
        'paga_base': paga_base,
        'contingenza': contingenza,
        'netto_mese': busta.get('netto_mese', 0),
        'anno_riferimento': busta.get('anno'),
        'mese_riferimento': busta.get('mese'),
        'fonte': busta.get('file'),
        'format_detected': busta.get('format_detected', 'unknown')
    }


def scan_all_dipendenti(base_path: str = "/app/documents/buste_paga") -> Dict[str, Dict]:
    """
    Scansiona tutte le cartelle dei dipendenti e restituisce un dizionario
    con i progressivi più recenti per ogni dipendente.
    """
    result = {}
    
    if not os.path.exists(base_path):
        return result
    
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        if os.path.isdir(folder_path):
            progressivi = get_latest_progressivi(folder_path)
            if progressivi:
                # Usa il nome della cartella come chiave
                nome_normalizzato = folder_name.replace('_', ' ')
                result[nome_normalizzato] = progressivi
    
    return result


if __name__ == "__main__":
    # Test
    
    test_files = [
        "/app/documents/buste_paga/Vincenzo_Vespa/Busta paga - Vespa Vincenzo - Dicembre 2017.pdf",
        "/app/documents/buste_paga/Vincenzo_Vespa/Busta paga - Vespa Vincenzo - Dicembre 2020.pdf",
        "/app/documents/buste_paga/Vincenzo_Vespa/Busta paga - Vespa Vincenzo - Tredicesima 2022.pdf",
        "/app/documents/buste_paga/Vincenzo_Vespa/Busta paga - Vespa Vincenzo - Dicembre 2024.pdf",
    ]
    
    for path in test_files:
        if os.path.exists(path):
            print(f"\n{'='*60}")
            print(f"📄 {os.path.basename(path)}")
            data = extract_busta_paga_data(path)
            print(f"Formato: {data.get('format_detected')}")
            print(f"Paga Base: €{data.get('paga_base_mensile', 0):.2f}")
            print(f"Contingenza: €{data.get('contingenza_mensile', 0):.2f}")
            print(f"TFR Fondo: €{data.get('tfr_fondo', 0):.2f}")
            print(f"Ferie: Mat={data.get('ferie_maturate', 0):.2f} God={data.get('ferie_godute', 0):.2f} Sal={data.get('ferie_saldo', 0):.2f}")
            print(f"Netto: €{data.get('netto_mese', 0):.2f}")
