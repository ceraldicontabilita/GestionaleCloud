"""
Parser per estratti conto PayPal (MSR - Monthly Statement Report e CSR - Combined Statement Report).
Estrae transazioni, riepilogo attività e saldo da file PDF PayPal.
"""
import pdfplumber
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import os

logger = logging.getLogger(__name__)


def parse_italian_amount(text: str) -> float:
    """Converte importo italiano (es: -1.098,11) in float."""
    if not text:
        return 0.0
    text = text.strip()
    # Rimuovi punti separatori migliaia, converti virgola in punto
    text = text.replace('.', '').replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_italian_date(text: str) -> Optional[str]:
    """Converte data italiana in formato ISO."""
    if not text:
        return None
    text = text.strip()
    # Format: 12/1/2025 o 02/12/25
    for fmt in ['%d/%m/%Y', '%d/%m/%y']:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def extract_period_from_header(text: str) -> Dict[str, str]:
    """Estrae il periodo dal header del PDF."""
    result = {'periodo_inizio': None, 'periodo_fine': None, 'mese': None, 'anno': None}
    
    # Pattern: 1/1/2025 - 31/1/2025 o 01/12/25 - 31/12/25
    date_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})'
    match = re.search(date_pattern, text)
    if match:
        result['periodo_inizio'] = parse_italian_date(match.group(1))
        result['periodo_fine'] = parse_italian_date(match.group(2))
        if result['periodo_inizio']:
            dt = datetime.strptime(result['periodo_inizio'], '%Y-%m-%d')
            result['mese'] = dt.month
            result['anno'] = dt.year
    
    return result


def extract_account_info(text: str) -> Dict[str, str]:
    """Estrae informazioni account PayPal."""
    info = {'codice_conto': None, 'email_paypal': None}
    
    match = re.search(r'Codice conto commerciante:\s*(\S+)', text)
    if match:
        info['codice_conto'] = match.group(1)
    
    match = re.search(r'ID PayPal:\s*(\S+)', text)
    if match:
        info['email_paypal'] = match.group(1)
    
    return info


