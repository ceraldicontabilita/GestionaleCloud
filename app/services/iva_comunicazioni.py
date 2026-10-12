"""Email IVA: informazione riferita al mese, mai quietanza o saldo presunto."""
import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime, parseaddr
from urllib.parse import quote

MESI = {n: i+1 for i, n in enumerate(('gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre'))}


def periodo_da_testo(subject, body, data_email):
    text = (subject+'\n'+body).lower()
    candidates = set()
    prefix = r'\b(?:iva|liquidazione(?:\s+iva)?)\s*(?:di\s+|del\s+mese\s+di\s+|del\s+|mese\s+)?'
    for m in re.finditer(prefix+r'(0?[1-9]|1[0-2])[./_-](20\d{2})\b', text):
        candidates.add(f'{int(m[2]):04d}-{int(m[1]):02d}')
    for m in re.finditer(prefix+r'('+ '|'.join(MESI) +r')(?:\s+(20\d{2}))?\b', text):
        month = MESI[m[1]]
        year = int(m[2]) if m[2] else data_email.year - int(month > data_email.month)
        candidates.add(f'{year:04d}-{month:02d}')
    return next(iter(candidates)) if len(candidates) == 1 else None


async def registra_comunicazione(db, *, subject, body, sender, date_str, message_id, account):
    text = (subject+'\n'+body).lower()
    if not message_id or not (re.search(r'\biva(?=\b|\d)', text) and 'credit' in text and 'debit' in text and
            re.search(r'\bcompens(?:ata|ato|ate|iamo|ano)\b', text)):
        return None
    if re.search(r'\bnon\s+(?:viene\s+)?compens', text):
        return None
    address = parseaddr(sender)[1].lower()
    from app.services.mittenti import _addr
    allowed = await db['mittenti_email'].find({'attivo': True, 'tipo_documento': {'$in': ['f24', 'commercialista', 'iva']}}).to_list(500)
    if not any(_addr(r).lower() == address for r in allowed):
        return None
    try:
        sent = parsedate_to_datetime(date_str)
    except (TypeError, ValueError, IndexError):
        return None
    periodo = periodo_da_testo(subject, body, sent)
    if not periodo:
        return None
    # Legge soltanto un importo esplicitamente attribuito al debito, con valuta.
    values = re.findall(r'\bdebito\s*(?:di|:)?\s*([\d.]+(?:,\d{1,2})?)\s*(?:€|euro)', text)
    amount = None
    if len(values)==1:
        raw=values[0]
        if ',' in raw: raw=raw.replace('.','').replace(',','.')
        elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+',raw): raw=raw.replace('.','')
        amount=int(Decimal(raw)*100)
    ident = 'email:'+hashlib.sha256((account+'|'+message_id).encode()).hexdigest()
    row = {'id': ident, 'periodo': periodo, 'source_message_id': message_id,
           'source_account': account, 'mittente': address, 'oggetto': subject, 'testo': body,
           'data_email': date_str, 'data_email_iso': sent.isoformat(),
           'source_sha256': hashlib.sha256(body.encode()).hexdigest(),
           'source_url': 'https://mail.google.com/mail/u/?authuser='+quote(account,safe='')+'#search/rfc822msgid:'+quote(message_id.strip('<>'),safe=''),
           'compensazione_comunicata': True, 'verificato': True,
           'debito_mese_cents': amount, 'credito_residuo_cents': None}
    await db['iva_comunicazioni'].update_one({'id': ident}, {'$set': row}, upsert=True)
    return {'id': ident, 'periodo': periodo}
