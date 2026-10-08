/* Ceraldi compatibility: canonical ERP HTTP API only, no database credentials.
 * Account records, statement evidence and terminal closures remain distinct.
 * All failures are explicit; unsupported legacy writes never report success.
 */
(function (global) {
  'use strict';

  const PAGE = 500;
  const MAX_ROWS = 100000;
  const cache = new Map();
  const destinations = {
    fatture: '/fatture', fornitori: '/fornitori', movimenti_banca: '/prima-nota#sezione=banca',
    prima_nota_movimenti: '/prima-nota', versamenti: '/prima-nota#sezione=cassa',
    chiusure_giornaliere: '/corrispettivi', corrispettivi: '/corrispettivi',
    incassi: '/prima-nota#sezione=sumup', movimenti_carta: '/prima-nota#sezione=sumup',
    presenze_profili: '/hr', presenze_bonifici_stipendio: '/hr',
    impostazioni: '/admin', ceraldi_stato_condiviso: '/admin',
  };
  class BridgeError extends Error {
    constructor(status, message, destination, code) {
      super(message); this.status = status; this.destination = destination;
      this.code = code || (status === 501 ? 'MODULO_NON_COLLEGATO' : 'BRIDGE_ERROR');
    }
  }
  const fail = (message, resource) => {
    throw new BridgeError(501, message, destinations[resource] || '/');
  };
  const jsonResponse = (value, status, headers) => new Response(JSON.stringify(value), {
    status: status || 200, headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }, headers || {}),
  });
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  function first(o, fields) {
    for (const key of fields) if (o[key] !== undefined && o[key] !== null && o[key] !== '') return o[key];
    return null;
  }
  function number(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(n) ? n : null;
  }
  function id(value) {
    if (value === null || value === undefined || value === '') throw new BridgeError(502, 'Risposta ERP con identificatore mancante.');
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new BridgeError(502, 'Identificatore numerico non rappresentabile: il server deve restituirlo come stringa.');
    return String(value);
  }
  function isoDate(value) { return value === null || value === undefined ? null : String(value).slice(0, 10); }
  function timestamp(o) {
    const v = first(o, ['updated_at', 'created_at', 'imported_at', 'uploaded_at']);
    if (v === null) return null;
    const n = Date.parse(String(v)); return Number.isFinite(n) ? n : null;
  }
  function paymentState(o) {
    // Same vocabulary/precedence as app/services/stato_pagamento_fattura.py.
    const words = ['stato_pagamento', 'stato', 'payment_status'].map(k => String(o[k] || '').trim().toLowerCase());
    const matches = vocabulary => words.some(w => vocabulary.includes(w));
    if (matches(['annullata', 'annullato', 'stornata', 'stornato', 'cancelled', 'canceled', 'deleted', 'eliminata', 'eliminato'])) return 'annullata';
    if (['pagato', 'paid'].some(k => o[k] === true || String(o[k]).toLowerCase() === 'true') || matches(['pagata', 'pagato', 'paid', 'saldata', 'saldato', 'quietanzata', 'quietanzato', 'chiusa', 'chiuso', 'closed'])) return 'pagata';
    if (matches(['parziale', 'partial', 'parzialmente_pagata'])) return 'parziale';
    if (matches(['da_pagare', 'non_pagata', 'non_pagato', 'unpaid', 'aperta'])) return 'da_pagare';
    return 'da_verificare';
  }
  function invoice(o) {
    const state = paymentState(o);
    const td = String(first(o, ['tipo_documento', 'document_type']) || '');
    const rawType = String(first(o, ['tipo', 'document_role']) || '').toLowerCase();
    const type = rawType === 'ddt' ? 'ddt' : /^(TD04|TD08)$/i.test(td) || rawType === 'credit_note' || rawType === 'nota_credito' ? 'nota_credito' : 'fattura';
    const amount = number(first(o, ['total_amount', 'importo_totale', 'totale_documento', 'totale', 'importo_documento', 'importo']));
    const amountPaid = number(first(o, ['amount_paid', 'importo_pagato', 'parz_pagato']));
    // A historic flag can describe only a supplier payment method. Require
    // an explicit statement reference before presenting it as reconciliation.
    const statementReference = first(o, ['movimento_bancario_id', 'bank_transaction_id', 'estratto_conto_id', 'movimento_estratto_conto_id', 'movimento_banca_id', 'riconciliato_con_ec']);
    const reconciled = Boolean(statementReference) && (o.riconciliato === true || o.bank_reconciled === true || o.paypal_riconciliato_banca === true);
    return Object.assign({}, o, {
      id: id(o.id), tipo: type, td: td || null,
      fornitore: first(o, ['supplier_name', 'cedente_denominazione', 'fornitore_ragione_sociale', 'fornitore']),
      numero: first(o, ['invoice_number', 'numero_documento', 'numero_fattura']),
      fatt_num: first(o, ['invoice_number', 'numero_documento', 'numero_fattura']),
      data: isoDate(first(o, ['invoice_date', 'data_documento', 'data_fattura', 'data'])),
      importo: amount === null ? null : type === 'nota_credito' ? -Math.abs(amount) : amount,
      piva: first(o, ['supplier_vat', 'fornitore_partita_iva', 'cedente_piva']),
      denominazione_xml: first(o, ['cedente_denominazione', 'supplier_name', 'fornitore_ragione_sociale']),
      pagamento: first(o, ['metodo_pagamento_effettivo', 'payment_method', 'metodo_pagamento']),
      stato: state, pagato: state === 'pagata', stato_pagamento: state,
      riconciliata: reconciled, stato_riconciliazione: reconciled ? 'riconciliato' : String(o.stato_finanziario || 'da_verificare'),
      scadenza: isoDate(first(o, ['due_date', 'data_scadenza', 'scadenza'])),
      parz_pagato: amountPaid, data_pagamento: isoDate(o.data_pagamento),
      iva: number(first(o, ['total_iva', 'vat_amount', 'iva'])),
      totale_imponibile: number(first(o, ['total_imponibile', 'taxable_amount', 'imponibile'])),
      totale_imposta: number(first(o, ['total_iva', 'vat_amount', 'iva'])),
      note: first(o, ['notes', 'note']),
      fattura_allegata: first(o, ['xml_content', 'xml_originale', 'xml_raw']),
      fattura_allegata_name: first(o, ['xml_filename', 'filename']),
      foto: first(o, ['foto', 'image_base64']),
      assegno: first(o, ['check_number', 'numero_assegno']),
      ts: timestamp(o), deleted_at: o.deleted_at || null,
      bridge_destination: '/fatture', bridge_source: 'invoices',
    });
  }
  function supplier(o) {
    return Object.assign({}, o, {
      id: id(o.id), nome: first(o, ['ragione_sociale', 'denominazione', 'nome', 'name']),
      piva: first(o, ['partita_iva', 'piva', 'vat_number']),
      iban: first(o, ['iban', 'bank_iban']), email: first(o, ['email']),
      metodo_pagamento: first(o, ['metodo_pagamento', 'default_payment_method', 'payment_method']),
      whatsapp: first(o, ['whatsapp']), termini_giorni: first(o, ['termini_giorni']),
      termini_fine_mese: own(o, 'termini_fine_mese') ? o.termini_fine_mese : null,
      bridge_destination: '/fornitori', bridge_source: 'fornitori',
    });
  }
  function statement(o) {
    const amount = number(o.importo);
    const kind = String(o.tipo || '').toLowerCase();
    if (amount !== null && !['entrata', 'uscita'].includes(kind)) throw new BridgeError(502, 'Movimento estratto conto senza tipo entrata/uscita.');
    const invoiceId = first(o, ['fattura_id']) || (o.dettagli_riconciliazione && o.dettagli_riconciliazione.fattura_id);
    const official = o.evidenza_bancaria_ufficiale === true || o.livello_evidenza === 'ufficiale';
    return Object.assign({}, o, {
      id: id(o.id), data: isoDate(o.data), tipo: kind,
      importo: amount === null ? null : kind === 'uscita' ? -Math.abs(amount) : Math.abs(amount),
      descrizione: first(o, ['descrizione', 'descrizione_originale']),
      banca: first(o, ['banca']), fattura_id: invoiceId == null ? null : id(invoiceId),
      fattura_label: first(o, ['fattura_label', 'numero_fattura']),
      abbinata: Boolean(invoiceId) && o.riconciliato === true,
      ignorata: o.tipo_riconciliazione === 'commissione_ignorata',
      verificata_banca: official, riconciliata: o.riconciliato === true,
      stato_riconciliazione: first(o, ['stato_riconciliazione']) || (o.riconciliato === true ? 'riconciliato' : 'da_verificare'),
      deleted_at: o.deleted_at || null,
      bridge_source: 'estratto_conto_movimenti', bridge_destination: '/prima-nota#sezione=banca',
    });
  }
  function movement(o, account) {
    return Object.assign({}, o, {
      id: id(o.id), data: isoDate(o.data), conto: account, registro: account, fonte: account,
      origine_esterna: first(o, ['source', 'origine']),
      importo: number(o.importo), fattura_id: o.fattura_id == null ? null : id(o.fattura_id),
      stato: first(o, ['stato']) || (account === 'banca' && o.provvisorio === true ? 'DA_VERIFICARE' : 'da_verificare'),
      riconciliato: o.riconciliato === true, deleted_at: o.deleted_at || null,
      bridge_source: 'prima_nota_' + account, bridge_destination: '/prima-nota#sezione=' + account,
    });
  }
  function receipt(o) {
    return Object.assign({}, o, {
      id: id(o.id), data: isoDate(o.data), totale: number(first(o, ['totale', 'totale_complessivo'])),
      pagato_contanti: number(o.pagato_contanti),
      pagato_elettronico: number(first(o, ['pagato_elettronico', 'pagato_pos'])),
      stato: first(o, ['stato']) || 'da_verificare', deleted_at: o.deleted_at || null,
      bridge_source: 'corrispettivi', bridge_destination: '/corrispettivi',
    });
  }
  async function closures(api) {
    const receipts = await dataset('corrispettivi', api);
    // The canonical two-phase endpoint has a hard internal 10,000 XML cap.
    // Never silently present a truncated fiscal/terminal comparison.
    if (receipts.length > 10000) throw new BridgeError(413, 'Confronto POS troppo esteso: apri il controllo POS del gestionale e seleziona un anno.', '/corrispettivi');
    const control = await canonical(api, '/api/pos-corrispettivi/controllo-due-fasi?data_da=1900-01-01&data_a=2100-12-31');
    if (control.success !== true || !Array.isArray(control.giorni)) throw new BridgeError(502, 'Risposta del controllo POS non valida.');
    const groups = new Map();
    for (const row of receipts) {
      if (!row.data) throw new BridgeError(502, 'Corrispettivo senza data.');
      if (!groups.has(row.data)) groups.set(row.data, []);
      groups.get(row.data).push(row);
    }
    const controls = new Map();
    for (const day of control.giorni) {
      const date = isoDate(day.data);
      if (!date || controls.has(date)) throw new BridgeError(502, 'Identità giornaliera POS mancante o duplicata.');
      controls.set(date, day);
    }
    const dates = new Set([...groups.keys(), ...controls.keys()]);
    const sumKnown = values => values.some(v => v === null) ? null : Math.round(values.reduce((s, v) => s + v, 0) * 100) / 100;
    return [...dates].map(date => {
      const rows = groups.get(date) || [], day = controls.get(date) || {};
      const circuits = day.pos_per_circuito || {}, sources = day.fonte_pos_per_circuito || {};
      const reconstructed = ['estratto_conto_numia', 'numia_non_usato_estratto'].includes(sources.numia);
      const numia = reconstructed ? null : number(circuits.numia), sumup = number(circuits.sumup);
      const pos = numia === null && sumup === null ? null : Math.round(((numia === null ? 0 : numia) + (sumup === null ? 0 : sumup)) * 100) / 100;
      const total = rows.length ? sumKnown(rows.map(o => o.totale)) : number(first(day, ['totale_xml', 'totale_manuale']));
      const cash = rows.length ? sumKnown(rows.map(o => o.pagato_contanti)) : null;
      const bankPresent = number(day.numero_movimenti_banca) > 0;
      const primary = rows.length === 1 ? rows[0] : {};
      return Object.assign({}, primary, {
        id: rows.length === 1 ? rows[0].id : 'chiusura:' + date, data: date,
        corrispettivo_ids: rows.map(o => o.id), totale_corrispettivi: total, cassa: cash,
        pos: pos, pos_numia: numia, pos_sumup: sumup,
        pos_totale_completo: numia !== null && sumup !== null,
        pos_banca: bankPresent ? number(day.accredito_banca) : null,
        pos_riconciliata: day.riconciliato_banca_reale === true,
        numia_ricostruito_da_banca: reconstructed ? number(circuits.numia) : null,
        fonte_pos_per_circuito: sources,
        stato: day.stato_corrispettivo || (rows.length && rows.every(o => o.stato === 'definitivo_xml') ? 'definitivo_xml' : 'da_verificare'),
        stato_pos: day.stato_accredito || 'da_verificare',
        incassato: cash === null || pos === null ? null : Math.round((cash + pos) * 100) / 100,
        differenza: cash === null || pos === null || total === null ? null : Math.round((cash + pos - total) * 100) / 100,
        deleted_at: null, bridge_source: 'corrispettivi+controllo_pos',
        bridge_destination: '/corrispettivi',
      });
    });
  }
  async function canonical(api, path, opts) {
    const response = await api(path, opts || {});
    if (!response || typeof response.json !== 'function') throw new BridgeError(502, 'Risposta HTTP ERP non valida.');
    let data;
    try { data = await response.json(); } catch (_) { throw new BridgeError(502, 'Il gestionale ha risposto senza dati JSON validi.'); }
    if (!response.ok) {
      const detail = data && (data.detail || data.message);
      throw new BridgeError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail || data), data && data.destination);
    }
    return data;
  }
  async function pages(api, endpoint, arrayKey, offsetKey, query) {
    const rows = []; const seen = new Set(); let expected = null;
    for (let offset = 0; offset <= MAX_ROWS; offset += PAGE) {
      const params = new URLSearchParams(query || {});
      params.set(offsetKey || 'skip', String(offset)); params.set('limit', String(PAGE));
      const data = await canonical(api, endpoint + '?' + params.toString());
      const batch = arrayKey ? data && data[arrayKey] : data;
      if (!Array.isArray(batch) || batch.length > PAGE) throw new BridgeError(502, 'Paginazione ERP non valida: ' + endpoint);
      if (arrayKey) {
        const total = number(data.totale === undefined ? data.total : data.totale);
        if (total === null || total < 0 || !Number.isInteger(total)) throw new BridgeError(502, 'Totale pagina ERP mancante: ' + endpoint);
        if (expected !== null && expected !== total) throw new BridgeError(409, 'Archivio cambiato durante il caricamento: aggiorna la pagina.');
        expected = total;
      }
      for (const row of batch) {
        const key = id(row.id);
        if (seen.has(key)) throw new BridgeError(409, 'Archivio cambiato o identificatore duplicato durante il caricamento.');
        seen.add(key); rows.push(row);
      }
      if (rows.length > MAX_ROWS || (expected !== null && expected > MAX_ROWS)) throw new BridgeError(413, 'Archivio troppo grande: usa la sezione del gestionale con filtri per anno.');
      if (expected !== null && rows.length === expected) return rows;
      if (batch.length < PAGE) {
        if (expected !== null && rows.length !== expected) throw new BridgeError(502, 'Pagina incompleta rispetto al totale ERP.');
        return rows;
      }
    }
    throw new BridgeError(413, 'Limite di paginazione raggiunto.');
  }
  async function dataset(resource, api) {
    const hit = cache.get(resource);
    if (hit && Date.now() - hit.at < 5000) return hit.promise;
    const promise = (async function () {
      switch (resource) {
        case 'fatture': return (await pages(api, '/api/invoices')).map(invoice);
        case 'fornitori': return (await pages(api, '/api/suppliers')).map(supplier);
        case 'movimenti_banca': return (await pages(api, '/api/estratto-conto-movimenti/movimenti', 'movimenti', 'offset')).map(statement);
        case 'prima_nota_movimenti': {
          const cassa = await pages(api, '/api/prima-nota/cassa', 'movimenti');
          const banca = await pages(api, '/api/prima-nota/banca', 'movimenti');
          return cassa.map(o => movement(o, 'cassa')).concat(banca.map(o => movement(o, 'banca')));
        }
        case 'versamenti': return (await pages(api, '/api/prima-nota/cassa', 'movimenti', 'skip', { tipo: 'uscita', categoria: 'Versamento Banca' })).map(o => movement(o, 'cassa'));
        case 'corrispettivi': return (await pages(api, '/api/corrispettivi', null, 'skip', { data_da: '1900-01-01', data_a: '2100-12-31' })).map(receipt);
        case 'chiusure_giornaliere': return closures(api);
        default: fail('La risorsa «' + resource + '» usa un modulo differente. Apri la sezione del gestionale.', resource);
      }
    })();
    cache.set(resource, { at: Date.now(), promise });
    try { return await promise; } catch (e) { cache.delete(resource); throw e; }
  }
  function splitTop(text) {
    let level = 0, quoted = false, current = '', out = [];
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (ch === '"' && text[i - 1] !== '\\') quoted = !quoted;
      if (!quoted && ch === '(') level++;
      if (!quoted && ch === ')') level--;
      if (!quoted && !level && ch === ',') { out.push(current); current = ''; } else current += ch;
    }
    if (level !== 0 || quoted) throw new BridgeError(400, 'Filtro non valido.');
    out.push(current); return out;
  }
  function literal(value) {
    const v = value.trim();
    if (v.startsWith('"') && v.endsWith('"')) {
      try { return JSON.parse(v); } catch (_) { throw new BridgeError(400, 'Valore filtro non valido.'); }
    }
    return v;
  }
  function compare(value, expression, field, resource) {
    let negate = false;
    if (expression.startsWith('not.')) { negate = true; expression = expression.slice(4); }
    const dot = expression.indexOf('.');
    if (dot < 0) fail('Operatore filtro non supportato: ' + expression, resource);
    const op = expression.slice(0, dot), wanted = expression.slice(dot + 1);
    let result;
    if (op === 'is') {
      if (wanted === 'null') result = value == null;
      else if (wanted === 'true' || wanted === 'false') result = value === (wanted === 'true');
      else fail('Filtro is non supportato.', resource);
    } else if (op === 'in') {
      if (!wanted.startsWith('(') || !wanted.endsWith(')')) throw new BridgeError(400, 'Filtro in non valido.');
      result = value != null && splitTop(wanted.slice(1, -1)).map(literal).some(v => String(value) === String(v));
    } else if (op === 'like' || op === 'ilike') {
      const escaped = wanted.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/[%*]/g, '.*').replace(/_/g, '.');
      result = value != null && new RegExp('^' + escaped + '$', op === 'ilike' ? 'i' : '').test(String(value));
    } else if (['eq', 'neq', 'gt', 'gte', 'lt', 'lte'].includes(op)) {
      if (value == null) result = false;
      else {
        const v = typeof value === 'number' ? number(wanted) : typeof value === 'boolean' ? (wanted === 'true' ? true : wanted === 'false' ? false : null) : literal(wanted);
        if (op === 'eq') result = String(value) === String(v);
        if (op === 'neq') result = String(value) !== String(v);
        if (op === 'gt') result = v !== null && value > v;
        if (op === 'gte') result = v !== null && value >= v;
        if (op === 'lt') result = v !== null && value < v;
        if (op === 'lte') result = v !== null && value <= v;
      }
    } else fail('Operatore filtro «' + op + '» non supportato.', resource);
    // SQL null does not become true under NOT (except explicit IS NULL).
    return value == null && op !== 'is' ? false : negate ? !result : result;
  }
  function logical(row, expression, mode, resource) {
    if (!expression.startsWith('(') || !expression.endsWith(')')) throw new BridgeError(400, 'Filtro logico non valido.');
    const results = splitTop(expression.slice(1, -1)).map(item => {
      if (item.startsWith('or.')) return logical(row, item.slice(3), 'or', resource);
      if (item.startsWith('and.')) return logical(row, item.slice(4), 'and', resource);
      const dot = item.indexOf('.'), field = item.slice(0, dot);
      if (dot < 1 || !/^[A-Za-z_][A-Za-z_0-9]*$/.test(field)) fail('Filtro logico non supportato.', resource);
      return compare(row[field], item.slice(dot + 1), field, resource);
    });
    return mode === 'or' ? results.some(Boolean) : results.every(Boolean);
  }
  function filtered(rows, params, resource) {
    const ignored = new Set(['select', 'order', 'offset', 'limit', 'on_conflict']);
    return rows.filter(row => {
      for (const [field, expression] of params.entries()) {
        if (ignored.has(field)) continue;
        if (field === 'or' || field === 'and') { if (!logical(row, expression, field, resource)) return false; continue; }
        if (!/^[A-Za-z_][A-Za-z_0-9]*$/.test(field)) fail('Campo filtro non supportato: ' + field, resource);
        if (!compare(row[field], expression, field, resource)) return false;
      }
      return true;
    });
  }
  function nonnegative(value, fallback) {
    if (value === null || value === undefined) return fallback;
    if (!/^\d+$/.test(String(value))) throw new BridgeError(400, 'Offset/limite non valido.');
    const n = Number(value);
    if (!Number.isSafeInteger(n) || n > MAX_ROWS) throw new BridgeError(400, 'Offset/limite oltre il limite consentito.');
    return n;
  }
  function restResult(rows, params, opts, resource) {
    let selected = filtered(rows, params, resource).slice();
    const order = params.get('order');
    if (order) {
      const rules = splitTop(order).map(item => {
        const bits = item.split('.');
        if (!/^[A-Za-z_][A-Za-z_0-9]*$/.test(bits[0]) || bits.slice(1).some(v => !['asc', 'desc', 'nullsfirst', 'nullslast'].includes(v))) fail('Ordinamento non supportato.', resource);
        return { field: bits[0], desc: bits.includes('desc'), nullsFirst: bits.includes('nullsfirst') };
      });
      selected.sort((a, b) => {
        for (const rule of rules) {
          const av = a[rule.field], bv = b[rule.field];
          if (av == null && bv == null) continue;
          if (av == null) return rule.nullsFirst ? -1 : 1;
          if (bv == null) return rule.nullsFirst ? 1 : -1;
          const diff = av < bv ? -1 : av > bv ? 1 : 0;
          if (diff) return rule.desc ? -diff : diff;
        }
        return 0;
      });
    }
    const total = selected.length;
    let offset = nonnegative(params.get('offset'), 0), limit = nonnegative(params.get('limit'), 1000);
    const headers = new Headers(opts.headers || {}), range = headers.get('Range');
    if (range) {
      const match = /^(?:items=)?(\d+)-(\d+)$/.exec(range);
      if (!match) throw new BridgeError(400, 'Header Range non valido.');
      const start = nonnegative(match[1], 0), end = nonnegative(match[2], 0);
      if (end < start) throw new BridgeError(400, 'Header Range non valido.');
      offset += start; limit = Math.min(limit, end - start + 1);
    }
    selected = selected.slice(offset, offset + limit);
    const select = params.get('select');
    if (select && select !== '*') {
      const fields = splitTop(select);
      if (fields.some(f => !/^[A-Za-z_][A-Za-z_0-9]*$/.test(f))) fail('Proiezione select non supportata.', resource);
      selected = selected.map(row => Object.fromEntries(fields.map(k => [k, own(row, k) ? row[k] : null])));
    }
    return jsonResponse(selected, 200, { 'Content-Range': selected.length ? offset + '-' + (offset + selected.length - 1) + '/' + total : '*/' + total, 'Range-Unit': 'items' });
  }
  function bodyObject(opts, resource) {
    let body;
    try { body = typeof opts.body === 'string' ? JSON.parse(opts.body) : opts.body; } catch (_) { throw new BridgeError(400, 'JSON non valido.'); }
    if (Array.isArray(body)) {
      if (body.length !== 1) fail('Scritture massive e inizializzazioni non supportate.', resource);
      body = body[0];
    }
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new BridgeError(400, 'Oggetto JSON richiesto.');
    return body;
  }
  function allowed(body, fields, resource) {
    const unexpected = Object.keys(body).filter(k => !fields.includes(k));
    if (unexpected.length) fail('Campi senza equivalenza sicura: ' + unexpected.join(', ') + '. Usa il modulo del gestionale.', resource);
  }
  function exactSelection(params, resource, allowName) {
    const filters = [...params.entries()].filter(([k]) => !['select', 'order', 'limit', 'on_conflict'].includes(k));
    if (filters.length !== 1 || !['id', ...(allowName ? ['nome', 'piva'] : [])].includes(filters[0][0]) || !filters[0][1].startsWith('eq.')) fail('La scrittura richiede una singola identità esplicita; operazioni massive non consentite.', resource);
    return filters[0];
  }
  async function resolveOne(resource, params, api, allowName) {
    const selection = exactSelection(params, resource, allowName);
    const rows = filtered(await dataset(resource, api), new URLSearchParams([selection]), resource);
    if (rows.length !== 1) throw new BridgeError(rows.length ? 409 : 404, rows.length ? 'Identità ambigua: apri il modulo del gestionale.' : 'Record non trovato.', destinations[resource]);
    return rows[0];
  }
  function signedAmount(body) {
    const amount = number(body.importo);
    if (amount === null || amount <= 0) throw new BridgeError(422, 'Importo deve essere finito e maggiore di zero.');
    return amount;
  }
  function resultAfterWrite(value, opts) {
    if (String(new Headers(opts.headers || {}).get('Prefer') || '').includes('return=minimal')) return new Response(null, { status: 204 });
    return jsonResponse(value);
  }
  async function write(resource, params, opts, api, method) {
    const prefer = String(new Headers(opts.headers || {}).get('Prefer') || '');
    if (/resolution=ignore-duplicates/.test(prefer)) fail('Importazioni e inizializzazioni automatiche richiedono il modulo Import Documenti.', resource);
    if (resource === 'movimenti_banca') fail('L’estratto conto conserva la prova originale. Associazioni e importazioni si eseguono dal modulo Banca.', resource);
    if (resource === 'fatture') {
      if (method !== 'PATCH' && method !== 'PUT') fail('Importa o elimina fatture dal modulo del gestionale.', resource);
      const body = bodyObject(opts, resource);
      allowed(body, ['note', 'pagamento'], resource);
      if (own(body, 'note') && own(body, 'pagamento')) fail('Salva separatamente note e metodo dal modulo Fatture.', resource);
      const existing = await resolveOne(resource, params, api);
      if (own(body, 'note')) await canonical(api, '/api/fatture-ricevute/fattura/' + encodeURIComponent(existing.id), { method: 'PUT', body: JSON.stringify({ note: body.note }) });
      else if (own(body, 'pagamento')) await canonical(api, '/api/fatture-ricevute/cambia-metodo-pagamento', { method: 'POST', body: JSON.stringify({ fattura_id: existing.id, metodo: body.pagamento }) });
      else fail('Nessun campo aggiornabile nella richiesta.', resource);
      cache.clear();
      const updated = (await dataset(resource, api)).find(o => o.id === existing.id);
      if (!updated) throw new BridgeError(502, 'Record aggiornato non disponibile nella risposta ERP.');
      return resultAfterWrite([updated], opts);
    }
    if (resource === 'rpc/paga_fattura') {
      if (method !== 'POST') fail('Il pagamento richiede POST.', 'fatture');
      const body = bodyObject(opts, 'fatture');
      allowed(body, ['fattura_id', 'scadenza_id', 'importo', 'metodo', 'data_pagamento', 'fornitore', 'numero_fattura', 'idempotency_key'], 'fatture');
      const payload = Object.assign({}, body, { fattura_id: id(body.fattura_id) });
      if (!['cassa', 'banca'].includes(payload.metodo)) throw new BridgeError(422, 'Scegli cassa o banca.');
      const result = await canonical(api, '/api/fatture-ricevute/paga-manuale', { method: 'POST', body: JSON.stringify(payload) });
      cache.clear(); return jsonResponse(result);
    }
    if (resource === 'rpc/riconcilia_fattura') {
      if (method !== 'POST') fail('La riconciliazione richiede POST.', 'fatture');
      const body = bodyObject(opts, 'fatture');
      allowed(body, ['fattura_id', 'movimento_id'], 'fatture');
      // Exact document and statement IDs go to the atomic canonical service.
      // No flag, approximate amount, fabricated movement or automatic override.
      const result = await canonical(api, '/api/fatture-ricevute/riconcilia-con-estratto-conto', {
        method: 'POST', body: JSON.stringify({ fattura_id: id(body.fattura_id), movimento_id: id(body.movimento_id) }),
      });
      cache.clear(); return jsonResponse(result);
    }
    if (resource === 'fornitori') {
      if (!['POST', 'PATCH', 'PUT'].includes(method)) fail('Elimina o unifica i fornitori dal modulo Fornitori.', resource);
      const body = bodyObject(opts, resource);
      allowed(body, ['id', 'nome', 'piva', 'metodo_pagamento', 'iban', 'email', 'telefono', 'note', 'indirizzo', 'cap', 'comune', 'provincia', 'codice_fiscale', 'nazione', 'updated_at', 'created_at'], resource);
      const payload = {};
      for (const k of ['metodo_pagamento', 'iban', 'email', 'telefono', 'note', 'indirizzo', 'cap', 'comune', 'provincia', 'codice_fiscale', 'nazione']) if (own(body, k)) payload[k] = body[k];
      if (own(body, 'nome')) { payload.ragione_sociale = body.nome; payload.denominazione = body.nome; payload.nome = body.nome; }
      let existing = null;
      if (method !== 'POST') existing = await resolveOne(resource, params, api, true);
      else if (params.get('on_conflict')) {
        if (params.get('on_conflict') !== 'nome' || !body.nome) fail('Upsert fornitore senza identità verificabile.', resource);
        const candidates = (await dataset(resource, api)).filter(o => o.nome === body.nome);
        if (candidates.length > 1) throw new BridgeError(409, 'Nome fornitore ambiguo: seleziona l’anagrafica nel gestionale.');
        existing = candidates[0] || null;
      }
      if (existing && body.piva && existing.piva && String(body.piva) !== String(existing.piva)) fail('La partita IVA non può essere cambiata tramite il ponte.', resource);
      if (!existing && own(body, 'piva')) payload.partita_iva = body.piva || '';
      const result = await canonical(api, '/api/suppliers' + (existing ? '/' + encodeURIComponent(existing.id) : ''), { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      const target = existing ? existing.id : id(result.id || result.supplier && result.supplier.id);
      cache.clear();
      const updated = (await dataset(resource, api)).find(o => o.id === target);
      if (!updated) throw new BridgeError(502, 'Fornitore salvato non disponibile nella risposta ERP.');
      return resultAfterWrite([updated], opts);
    }
    if (resource === 'prima_nota_movimenti' || resource === 'versamenti') {
      if (!['POST', 'PATCH', 'PUT', 'DELETE'].includes(method)) fail('Operazione di Prima Nota non supportata.', resource);
      if (resource === 'versamenti' && method !== 'POST') fail('Modifica e annulla il versamento nel gestionale per mantenere coerente la gamba bancaria.', resource);
      let existing = null, account;
      if (method !== 'POST') {
        existing = await resolveOne(resource, params, api);
        account = existing.conto;
        if (existing.categoria === 'Versamento Banca' || existing.trasferimento_collegato_id) fail('Il trasferimento richiede la gestione di entrambe le gambe nel gestionale.', resource);
      }
      const body = method === 'DELETE' ? {} : bodyObject(opts, resource);
      allowed(body, ['id', 'data', 'tipo', 'importo', 'descrizione', 'categoria', 'riferimento', 'note', 'conto', 'registro', 'fonte', 'fornitore', 'fornitore_piva', 'fattura_id', 'estratto_conto_id', 'movimento_bancario_id', 'created_at', 'updated_at'], resource);
      if (method === 'POST') account = resource === 'versamenti' ? 'cassa' : body.conto || body.registro || body.fonte;
      if (!['cassa', 'banca'].includes(account)) throw new BridgeError(422, 'La destinazione cassa o banca deve essere esplicita.');
      if (['conto', 'registro', 'fonte'].some(k => body[k] && body[k] !== account)) fail('Non è consentito spostare il conto tramite una modifica generica.', resource);
      const payload = {};
      for (const k of ['data', 'tipo', 'importo', 'descrizione', 'categoria', 'riferimento', 'note', 'fornitore', 'fornitore_piva']) if (own(body, k)) payload[k] = body[k];
      if (resource === 'versamenti') Object.assign(payload, { tipo: 'uscita', categoria: 'Versamento Banca', descrizione: body.descrizione || 'Versamento contanti da cassa' });
      if (method === 'POST') {
        signedAmount(payload);
        if (!['entrata', 'uscita'].includes(payload.tipo) || !payload.data || !payload.descrizione) throw new BridgeError(422, 'Data, tipo, importo e descrizione sono obbligatori.');
        if (body.fattura_id) fail('Per pagare una fattura usa il pagamento atomico nel modulo Fatture.', 'fatture');
        for (const k of ['estratto_conto_id', 'movimento_bancario_id']) if (body[k]) payload[k] = id(body[k]);
      } else if (own(body, 'fattura_id') || body.estratto_conto_id || body.movimento_bancario_id) fail('Il collegamento a documenti e prove non è una modifica generica.', resource);
      const result = await canonical(api, '/api/prima-nota/' + account + (existing ? '/' + encodeURIComponent(existing.id) : ''), { method: method === 'PATCH' ? 'PUT' : method, ...(method === 'DELETE' ? {} : { body: JSON.stringify(payload) }) });
      if (result.require_force) throw new BridgeError(409, result.message || 'Operazione da confermare nel gestionale.', destinations[resource]);
      cache.clear();
      if (method === 'DELETE') return resultAfterWrite([], opts);
      const target = existing ? existing.id : id(result.id);
      const updated = (await dataset('prima_nota_movimenti', api)).find(o => o.id === target && o.conto === account);
      if (!updated) throw new BridgeError(502, 'Movimento salvato non disponibile nella risposta ERP.');
      return resultAfterWrite([updated], opts);
    }
    if (resource === 'corrispettivi') {
      if (method !== 'POST') fail('Correggi i corrispettivi dal modulo del gestionale; gli XML fiscali non vengono sovrascritti.', resource);
      const body = bodyObject(opts, resource);
      allowed(body, ['data', 'totale', 'pos_reale_serale', 'note'], resource);
      const result = await canonical(api, '/api/corrispettivi/manuale', { method: 'POST', body: JSON.stringify(body) });
      cache.clear();
      const row = (await dataset(resource, api)).find(o => o.id === id(result.corrispettivo_id));
      if (!row) throw new BridgeError(502, 'Corrispettivo salvato non disponibile nella risposta ERP.');
      return resultAfterWrite([row], opts);
    }
    if (resource === 'chiusure_giornaliere') {
      if (!['POST', 'PATCH', 'PUT'].includes(method)) fail('Le chiusure fiscali si correggono dal modulo Corrispettivi.', resource);
      const body = bodyObject(opts, resource);
      allowed(body, ['data', 'pos_numia', 'pos_sumup', 'note', 'updated_at'], resource);
      const existing = method === 'POST' ? null : await resolveOne(resource, params, api);
      const date = body.data || existing && existing.data;
      if (existing && body.data && body.data !== existing.data) fail('Non è consentito spostare una chiusura su un’altra giornata.', resource);
      const supplied = ['pos_numia', 'pos_sumup'].filter(k => own(body, k) && body[k] !== null);
      if (supplied.length !== 1 || !date) fail('Registra un terminale per volta indicando Numia o SumUp; il totale aggregato non identifica il gestore.', resource);
      const value = number(body[supplied[0]]);
      if (value === null || value < 0) throw new BridgeError(422, 'Importo terminale deve essere finito e non negativo.');
      await canonical(api, '/api/pos-corrispettivi/chiusura-giornaliera', { method: 'PUT', body: JSON.stringify({ data: date, importo: value, gestore: supplied[0] === 'pos_numia' ? 'numia' : 'sumup', note: body.note || '' }) });
      cache.clear();
      const row = (await dataset(resource, api)).find(o => o.data === date);
      if (!row) throw new BridgeError(502, 'Chiusura terminale salvata non disponibile nella risposta ERP.');
      return resultAfterWrite([row], opts);
    }
    fail('Operazione non collegata: nessuna modifica è stata eseguita.', resource);
  }
  async function request(path, opts, api) {
    opts = opts || {};
    let resource = '';
    try {
      if (typeof api !== 'function') throw new BridgeError(500, 'Trasporto API autenticato mancante.');
      const relative = String(path).replace(/^\/?(?:ceraldi-compat\/)?rest\/v1\//, '').replace(/^\//, '');
      if (/^https?:/i.test(relative)) throw new BridgeError(400, 'Sono ammesse solo risorse locali del ponte.');
      const url = new URL(relative, 'https://bridge.invalid/');
      resource = url.pathname.slice(1);
      const method = String(opts.method || 'GET').toUpperCase();
      if (method === 'GET' || method === 'HEAD') {
        // Validate expressions even on a legitimately empty collection.
        for (const [field, expression] of url.searchParams.entries()) {
          if (['select', 'order', 'limit', 'offset', 'on_conflict'].includes(field)) continue;
          if (field === 'or' || field === 'and') logical({}, expression, field, resource);
          else {
            if (!/^[A-Za-z_][A-Za-z_0-9]*$/.test(field)) fail('Campo filtro non supportato: ' + field, resource);
            compare(null, expression, field, resource);
          }
        }
        let rows;
        const exactIds = url.searchParams.getAll('id');
        if (resource === 'fatture' && exactIds.length === 1 && exactIds[0].startsWith('eq.') && exactIds[0].slice(3)) {
          // Collection responses deliberately omit document bodies. A document
          // opened by ID uses the canonical detail reader, preserving the XML.
          const expectedId = exactIds[0].slice(3);
          const detailResponse = await api('/api/invoices/' + encodeURIComponent(expectedId), {});
          if (detailResponse.status === 404) rows = [];
          else {
            let detail;
            try { detail = await detailResponse.json(); } catch (_) { throw new BridgeError(502, 'Dettaglio fattura ERP non leggibile.'); }
            if (!detailResponse.ok) throw new BridgeError(detailResponse.status, typeof detail.detail === 'string' ? detail.detail : 'Dettaglio fattura non disponibile.');
            if (!detail || Array.isArray(detail) || id(detail.id) !== expectedId) throw new BridgeError(502, 'Identità del dettaglio fattura ERP non corrispondente.');
            rows = [invoice(detail)];
          }
        } else rows = await dataset(resource, api);
        const response = restResult(rows, url.searchParams, opts, resource);
        return method === 'HEAD' ? new Response(null, { status: response.status, headers: response.headers }) : response;
      }
      return await write(resource, url.searchParams, opts, api, method);
    } catch (error) {
      const status = error instanceof BridgeError ? error.status : 502;
      return jsonResponse({ code: error.code || 'BRIDGE_ERROR', detail: error.message || 'Connessione al gestionale non riuscita.', destination: error.destination || destinations[resource] || '/' }, status);
    }
  }
  global.CeraldiBridgeData = Object.freeze({ request, invalidate() { cache.clear(); } });
})(typeof window === 'undefined' ? globalThis : window);