def extract_activity_summary(text: str) -> Dict[str, float]:
    """Estrae il riepilogo attività dalla pagina 2."""
    summary = {
        'saldo_iniziale': 0.0,
        'pagamenti_ricevuti': 0.0,
        'pagamenti_inviati': 0.0,
        'trasferimenti_addebiti': 0.0,
        'depositi_accrediti': 0.0,
        'tariffe': 0.0,
        'saldo_finale': 0.0,
        'trasferimenti': 0.0,
    }
    
    patterns = {
        'saldo_iniziale': r'Saldo disponibile iniziale\s+(-?[\d.,]+)',
        'pagamenti_ricevuti': r'Pagamenti ricevuti\s+(-?[\d.,]+)',
        'pagamenti_inviati': r'Pagamenti inviati\s+(-?[\d.,]+)',
        'trasferimenti_addebiti': r'Trasferimenti e addebiti\s+(-?[\d.,]+)',
        'depositi_accrediti': r'Depositi e accrediti\s+(-?[\d.,]+)',
        'tariffe': r'Tariffe\s+(-?[\d.,]+)',
        'saldo_finale': r'Saldo disponibile finale\s+(-?[\d.,]+)',
        'trasferimenti': r'Trasferimenti\s+(-?[\d.,]+)',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            summary[key] = parse_italian_amount(match.group(1))
    
    return summary


def extract_transactions_from_table(table_data: List[List[str]]) -> List[Dict[str, Any]]:
    """Estrae transazioni dalla tabella cronologia."""
    transactions = []
    
    if not table_data or len(table_data) < 2:
        return transactions
    
    # Skip header row
    for row in table_data[1:]:
        if not row or len(row) < 4:
            continue
        
        data_str = row[0] if row[0] else ''
        descrizione_raw = row[1] if len(row) > 1 and row[1] else ''
        nome_email_raw = row[2] if len(row) > 2 and row[2] else ''
        lordo_str = row[3] if len(row) > 3 and row[3] else '0'
        tariffa_str = row[4] if len(row) > 4 and row[4] else '0'
        netto_str = row[5] if len(row) > 5 and row[5] else '0'
        
        data = parse_italian_date(data_str)
        if not data:
            continue
        
        # Parse descrizione e ID transazione
        descrizione = ''
        transaction_id = ''
        if descrizione_raw:
            lines = descrizione_raw.split('\n')
            descrizione = lines[0].strip()
            for line in lines:
                id_match = re.search(r'ID:\s*(\S+)', line)
                if id_match:
                    transaction_id = id_match.group(1)
        
        # Parse nome e email
        nome = ''
        email = ''
        if nome_email_raw:
            parts = nome_email_raw.split('\n')
            nome = parts[0].strip() if parts else ''
            for part in parts:
                if '@' in part:
                    email = part.strip()
        
        lordo = parse_italian_amount(lordo_str)
        tariffa = parse_italian_amount(tariffa_str)
        netto = parse_italian_amount(netto_str)
        
        # Determina tipo transazione
        tipo = 'altro'
        if 'Pagamento' in descrizione and lordo < 0:
            if 'Express Checkout' in descrizione:
                tipo = 'express_checkout'
            elif 'preautorizzato' in descrizione or 'utenza' in descrizione:
                tipo = 'pagamento_utenza'
            elif 'sito web' in descrizione:
                tipo = 'pagamento_web'
            else:
                tipo = 'pagamento'
        elif 'Versamento' in descrizione or 'Accredito' in descrizione:
            tipo = 'accredito'
        elif 'Bonifico bancario' in descrizione:
            tipo = 'bonifico_paypal'
        elif 'Rimborso' in descrizione:
            tipo = 'rimborso'
        elif 'Conversione' in descrizione:
            tipo = 'conversione_valuta'
        elif 'Prelievo' in descrizione:
            tipo = 'prelievo'
        
        tx = {
            'data': data,
            'descrizione': descrizione,
            'transaction_id': transaction_id,
            'nome_controparte': nome,
            'email_controparte': email,
            'lordo': lordo,
            'tariffa': tariffa,
            'netto': netto,
            'tipo': tipo,
            'valuta': 'EUR',
        }
        transactions.append(tx)
    
    return transactions


def extract_transactions_from_text(text: str) -> List[Dict[str, Any]]:
    """Fallback: estrae transazioni dal testo quando le tabelle non funzionano bene."""
    transactions = []
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Cerca pattern: descrizione seguita da data + importi
        date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+?)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)$', line)
        if date_match:
            data = parse_italian_date(date_match.group(1))
            rest = date_match.group(2)
            lordo = parse_italian_amount(date_match.group(3))
            tariffa = parse_italian_amount(date_match.group(4))
            netto = parse_italian_amount(date_match.group(5))
            
            if data:
                # Look back for description
                descrizione = ''
                nome = ''
                email = ''
                transaction_id = ''
                
                if i > 0:
                    prev_line = lines[i-1].strip()
                    if not re.match(r'^\d{1,2}/', prev_line) and prev_line and 'Pagina' not in prev_line:
                        descrizione = prev_line
                
                # Look forward for ID and email
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    id_match = re.search(r'ID:\s*(\S+)', next_line)
                    if id_match:
                        transaction_id = id_match.group(1)
                    email_match = re.search(r'(\S+@\S+)', next_line)
                    if email_match:
                        email = email_match.group(1)
                
                nome = rest.strip() if rest.strip() else ''
                
                tipo = 'altro'
                full_desc = f"{descrizione} {nome}".lower()
                if 'pagamento' in full_desc and lordo < 0:
                    if 'express checkout' in full_desc:
                        tipo = 'express_checkout'
                    elif 'utenza' in full_desc:
                        tipo = 'pagamento_utenza'
                    else:
                        tipo = 'pagamento'
                elif 'versamento' in full_desc or 'accredito' in full_desc:
                    tipo = 'accredito'
                elif 'bonifico' in full_desc:
                    tipo = 'bonifico_paypal'
                elif 'rimborso' in full_desc:
                    tipo = 'rimborso'
                elif 'conversione' in full_desc:
                    tipo = 'conversione_valuta'
                
                tx = {
                    'data': data,
                    'descrizione': descrizione or nome,
                    'transaction_id': transaction_id,
                    'nome_controparte': nome,
                    'email_controparte': email,
                    'lordo': lordo,
                    'tariffa': tariffa,
                    'netto': netto,
                    'tipo': tipo,
                    'valuta': 'EUR',
                }
                transactions.append(tx)
        
        i += 1
    
    return transactions


