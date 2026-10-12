"""Quadratura FatturaPA: componenti documentate, mai scarti inventati."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal('0.01')
VERSIONE = 'fattura_totali_sc_v1'
CAMPI_CONTROLLO = ('totali_coerenti', 'differenza_totali', 'controllo_totali',
                   'sconto_merce', 'imponibile_contabile', 'arrotondamento_documento')


def _d(v):
    n = Decimal(str(v))
    if not n.is_finite():
        raise InvalidOperation
    return n


def verifica_totali(fattura):
    """SC positiva con IVA a carico: deduce merce, conserva IVA fiscale.

    Ammessa solo quando le righe quadrano per aliquota/natura con i riepiloghi
    e il totale documento conferma la sottrazione. ScontoMaggiorazione e'
    gia' compreso in PrezzoTotale e non si sottrae nuovamente.
    """
    try:
        base = _d(fattura.get('imponibile', 0))
        iva = _d(fattura.get('iva', fattura.get('total_tax', 0)))
        totale = _d(fattura.get('total_amount', 0))
        header_round = _d(fattura.get('arrotondamento_documento') or 0)
        gross = base + iva
        scarto_grezzo = abs(totale - gross)
        modo, sconto, correzione = 'riepilogo_iva', Decimal(0), Decimal(0)
        righe, riepiloghi = fattura.get('linee') or [], fattura.get('riepilogo_iva') or []
        sc = [r for r in righe if str(r.get('tipo_cessione_prestazione') or '').upper() == 'SC']
        # Prova di quadratura delle righe per ogni aliquota/natura; un numero
        # di linea mancante/duplicato non consente di validare gli SC.
        gruppi, riepiloghi_per_gruppo = {}, {}
        numeri = [str(r.get('numero_linea') or '') for r in righe]
        prova = bool(righe and riepiloghi and all(numeri) and len(set(numeri)) == len(numeri))
        for r in righe:
            key = (_d(r.get('aliquota_iva', 0)), r.get('natura') or '')
            gruppi[key] = gruppi.get(key, Decimal(0)) + _d(r.get('prezzo_totale', 0))
        sum_base, sum_iva, sum_round = Decimal(0), Decimal(0), Decimal(0)
        for r in riepiloghi:
            key = (_d(r.get('aliquota_iva', 0)), r.get('natura') or '')
            if key in riepiloghi_per_gruppo:
                prova = False  # non decidere tra riepiloghi della stessa aliquota
            riepiloghi_per_gruppo[key] = r
            sum_base += _d(r.get('imponibile', 0))
            sum_iva += _d(r.get('imposta', 0))
            sum_round += _d(r.get('arrotondamento') or 0)
        prova = prova and set(gruppi) == set(riepiloghi_per_gruppo)
        prova = prova and abs(sum_base-base) <= CENT and abs(sum_iva-iva) <= CENT
        for key, r in riepiloghi_per_gruppo.items():
            if abs(gruppi.get(key, Decimal(0)) + _d(r.get('arrotondamento') or 0) - _d(r.get('imponibile', 0))) > CENT:
                prova = False
        sc_positivi = bool(sc) and all(_d(r.get('prezzo_totale', 0)) > 0 and
                                     _d(r.get('aliquota_iva', 0)) > 0 and not r.get('natura') for r in sc)
        candidato_sc = sum((_d(r['prezzo_totale']) for r in sc), Decimal(0)) if sc_positivi else Decimal(0)
        candidato_round = header_round - sum_round
        candidato = gross - candidato_sc + candidato_round
        # Se il lordo gia' quadra, non dedurre SC gia' trattati dal fornitore.
        if scarto_grezzo > CENT and prova and (sc_positivi or candidato_round != 0) and abs(totale-candidato) <= CENT:
            sconto, correzione = candidato_sc, candidato_round
            modo = 'sconto_merce_iva_a_carico' if sconto else 'arrotondamento_xml'
        atteso = gross - sconto + correzione
        scarto = abs(totale-atteso)
        coherent = scarto <= CENT and base-sconto >= 0
        return {'totali_coerenti': coherent, 'differenza_totali': float(scarto.quantize(CENT, rounding=ROUND_HALF_UP)),
                'sconto_merce': float(sconto), 'imponibile_contabile': float(base-sconto),
                'controllo_totali': {'versione': VERSIONE, 'criterio': modo,
                    'imponibile_fiscale': float(base), 'iva': float(iva),
                    'sconto_merce': float(sconto), 'rettifica_arrotondamento_xml': float(correzione),
                    'totale_atteso': float(atteso), 'scarto_prima_componenti': float(scarto_grezzo)}}
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return {'totali_coerenti': False, 'differenza_totali': None,
                'sconto_merce': 0.0, 'imponibile_contabile': None,
                'controllo_totali': {'versione': VERSIONE, 'criterio': 'dati_non_validi'}}


async def rivalida_originale(db, invoice_id, *, dry_run=True):
    """Rilegge un solo originale; aggiorna prove/derivati, mai importi o ledger."""
    import hashlib
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml_multi
    from app.services.fatture_identita import _testo_xml
    from app.utils.id_fattura import filtro_id
    doc = await db['invoices'].find_one(filtro_id(invoice_id), {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Fattura non trovata')
    xml = _testo_xml(doc)
    if not xml:
        raise HTTPException(409, 'Originale XML non disponibile')
    bodies = parse_fattura_xml_multi(xml)
    index = int(doc.get('xml_body_index', 0))
    if index < 0 or index >= len(bodies) or bodies[index].get('error'):
        raise HTTPException(409, 'Body XML non identificato')
    parsed = bodies[index]
    for field in ('total_amount', 'imponibile', 'iva'):
        if _d(doc.get(field)) != _d(parsed[field]):
            raise HTTPException(409, 'Importi registrati diversi dall’originale: rivalidazione non applicata')
    number = doc.get('invoice_number') or doc.get('numero_fattura')
    if number and number != parsed['invoice_number']:
        raise HTTPException(409, 'Numero fattura diverso dall’originale')
    patch = {k: parsed[k] for k in CAMPI_CONTROLLO if k in parsed}
    # Conserva eventuali arricchimenti nelle righe/riepiloghi; aggiunge solo
    # i campi originali necessari al controllo e al motore contabile.
    lines = [dict(r) for r in doc.get('linee') or []]
    source_lines = {str(r['numero_linea']): r for r in parsed['linee']}
    if len(lines) != len(source_lines) or any(str(r.get('numero_linea')) not in source_lines for r in lines):
        raise HTTPException(409, 'Righe registrate diverse dall’originale')
    for r in lines:
        source = source_lines[str(r['numero_linea'])]
        if _d(r.get('prezzo_totale')) != _d(source['prezzo_totale']):
            raise HTTPException(409, 'Importo riga diverso dall’originale')
        r['tipo_cessione_prestazione'] = source['tipo_cessione_prestazione']
    summaries = [dict(r) for r in doc.get('riepilogo_iva') or []]
    if len(summaries) != len(parsed['riepilogo_iva']):
        raise HTTPException(409, 'Riepiloghi registrati diversi dall’originale')
    for r, source in zip(summaries, parsed['riepilogo_iva']):
        for field in ('aliquota_iva', 'imponibile', 'imposta'):
            if _d(r.get(field)) != _d(source[field]):
                raise HTTPException(409, 'Riepilogo IVA diverso dall’originale')
        r['arrotondamento'] = source['arrotondamento']
    patch.update(linee=lines, riepilogo_iva=summaries)
    changed = any(doc.get(k) != v for k, v in patch.items())
    if changed:
        old = doc.get('verifica_totali_originale')
        if old and not doc.get('verifica_totali_originale_precedente'):
            patch['verifica_totali_originale_precedente'] = old
        patch['verifica_totali_originale'] = {
            'source_sha256': hashlib.sha256(xml.encode('utf-8')).hexdigest(),
            'stato': 'validata_componenti_xml' if parsed['totali_coerenti'] else 'fonte_da_verificare',
            'criterio': parsed['controllo_totali']['criterio'],
            'verified_at': datetime.now(timezone.utc).isoformat(),
        }
        if not dry_run:
            # Include la versione riletta: una modifica concorrente non puo'
            # essere coperta da una prova derivata dalla versione precedente.
            query = {**filtro_id(invoice_id), 'xml_raw': doc.get('xml_raw'),
                     'total_amount': doc.get('total_amount'), 'imponibile': doc.get('imponibile'),
                     'iva': doc.get('iva'), 'linee': doc.get('linee')}
            result = await db['invoices'].update_one(query, {'$set': patch})
            if not result.matched_count:
                raise HTTPException(409, 'Fattura modificata nel frattempo')
    return {'id': invoice_id, 'dry_run': dry_run, 'aggiornata': changed and not dry_run,
            'da_aggiornare': changed, **{k: parsed[k] for k in CAMPI_CONTROLLO if k in parsed}}
