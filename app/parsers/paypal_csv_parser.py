"""
Parser per l'estratto conto PayPal esportato in CSV (export massivo, più
mesi in un unico file), alternativo ai PDF MSR/CSR già gestiti da
paypal_msr_parser.py.

Produce lo STESSO schema di parse_paypal_msr() (vedi quel modulo) così può
riusare _save_parsed_statement()/_auto_riconcilia() in paypal_statements.py
senza duplicare la logica di persistenza/riconciliazione — cambia solo la
fonte del dato.

Il CSV osservato ha due layout di colonne che convivono nello stesso file
(export PayPal in inglese fino a metà 2024, poi in italiano da metà 2024 in
poi): "date/description/name \\ email/gross/fee/net" oppure
"data/descrizione/nome \\ email/lordo/tariffa/netto". Ogni riga valorizza
solo una delle due coppie: si usa quella non vuota.
"""
import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def _parse_amount(text: Optional[str]) -> float:
    if not text:
        return 0.0
    text = text.strip()
    if not text:
        return 0.0
    if ',' in text and '.' not in text:
        # Formato italiano: punto migliaia, virgola decimale (es. "-1.234,56")
        text = text.replace('.', '').replace(',', '.')
    else:
        text = text.replace(',', '')
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _split_lines(raw: Optional[str]) -> List[str]:
    return [p.strip() for p in (raw or '').split('\n') if p.strip()]


def _classifica_tipo(descrizione: str, lordo: float) -> str:
    """Stessa tassonomia di tipo usata da paypal_msr_parser.py, estesa per
    riconoscere anche le descrizioni in inglese presenti nel CSV."""
    d = descrizione.lower()
    if any(k in d for k in ('rimborso', 'refund')):
        return 'rimborso'
    if any(k in d for k in ('conversione', 'conversion')):
        return 'conversione_valuta'
    if any(k in d for k in ('bonifico bancario', 'bank transfer')):
        return 'bonifico_paypal'
    if any(k in d for k in ('prelievo', 'withdraw')):
        return 'prelievo'
    if any(k in d for k in ('versamento', 'general card deposit', 'deposit', 'accredito')):
        return 'accredito'
    if lordo < 0 and any(k in d for k in ('pagamento', 'payment')):
        if 'express checkout' in d:
            return 'express_checkout'
        if any(k in d for k in ('preautorizzat', 'utenza', 'preapproved', 'bill user')):
            return 'pagamento_utenza'
        if any(k in d for k in ('sito web', 'website')):
            return 'pagamento_web'
        return 'pagamento'
    if lordo > 0:
        return 'accredito'
    return 'altro'


def _parse_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    usa_colonne_italiane = bool((row.get('data') or '').strip())
    if usa_colonne_italiane:
        data_raw = row.get('data')
        descrizione_raw = row.get('descrizione')
        nome_email_raw = row.get('nome \\ email')
        lordo_raw = row.get('lordo')
        tariffa_raw = row.get('tariffa')
        netto_raw = row.get('netto')
    else:
        data_raw = row.get('date')
        descrizione_raw = row.get('description')
        nome_email_raw = row.get('name \\ email')
        lordo_raw = row.get('gross')
        tariffa_raw = row.get('fee')
        netto_raw = row.get('net')

    data = _parse_date(data_raw)
    if not data:
        return None

    desc_lines = _split_lines(descrizione_raw)
    descrizione = desc_lines[0] if desc_lines else ''
    transaction_id = ''
    for line in desc_lines:
        m = re.search(r'ID:\s*(\S+)', line)
        if m:
            transaction_id = m.group(1)
            break

    nome = ''
    email = ''
    for part in _split_lines(nome_email_raw):
        if '@' in part:
            email = part
        elif not nome:
            nome = part

    lordo = _parse_amount(lordo_raw)

    return {
        'data': data,
        'descrizione': descrizione,
        'transaction_id': transaction_id,
        'nome_controparte': nome,
        'email_controparte': email,
        'lordo': lordo,
        'tariffa': _parse_amount(tariffa_raw),
        'netto': _parse_amount(netto_raw),
        'tipo': _classifica_tipo(descrizione, lordo),
        'valuta': (row.get('currency') or 'EUR').strip() or 'EUR',
        'status_paypal': (row.get('status') or '').strip(),
        '_file_origine': (row.get('File') or '').strip() or 'import_csv',
    }


def parse_paypal_csv(content: bytes) -> Dict[str, Any]:
    """
    Parsa un CSV di export PayPal multi-mese e restituisce una lista di
    "statement" (uno per file/periodo sorgente indicato nella colonna
    "File"), ciascuno nello stesso formato prodotto da parse_paypal_msr(),
    pronto per _save_parsed_statement().
    """
    text = content.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))

    per_file: Dict[str, List[Dict[str, Any]]] = {}
    righe_totali = 0
    righe_scartate = 0
    for row in reader:
        righe_totali += 1
        tx = _parse_row(row)
        if not tx:
            righe_scartate += 1
            continue
        file_origine = tx.pop('_file_origine')
        per_file.setdefault(file_origine, []).append(tx)

    statements = []
    for file_name, transazioni in per_file.items():
        transazioni.sort(key=lambda t: t['data'])
        date_valide = [t['data'] for t in transazioni]
        periodo_inizio = date_valide[0] if date_valide else None
        periodo_fine = date_valide[-1] if date_valide else None

        statements.append({
            'success': True,
            'tipo_documento': 'CSV',
            'account_info': {},
            'periodo': {
                'periodo_inizio': periodo_inizio,
                'periodo_fine': periodo_fine,
                'mese': int(periodo_inizio[5:7]) if periodo_inizio else None,
                'anno': int(periodo_inizio[:4]) if periodo_inizio else None,
            },
            'riepilogo_attivita': {},
            'transazioni': transazioni,
            'totale_transazioni': len(transazioni),
            'file_name': file_name,
            'errors': [],
        })

    return {
        'success': True,
        'statements': statements,
        'righe_totali': righe_totali,
        'righe_scartate': righe_scartate,
    }