def parse_paypal_msr(file_path: str) -> Dict[str, Any]:
    """
    Parser principale per PDF PayPal MSR/CSR.
    
    Returns:
        Dict con: account_info, periodo, riepilogo, transazioni, metadata
    """
    result = {
        'success': False,
        'tipo_documento': 'MSR',
        'account_info': {},
        'periodo': {},
        'riepilogo_attivita': {},
        'transazioni': [],
        'totale_transazioni': 0,
        'file_path': file_path,
        'file_name': os.path.basename(file_path),
        'errors': []
    }
    
    try:
        with pdfplumber.open(file_path) as pdf:
            result['pagine_totali'] = len(pdf.pages)
            
            all_text = ''
            all_transactions = []
            
            for page_idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                all_text += text + '\n'
                
                # Page 1: Header e info account
                if page_idx == 0:
                    result['account_info'] = extract_account_info(text)
                    result['periodo'] = extract_period_from_header(text)
                    
                    # Determina tipo (MSR vs CSR)
                    fname = os.path.basename(file_path).upper()
                    if 'CSR' in fname or 'Combined' in text:
                        result['tipo_documento'] = 'CSR'
                
                # Page 2: Riepilogo attività
                if 'Riepilogo attività' in text:
                    result['riepilogo_attivita'] = extract_activity_summary(text)
                
                # Pages with transaction history
                if 'Cronologia transazioni' in text:
                    tables = page.extract_tables()
                    for table in tables:
                        if table and len(table) > 1:
                            header = table[0]
                            if header and any('Data' in str(h) for h in header if h):
                                txs = extract_transactions_from_table(table)
                                all_transactions.extend(txs)
                    
                    # If table extraction got fewer results, try text-based
                    if not all_transactions:
                        txs = extract_transactions_from_text(text)
                        all_transactions.extend(txs)
            
            # Deduplica per transaction_id
            seen_ids = set()
            unique_transactions = []
            for tx in all_transactions:
                tid = tx.get('transaction_id', '')
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                unique_transactions.append(tx)
            
            result['transazioni'] = unique_transactions
            result['totale_transazioni'] = len(unique_transactions)
            result['success'] = True
            
            logger.info(f"Parsed {file_path}: {len(unique_transactions)} transazioni estratte")
            
    except Exception as e:
        result['errors'].append(str(e))
        logger.error(f"Errore parsing {file_path}: {e}")
    
    return result


def parse_multiple_pdfs(file_paths: List[str]) -> Dict[str, Any]:
    """Parsa più file PDF PayPal."""
    results = {
        'totale_files': len(file_paths),
        'files_ok': 0,
        'files_errore': 0,
        'totale_transazioni': 0,
        'statements': [],
        'errors': []
    }
    
    for fp in file_paths:
        parsed = parse_paypal_msr(fp)
        if parsed['success']:
            results['files_ok'] += 1
            results['totale_transazioni'] += parsed['totale_transazioni']
        else:
            results['files_errore'] += 1
            results['errors'].extend(parsed['errors'])
        results['statements'].append(parsed)
    
    return results
