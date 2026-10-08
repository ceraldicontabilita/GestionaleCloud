/* Semantic actions for the recovered Ceraldi interface.
 * The old full-row writers never become a generic ERP database transport.
 */
(function (global) {
  'use strict';
  let installed = false;
  const operations = new Map();
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const clone = value => JSON.parse(JSON.stringify(value));
  const destinations = { invoices: '/fatture', suppliers: '/fornitori', bank: '/prima-nota#sezione=banca', import: '/documenti/import' };

  function failure(message, status, destination) {
    const error = new Error(message);
    error.status = status || 501;
    error.code = error.status === 501 ? 'AZIONE_NON_COLLEGATA' : 'AZIONE_NON_SALVATA';
    error.destination = destination || destinations.invoices;
    return error;
  }
  function bridge() {
    if (!global.CeraldiBridge || !global.CeraldiBridgeData) throw failure('Collegamento al gestionale non disponibile.', 503);
    return global.CeraldiBridge;
  }
  function requireWrite() {
    const current = bridge();
    if (typeof current.requireWrite === 'function') current.requireWrite();
    else if (!current.canWrite) throw failure('Account in sola lettura.', 403);
  }
  function invoices() { return typeof fatture !== 'undefined' && Array.isArray(fatture) ? fatture : Array.isArray(global.fatture) ? global.fatture : []; }
  function suppliers() { return typeof fornitori !== 'undefined' && Array.isArray(fornitori) ? fornitori : Array.isArray(global.fornitori) ? global.fornitori : []; }
  function findInvoice(identifier) { return invoices().find(value => String(value.id) === String(identifier)); }
  function identifier(value) {
    if (value === undefined || value === null || value === '') throw failure('Identificatore mancante.', 422);
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw failure('Il server deve fornire questo identificatore come stringa.', 422);
    return String(value);
  }
  function valueOf(name) {
    if (typeof global.gv === 'function') return String(global.gv(name) || '');
    const element = global.document && global.document.getElementById(name);
    return element ? String(element.value || '') : '';
  }
  function date(value) {
    const text = String(value || '').slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || !Number.isFinite(Date.parse(text)) || new Date(text).toISOString().slice(0, 10) !== text) throw failure('Indica una data di pagamento valida.', 422);
    return text;
  }
  function amount(value) {
    const parsed = typeof value === 'number' ? value : parseFloat(String(value || '').replace(',', '.'));
    if (!Number.isFinite(parsed) || parsed <= 0) throw failure('Indica un importo di pagamento maggiore di zero.', 422);
    return Math.round(parsed * 100) / 100;
  }
  function account(method) {
    const text = String(method || '').trim().toLowerCase();
    if (['cassa', 'contanti', 'cash'].includes(text)) return 'cassa';
    if (['banca', 'bonifico', 'sepa', 'sdd', 'rid', 'assegno', 'carta', 'bank_transfer', 'credit_card'].includes(text)) return 'banca';
    throw failure('Scegli Contanti oppure un metodo bancario esplicito.', 422);
  }
  function supplierMethod(method) {
    const text = String(method || '').trim().toLowerCase();
    if (['contanti', 'cash'].includes(text)) return 'cassa';
    if (['bonifico', 'sepa', 'sdd', 'bank_transfer'].includes(text)) return 'banca';
    if (['cassa', 'banca', 'misto', 'assegno', 'rid', 'carta'].includes(text)) return text;
    throw failure('Metodo fornitore non valido.', 422, destinations.suppliers);
  }
  function equal(left, right) {
    if ((left === '' || left == null) && (right === '' || right == null)) return true;
    return JSON.stringify(left) === JSON.stringify(right);
  }
  async function json(response) {
    let result;
    try { result = response.status === 204 ? null : await response.json(); }
    catch (_) { throw failure('Risposta del gestionale non leggibile.', 502); }
    if (!response.ok) {
      const detail = result && (result.detail || result.message || result.error);
      const error = failure(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : 'Operazione non accettata dal gestionale.', response.status, result && result.destination);
      if (result && result.code) error.code = result.code;
      throw error;
    }
    return result;
  }
  async function request(path, options) { return json(await global.CeraldiBridgeData.request(path, options || {}, bridge().api)); }
  async function canonical(path, options) { return json(await bridge().api(path, options || {})); }
  function toApp(row) {
    const object = typeof global.dbToApp === 'function' ? global.dbToApp(row) : Object.assign({}, row, {
      parzPagato: row.parz_pagato || 0, dataPagamento: row.data_pagamento || '', pagamentoOrigine: row.pagamento_origine || '',
      riconciliazione: row.riconciliazione || null, riconciliazioneStorico: row.riconciliazione_storico || [], pagamentiManuali: row.pagamenti_manuali || []
    });
    object.id = identifier(row.id);
    object.stato = row.stato || 'da_verificare';
    object.riconciliata = row.riconciliata === true;
    object.bridgeSource = row.bridge_source;
    object.bridgeDestination = row.bridge_destination || destinations.invoices;
    return object;
  }
  async function snapshot(id) {
    const rows = await request('fatture?id=eq.' + encodeURIComponent(identifier(id)) + '&select=*');
    if (!Array.isArray(rows) || rows.length !== 1) throw failure(rows && rows.length ? 'Identità fattura ambigua.' : 'Fattura non trovata nel gestionale.', rows && rows.length ? 409 : 404);
    return { row: rows[0], app: toApp(rows[0]) };
  }
  function publish(current, target) {
    const fresh = current.app;
    if (target) Object.assign(target, clone(fresh));
    const list = invoices();
    const index = list.findIndex(value => String(value.id) === fresh.id);
    if (index >= 0) Object.assign(list[index], clone(fresh));
    if (typeof global._updateCacheRow === 'function') global._updateCacheRow(current.row);
    if (typeof global.save === 'function') global.save(list);
    return current.row;
  }
  async function refresh(id, target) { const current = await snapshot(id); publish(current, target); return current; }
  function render() {
    for (const name of ['renderLista', 'aggiornaAlertBanner', 'aggiornaHeroCard']) {
      if (typeof global[name] === 'function') { try { global[name](); } catch (_) { /* A hidden panel may not be mounted. */ } }
    }
  }
  function notify(message) { if (typeof global.toast === 'function') global.toast(message, { forza: true }); }
  function report(error) {
    notify(error.message || 'Operazione non salvata.');
    if (error.status === 501 && typeof bridge().showUnsupported === 'function') bridge().showUnsupported(error.message, error.destination);
    if (typeof global._registraErrore === 'function') global._registraErrore('database', error.message || String(error));
  }
  async function once(key, task) {
    if (operations.has(key)) return operations.get(key);
    const pending = task(); operations.set(key, pending);
    try { return await pending; } finally { operations.delete(key); }
  }
  function residual(current) {
    if (current.row.importo_residuo != null) return Math.max(0, Math.round(Number(current.row.importo_residuo) * 100) / 100);
    if (current.app.stato === 'pagata') return 0;
    const total = Math.abs(Number(current.app.importo));
    const paid = Math.abs(Number(current.row.importo_pagato != null ? current.row.importo_pagato : current.row.parz_pagato || 0));
    if (!Number.isFinite(total) || !Number.isFinite(paid)) throw failure('Importi fattura da verificare nel gestionale.', 409);
    return Math.max(0, Math.round((total - paid) * 100) / 100);
  }
  async function operationKey(parts) {
    const text = JSON.stringify(parts);
    if (global.crypto && global.crypto.subtle && typeof TextEncoder !== 'undefined') {
      const digest = await global.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
      return 'ceraldi:' + Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    }
    // Deterministic fallback for older browsers. This is a retry identity, not a credential.
    let first = 2166136261, second = 2246822519;
    for (let index = 0; index < text.length; index++) {
      first = Math.imul(first ^ text.charCodeAt(index), 16777619);
      second = Math.imul(second ^ text.charCodeAt(index), 3266489917);
    }
    return 'ceraldi:' + (first >>> 0).toString(16) + ':' + (second >>> 0).toString(16) + ':' + text.length;
  }
  async function pay(id, details) {
    requireWrite();
    id = identifier(id);
    const options = details || {};
    const method = account(options.metodo), paidOn = date(options.data);
    return once('pay:' + id, async () => {
      const before = await snapshot(id);
      if (before.app.tipo === 'nota_credito' || before.app.tipo === 'ddt' || before.app.stato === 'annullata') throw failure('Questo documento non si paga come fattura fornitore.', 409);
      const remaining = residual(before);
      const payment = options.importo == null ? remaining : amount(options.importo);
      if (payment <= 0 || payment - remaining > 0.005) throw failure('Importo superiore al residuo o fattura già saldata.', 409);
      const body = { fattura_id: id, importo: payment, metodo: method, data_pagamento: paidOn, fornitore: before.app.fornitore || 'Fornitore', numero_fattura: before.app.numero || '' };
      if (options.scadenza_id) body.scadenza_id = identifier(options.scadenza_id);
      body.idempotency_key = await operationKey([id, body.scadenza_id || '', payment, method, paidOn, before.row.importo_pagato || 0]);
      if (options.reference) {
        const reference = String(options.reference).trim();
        const notes = String(before.app.note || '');
        if (reference && !notes.split('\n').includes(reference)) await request('fatture?id=eq.' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify({ note: notes + (notes ? '\n' : '') + reference }) });
      }
      const result = await request('rpc/paga_fattura', { method: 'POST', body: JSON.stringify(body) });
      if (!result || result.success !== true || !result.movimento_id) throw failure('Pagamento non confermato dal gestionale.', 502);
      const after = await refresh(id, options.target || findInvoice(id));
      // A bank proposal must stay distinguishable from an EC-confirmed payment.
      if (method === 'banca' && result.pagamento_confermato !== false && result.in_attesa_estratto_ufficiale !== true && result.riconciliato !== true) {
        throw failure('Il servizio banca non ha restituito lo stato di attesa richiesto. Verifica il movimento nel gestionale.', 502, destinations.bank);
      }
      return { result, row: after.row, app: after.app, pending: result.pagamento_confermato === false || result.in_attesa_estratto_ufficiale === true };
    });
  }
  async function reconcile(id, movementId, target) {
    requireWrite(); id = identifier(id); movementId = identifier(movementId);
    return once('reconcile:' + id + ':' + movementId, async () => {
      const result = await request('rpc/riconcilia_fattura', { method: 'POST', body: JSON.stringify({ fattura_id: id, movimento_id: movementId }) });
      if (!result || result.success !== true) throw failure('Riconciliazione non confermata dal gestionale.', 502, destinations.bank);
      const after = await refresh(id, target || findInvoice(id));
      // Reload statement rows through the canonical reader, never by setting abbinata locally.
      if (typeof global.loadMovimentiBanca === 'function') await global.loadMovimentiBanca();
      return { result, row: after.row, app: after.app };
    });
  }
  async function candidates(id) {
    id = identifier(id);
    const result = await canonical('/api/fatture-ricevute/candidati-bancari/' + encodeURIComponent(id));
    if (!result || String(result.fattura_id) !== id || !Array.isArray(result.candidati)) throw failure('Risposta dei candidati bancari non valida.', 502, destinations.bank);
    return result;
  }
  async function reconcileGroup(selected, movements) {
    requireWrite();
    if (!Array.isArray(selected) || !selected.length || !Array.isArray(movements) || !movements.length) throw failure('Seleziona fatture e movimenti.', 422, destinations.bank);
    if (selected.length > 1 && movements.length > 1) throw failure('Un gruppo con più fatture e più movimenti richiede quote esplicite per ogni abbinamento. Usa il controllo del gestionale.', 501, destinations.bank);
    const ids = selected.map(value => identifier(value.id)), movementIds = movements.map(value => identifier(value.id));
    if (new Set(ids).size !== ids.length || new Set(movementIds).size !== movementIds.length) throw failure('Il gruppo contiene identificatori duplicati.', 422, destinations.bank);
    const statements = await request('movimenti_banca?select=*&limit=100000');
    const official = movementIds.map(id => statements.find(value => String(value.id) === id));
    for (const movement of official) {
      // Mirror the canonical official-evidence convention for historic EC rows.
      if (!movement || movement.tipo !== 'uscita' || movement.provvisorio === true || movement.in_attesa_estratto_ufficiale === true || movement.ignorata === true || movement.in_quarantena === true || ['deleted', 'archived'].includes(movement.status) || (own(movement, 'livello_evidenza') && movement.livello_evidenza !== 'ufficiale' && movement.evidenza_bancaria_ufficiale !== true)) throw failure('Il gruppo richiede movimenti attivi dell’estratto conto ufficiale.', 409, destinations.bank);
    }
    const before = await Promise.all(ids.map(snapshot));
    const requests = [];
    if (movements.length === 1) {
      const associations = before.map(current => ({ id: current.app.id, quota_cents: Math.round(residual(current) * 100) }));
      if (associations.some(value => value.quota_cents <= 0) || associations.reduce((sum, value) => sum + value.quota_cents, 0) !== Math.round(Math.abs(Number(official[0].importo)) * 100)) throw failure('Le quote residue delle fatture non quadrano con il movimento al centesimo.', 409, destinations.bank);
      requests.push({ movimento_id: movementIds[0], tipo: 'fattura', associazioni: associations });
    } else {
      const available = Math.round(residual(before[0]) * 100), total = official.reduce((sum, value) => sum + Math.round(Math.abs(Number(value.importo)) * 100), 0);
      if (total > available || total <= 0) throw failure('La somma dei movimenti supera il residuo della fattura.', 409, destinations.bank);
      official.forEach(movement => requests.push({ movimento_id: identifier(movement.id), tipo: 'fattura', associazioni: [{ id: ids[0], quota_cents: Math.round(Math.abs(Number(movement.importo)) * 100) }] }));
    }
    let confirmed = 0, operationError = null;
    try {
      for (const body of requests) {
        const result = await canonical('/api/operazioni-da-confermare/smart/riconcilia-manuale', { method: 'POST', body: JSON.stringify(body) });
        if (!result || result.success !== true) throw failure('Allocazione bancaria non confermata dal gestionale.', 502, destinations.bank);
        const allocated = Array.isArray(result.allocazioni) ? result.allocazioni : [];
        if (body.associazioni.some(item => !allocated.some(value => String(value.fattura_id) === item.id && value.quota_cents === item.quota_cents))) throw failure('Le quote restituite dal gestionale non corrispondono al prospetto richiesto.', 502, destinations.bank);
        confirmed++;
      }
    } catch (error) {
      if (confirmed) error.message = confirmed + ' movimenti già confermati; il successivo non è stato completato. ' + error.message;
      operationError = error;
      throw error;
    } finally {
      if (typeof global.CeraldiBridgeData.invalidate === 'function') global.CeraldiBridgeData.invalidate();
      const readbacks = await Promise.allSettled(ids.map((id, index) => refresh(id, selected[index])));
      let readbackError = readbacks.find(value => value.status === 'rejected');
      try { if (typeof global.loadMovimentiBanca === 'function') await global.loadMovimentiBanca(); }
      catch (error) { readbackError = { reason: error }; }
      render();
      if (readbackError) {
        if (operationError) operationError.message += ' Anche l’aggiornamento dei dati è fallito: sincronizza prima di riprovare.';
        else throw failure(confirmed + ' movimenti confermati, ma i dati aggiornati non sono disponibili. Sincronizza prima di riprovare.', 502, destinations.bank);
      }
    }
    notify(confirmed + ' movimenti riconciliati dal gestionale.');
    return { success: true, confirmed };
  }
  function changed(proposed, before) { return Object.keys(proposed).filter(key => !equal(proposed[key], before[key])); }
  function paymentIntent(proposed, before) {
    const records = Array.isArray(proposed.pagamentiManuali) ? proposed.pagamentiManuali : [];
    const priorRecords = Array.isArray(before.pagamentiManuali) ? before.pagamentiManuali : [];
    if (records.length > priorRecords.length) {
      if (records.length !== priorRecords.length + 1 || !equal(records.slice(0, -1), priorRecords)) throw failure('Registra un pagamento alla volta dal pulsante Paga.', 501);
      const last = records[records.length - 1];
      return { metodo: last.metodo, data: last.data, importo: last.importo, target: proposed };
    }
    if ((proposed.stato === 'pagata' || proposed.stato === 'parziale') && (proposed.stato !== before.stato || Number(proposed.parzPagato || 0) > Number(before.parzPagato || 0))) {
      if (proposed.pagamentoOrigine !== 'manuale' || !proposed.pagamento || !(proposed.dataPagamento || proposed.dataPag)) throw failure('Lo stato Pagata richiede metodo, data e un pagamento esplicito. Usa Paga.', 501);
      return { metodo: proposed.pagamento, data: proposed.dataPagamento || proposed.dataPag, importo: proposed.stato === 'parziale' ? Number(proposed.parzPagato || 0) - Number(before.parzPagato || 0) : undefined, target: proposed };
    }
    return null;
  }
  async function update(proposed) {
    requireWrite();
    const id = identifier(proposed && proposed.id);
    return once('update:' + id, async () => {
      const initial = await snapshot(id), before = initial.app;
      const changes = changed(proposed, before);
      const movementId = proposed.riconciliazione && proposed.riconciliazione.movId;
      const previousMovementId = before.riconciliazione && before.riconciliazione.movId;
      const newMovement = movementId && String(movementId) !== String(previousMovementId);
      let intent;
      try { intent = newMovement ? null : paymentIntent(proposed, before); }
      catch (error) { publish(initial, proposed); throw error; }
      const safe = ['note', 'pagamento'];
      const display = ['ts', 'incompleta', 'bridgeSource', 'bridgeDestination'];
      const derived = ['stato', 'parzPagato', 'dataPag', 'dataPagamento', 'pagamentoOrigine', 'pagamentoImpostatoIl', 'riconciliata', 'riconciliazione', 'riconciliazioneStorico', 'pagamentiManuali'];
      const blocked = changes.filter(key => !safe.includes(key) && !display.includes(key) && !((intent || newMovement) && derived.includes(key)));
      if (blocked.length) {
        publish(initial, proposed);
        throw failure('Questi campi richiedono la modifica documentale del gestionale: ' + blocked.join(', ') + '.', 501);
      }
      if (!intent && !newMovement && changes.some(key => derived.includes(key))) {
        publish(initial, proposed);
        throw failure('Pagamento e riconciliazione si modificano con le azioni contabili. Lo stato non è un campo libero.', 501, destinations.bank);
      }
      try {
        if (changes.includes('note')) await request('fatture?id=eq.' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify({ note: proposed.note || '' }) });
        if (changes.includes('pagamento') && !intent && !newMovement) {
          if (!proposed.pagamento) throw failure('Per rimuovere un metodo usa il modulo Fatture.', 501);
          await request('fatture?id=eq.' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify({ pagamento: supplierMethod(proposed.pagamento) }) });
        }
        if (newMovement) return [(await reconcile(id, movementId, proposed)).row];
        if (intent) return [(await pay(id, intent)).row];
        return [(await refresh(id, proposed)).row];
      } catch (error) {
        try { await refresh(id, proposed); } catch (_) { publish(initial, proposed); }
        throw error;
      }
    });
  }
  const fieldNames = { parz_pagato: 'parzPagato', data_pagamento: 'dataPagamento', pagamento_origine: 'pagamentoOrigine', pagamento_impostato_il: 'pagamentoImpostatoIl', riconciliazione_storico: 'riconciliazioneStorico', pagamenti_manuali: 'pagamentiManuali', fatt_num: 'fattNum', num_ddt: 'numDdt', avviso_giorni: 'avvisoGiorni' };
  async function updatePartial(id, fields) {
    const before = await snapshot(id), proposed = clone(before.app);
    for (const [key, value] of Object.entries(fields || {})) proposed[fieldNames[key] || key] = value;
    const rows = await update(proposed);
    return rows[0].ts == null ? null : rows[0].ts;
  }
  async function insert(proposed) {
    requireWrite();
    const xml = proposed && proposed.fatturaAllegata;
    if (typeof xml !== 'string' || !xml.trim().startsWith('<') || !/FatturaElettronica\b/.test(xml)) throw failure('Per creare una fattura usa un XML originale oppure Import Documenti. L’inserimento manuale richiede il writer documentale del gestionale.', 501, destinations.import);
    const body = new FormData();
    const filename = String(proposed.fatturaAllegataName || 'fattura.xml').replace(/[/\\]/g, '_');
    body.append('file', new Blob([xml], { type: 'application/xml' }), filename);
    const result = await canonical('/api/fatture/upload-xml', { method: 'POST', body });
    if (!result || result.success !== true || !result.invoice || result.invoice.id == null) throw failure('Importazione XML non confermata dal gestionale.', 502, destinations.import);
    const newId = identifier(result.invoice.id), oldId = proposed.id;
    proposed.id = newId;
    const current = await refresh(newId, proposed);
    const list = invoices(), old = list.findIndex(value => String(value.id) === String(oldId));
    if (old >= 0) Object.assign(list[old], clone(current.app));
    return [current.row];
  }
  async function saveSupplier(name, fields) {
    requireWrite(); name = String(name || '').trim();
    if (!name) throw failure('Nome fornitore richiesto.', 422, destinations.suppliers);
    const found = await request('fornitori?nome=eq.' + encodeURIComponent(name) + '&select=*');
    if (!Array.isArray(found) || found.length > 1) throw failure('Identità fornitore ambigua: scegli la sua anagrafica.', 409, destinations.suppliers);
    const payload = Object.assign({}, fields || {});
    if (own(payload, 'metodo_pagamento')) payload.metodo_pagamento = supplierMethod(payload.metodo_pagamento);
    let result;
    if (found.length) result = Object.keys(payload).length ? await request('fornitori?id=eq.' + encodeURIComponent(found[0].id), { method: 'PATCH', body: JSON.stringify(payload) }) : found;
    else result = await request('fornitori', { method: 'POST', body: JSON.stringify(Object.assign({ nome: name }, payload)) });
    if (!Array.isArray(result) || result.length !== 1) throw failure('Fornitore non confermato dal gestionale.', 502, destinations.suppliers);
    const list = suppliers(); if (!list.includes(name)) { list.push(name); list.sort(); }
    if (typeof global.saveF === 'function') global.saveF(list);
    if (typeof global.aggiornaDL === 'function') global.aggiornaDL();
    return result;
  }
  async function archiveInvoice(id, confirmedWarning) {
    requireWrite(); id = identifier(id);
    return once('archive:' + id, async () => {
      const result = await canonical('/api/fatture/' + encodeURIComponent(id) + '?force=' + (confirmedWarning ? 'true' : 'false') + '&hard_delete=false', { method: 'DELETE' });
      if (result && result.require_force === true && result.status === 'warning') {
        // A validation preview is never treated as a completed deletion.
        return { success: false, requires_confirmation: true, warning: result, id };
      }
      if (!result || result.success !== true || String(result.invoice_id) !== id) throw failure('Archiviazione non confermata dal gestionale.', 502);
      let archived = false;
      try {
        const detail = await canonical('/api/invoices/' + encodeURIComponent(id));
        if (!detail || String(detail.id) !== id) throw failure('Identità del documento archiviato non corrispondente.', 502);
        archived = ['deleted', 'archived'].includes(detail.status) || ['deleted', 'archived'].includes(detail.entity_status);
      } catch (error) {
        if (error.status === 404) archived = true;
        else throw failure('Il gestionale ha archiviato la fattura, ma il controllo finale è fallito. Sincronizza prima di riprovare. ' + error.message, 502);
      }
      if (!archived) throw failure('Il documento risulta ancora attivo dopo l’archiviazione. Verifica il suo stato nel gestionale.', 502);
      if (typeof global.CeraldiBridgeData.invalidate === 'function') global.CeraldiBridgeData.invalidate();
      const list = invoices();
      for (let index = list.length - 1; index >= 0; index--) if (String(list[index].id) === id) list.splice(index, 1);
      if (typeof global.save === 'function') global.save(list);
      render();
      return { success: true, archived: true, result };
    });
  }
  async function remove(id) { return archiveInvoice(id, false); }
  async function archiveFromUi(id) {
    try {
      const preview = await remove(id);
      if (preview.requires_confirmation) {
        const warnings = Array.isArray(preview.warning.warnings) ? preview.warning.warnings.map(String) : [];
        const related = preview.warning.entita_correlate || {};
        const message = 'Il gestionale richiede una seconda conferma per archiviare la fattura.\n\n' + warnings.join('\n') + '\n\nEntità collegate: ' + String(related.totale_entita || 0) + '.\nConfermi l’archiviazione e gli effetti elencati?';
        if (typeof global.confirm !== 'function' || !global.confirm(message)) { notify('Archiviazione annullata.'); return { success: false, cancelled: true, warning: preview.warning }; }
        const result = await archiveInvoice(id, true);
        if (!result.success) throw failure('Il gestionale richiede un nuovo controllo prima dell’archiviazione.', 409);
        notify('Fattura archiviata dal gestionale.'); return result;
      }
      notify('Fattura archiviata dal gestionale.'); return preview;
    } catch (error) { report(error); return false; }
  }
  function paymentMessage(outcome) {
    if (outcome.pending) return outcome.result.message || 'Pagamento bancario registrato in attesa dell’estratto conto. La fattura resta aperta.';
    return outcome.app.stato === 'pagata' ? 'Fattura saldata in cassa.' : 'Pagamento in cassa registrato; resta un residuo.';
  }
  async function quickPay(id, method, extra, backup, selectedDate) {
    try {
      const details = extra || {};
      const reference = [['numAssegno', 'Assegno'], ['intestatario', 'Intestatario'], ['banca', 'Banca assegno'], ['contoPagamento', 'Conto/carta']].filter(([key]) => details[key]).map(([key, label]) => label + ': ' + String(details[key]).trim()).join(' · ');
      const result = await pay(id, { metodo: method, data: selectedDate, reference });
      render(); notify(paymentMessage(result)); return result;
    } catch (error) { render(); report(error); return false; }
  }
  async function paySelection(list, methodFor, dateFor) {
    requireWrite();
    let cash = 0, pending = 0, errors = 0;
    for (const invoice of list) {
      try {
        const result = await pay(invoice.id, { metodo: methodFor(invoice), data: dateFor(invoice), target: invoice });
        result.pending ? pending++ : cash++;
      } catch (error) { errors++; report(error); }
    }
    render(); notify(cash + ' pagamenti in cassa, ' + pending + ' in attesa banca' + (errors ? ', ' + errors + ' non salvati.' : '.'));
    return { cash, pending, errors };
  }
  async function saveEdit() {
    const id = typeof editId !== 'undefined' ? editId : global.editId;
    if (!id) return;
    try {
      const current = await snapshot(id), proposed = clone(current.app);
      const form = { fornitore: valueOf('eForn2').trim(), numero: valueOf('eNum2').trim(), fattNum: valueOf('eFattNum2').trim(), numDdt: valueOf('eNumDdt2').trim(), data: valueOf('eData2'), importo: parseFloat(valueOf('eImp2').replace(',', '.')), note: valueOf('eNote2').trim(), scadenza: valueOf('eScad2'), assegno: valueOf('eAss2').trim(), assInt: valueOf('eAssInt2').trim(), assBanca: valueOf('eAssBanca2').trim(), bonIban: valueOf('eBonIban2').trim(), bonCaus: valueOf('eBonCaus2').trim(), bonData: valueOf('eBonData2'), bonRif: valueOf('eBonRif2').trim() };
      for (const [key, value] of Object.entries(form)) {
        const elementNames = { fornitore: 'eForn2', numero: 'eNum2', fattNum: 'eFattNum2', numDdt: 'eNumDdt2', data: 'eData2', importo: 'eImp2', note: 'eNote2', scadenza: 'eScad2', assegno: 'eAss2', assInt: 'eAssInt2', assBanca: 'eAssBanca2', bonIban: 'eBonIban2', bonCaus: 'eBonCaus2', bonData: 'eBonData2', bonRif: 'eBonRif2' };
        if (global.document && global.document.getElementById(elementNames[key])) proposed[key] = value;
      }
      proposed.pagamento = typeof ePag !== 'undefined' ? ePag : proposed.pagamento;
      proposed.tipo = typeof eTipo !== 'undefined' ? eTipo : proposed.tipo;
      proposed.stato = typeof eStato !== 'undefined' ? eStato : proposed.stato;
      if (proposed.stato !== current.app.stato) {
        proposed.dataPagamento = valueOf('eDataPag2');
        proposed.parzPagato = proposed.stato === 'parziale' ? parseFloat(valueOf('eParzPagato').replace(',', '.')) : current.app.parzPagato;
        proposed.pagamentoOrigine = 'manuale';
      }
      const check = global.document && global.document.getElementById('eRiconciliata');
      if (check && check.checked !== current.app.riconciliata) throw failure('La spunta di riconciliazione richiede un movimento reale. Usa Riconcilia.', 501, destinations.bank);
      const rows = await update(proposed);
      if (typeof global.chiudiEdit === 'function') global.chiudiEdit();
      else { const overlay = global.document && global.document.getElementById('editOv'); if (overlay) overlay.remove(); }
      render(); notify('Fattura aggiornata dal gestionale.'); return rows;
    } catch (error) { report(error); render(); return false; }
  }
  async function savePartialPayment(button) {
    const state = typeof PRP !== 'undefined' ? PRP : global.PRP;
    if (!state) return false;
    const label = button && button.textContent;
    if (button) { button.disabled = true; button.textContent = 'Salvo…'; }
    try {
      const value = typeof global.pprpImporto === 'function' ? global.pprpImporto() : valueOf('ppAltro');
      const choice = state.scelta >= 0 && state.voci ? state.voci[state.scelta] : null;
      const options = { metodo: valueOf('ppMetodo'), data: valueOf('ppData'), importo: value };
      if (choice && choice.scadenza_id) options.scadenza_id = choice.scadenza_id;
      const result = await pay(state.id, options);
      if (typeof global.pnChiudi === 'function') global.pnChiudi('pnPaga');
      render(); notify(paymentMessage(result)); return result;
    } catch (error) { report(error); return false; }
    finally { if (button) { button.disabled = false; button.textContent = label; } }
  }
  async function linkFromList(index, invoiceId) {
    const movement = (global._nonAbbinati || [])[index];
    if (!movement || !findInvoice(invoiceId)) return false;
    if (typeof global.confirm === 'function' && !global.confirm('Collegare questa fattura al movimento reale dell’estratto conto? Il gestionale verificherà importo e causale.')) return false;
    try {
      const result = await reconcile(invoiceId, movement.id);
      const overlay = global.document && global.document.getElementById('_cfOv'); if (overlay) overlay.remove();
      render(); if (typeof global.renderRiconciliazione === 'function') global.renderRiconciliazione();
      notify(result.result.message || 'Fattura riconciliata con l’estratto conto.'); return result;
    } catch (error) { report(error); return false; }
  }
  async function confirmPayment(index, confirmed) {
    const proposal = (global._pagDaConfermare || [])[index];
    if (!proposal) return false;
    if (!confirmed) { global._pagDaConfermare.splice(index, 1); if (typeof global.renderRiconciliazione === 'function') global.renderRiconciliazione(); notify('Proposta rimossa da questa sessione.'); return true; }
    if (!proposal.mov || !proposal.fatt) return unsupported('Le riconciliazioni cumulative richiedono il controllo del gestionale.', destinations.bank);
    try {
      const result = await reconcile(proposal.fatt.id, proposal.mov.id, proposal.fatt);
      global._pagDaConfermare.splice(index, 1);
      render(); if (typeof global.renderRiconciliazione === 'function') global.renderRiconciliazione();
      notify(result.result.message || 'Riconciliazione confermata dal gestionale.'); return result;
    } catch (error) { report(error); return false; }
  }
  function unsupported(message, destination) { const error = failure(message, 501, destination); report(error); return false; }
  function blockedWriter(message, destination) { return async function () { requireWrite(); throw failure(message, 501, destination); }; }
  function install() {
    if (installed) return; installed = true;
    if (typeof bridge().addApiRule === 'function') bridge().addApiRule(/^\/api\/operazioni-da-confermare\/smart\/riconcilia-manuale$/, ['POST']);
    if (typeof bridge().addApiRule === 'function') bridge().addApiRule(/^\/api\/fatture\/(?!all$)[^/]+$/, ['DELETE']);
    const originalOpenReconciliation = global.apriRiconciliaDaFattura;
    if (typeof originalOpenReconciliation === 'function') global.apriRiconciliaDaFattura = async function (id) {
      try {
        const result = await candidates(id);
        await refresh(id, findInvoice(id));
        if (typeof global.loadMovimentiBanca === 'function') await global.loadMovimentiBanca();
        originalOpenReconciliation(identifier(id));
        if (global._rfStato) global._rfStato.candidatiCanonici = result;
        const overlay = global.document && global.document.getElementById('_riconciliaDaFattOv');
        if (overlay && typeof global.document.createElement === 'function') {
          const note = global.document.createElement('div'); note.className = 'rf-avviso';
          note.textContent = result.candidati.length + ' candidati verificati dal gestionale' + (result.totale_candidati > result.candidati.length ? ' su ' + result.totale_candidati : '') + '. L’abbinamento viene controllato sul server prima della conferma.';
          const list = overlay.querySelector && overlay.querySelector('#rfLista'); if (list && list.parentNode) list.parentNode.insertBefore(note, list);
        }
        return result;
      } catch (error) { report(error); return false; }
    };
    global.dbUpdate = async function (proposed) { try { return await update(proposed); } catch (error) { report(error); throw error; } };
    global.dbUpdatePartial = async function (id, fields) { try { return await updatePartial(id, fields); } catch (error) { report(error); throw error; } };
    global.dbInsert = async function (proposed) { try { return await insert(proposed); } catch (error) { report(error); throw error; } };
    global.dbSaveForn = async function (name) { try { return await saveSupplier(name); } catch (error) { report(error); throw error; } };
    global.dbDeleteForn = blockedWriter('Rimuovi un fornitore dal modulo Anagrafica: le sue fatture e partite collegate devono restare verificabili.', destinations.suppliers);
    global.dbCestina = blockedWriter('L’eliminazione documentale si esegue dal modulo Fatture con il controllo dei movimenti collegati.', destinations.invoices);
    global.dbRipristinaDaCestino = blockedWriter('Il ripristino del vecchio cestino non è compatibile con l’archivio documentale attuale.', destinations.invoices);
    global.dbDelete = blockedWriter('La cancellazione massiva e permanente è disabilitata in questa pagina.', destinations.invoices);
    global.dbUpdateFoto = blockedWriter('Allega il documento originale dal modulo Import Documenti.', destinations.import);
    global._applicaQuickPay = quickPay;
    const originalBulkAction = global._bulkAzione;
    if (typeof originalBulkAction === 'function') global._bulkAzione = function (action) {
      if (action === 'elimina') return unsupported('Archivia una fattura alla volta per controllare i suoi collegamenti. La cancellazione massiva non è disponibile.', destinations.invoices);
      return originalBulkAction.apply(this, arguments);
    };
    global.pprpSalva = savePartialPayment;
    global.salvaEdit = saveEdit;
    global._confermaSegnaPagateInsieme = async function () {
      const ids = global._sgIds || [], list = ids.map(findInvoice).filter(Boolean);
      const method = valueOf('_sgMetodo'), paidOn = valueOf('_sgData');
      const reference = valueOf('_sgRif').trim();
      if (typeof global.closeMo === 'function') global.closeMo();
      let result;
      if (!reference) result = await paySelection(list, () => method, () => paidOn);
      else {
        let cash = 0, pending = 0, errors = 0;
        for (const invoice of list) {
          try { const outcome = await pay(invoice.id, { metodo: method, data: paidOn, target: invoice, reference: 'Riferimento pagamento: ' + reference }); outcome.pending ? pending++ : cash++; }
          catch (error) { errors++; report(error); }
        }
        render(); notify(cash + ' pagamenti in cassa, ' + pending + ' in attesa banca' + (errors ? ', ' + errors + ' non salvati.' : '.')); result = { cash, pending, errors };
      }
      if (typeof global._uscitaSelezione === 'function') global._uscitaSelezione(); return result;
    };
    global.segnaTutteFattureFornitorePagate = function (name) {
      const list = invoices().filter(value => String(value.fornitore || '').trim().toLowerCase() === String(name || '').trim().toLowerCase() && !['pagata', 'annullata'].includes(value.stato));
      global._sgIds = list.map(value => identifier(value.id));
      if (typeof global._apriSegnaPagateInsieme === 'function') return global._apriSegnaPagateInsieme(global._sgIds);
      if (typeof global.segnaPagateInsieme === 'function') return global.segnaPagateInsieme(global._sgIds);
      return unsupported('Seleziona le fatture nel registro e usa Paga insieme per indicare metodo e data.', destinations.invoices);
    };
    global._bfPaga = async function (name, mode, selectedDate) {
      const list = typeof global._bfSelezionate === 'function' ? global._bfSelezionate(name) : [];
      const methods = typeof _bfMetodo !== 'undefined' ? _bfMetodo : global._bfMetodo || {};
      if (list.length && typeof global.confirm === 'function' && !global.confirm('Registrare ' + list.length + ' pagamenti di ' + name + ' con metodo e data selezionati? I pagamenti bancari resteranno in attesa dell’estratto conto.')) return false;
      const result = await paySelection(list, invoice => methods[name] || invoice.pagamento, invoice => mode === 'data' ? selectedDate : mode === 'scadenza' && invoice.scadenza ? invoice.scadenza : invoice.data);
      if (typeof global._bfRender === 'function') global._bfRender(); return result;
    };
    global._cfAbbina = linkFromList;
    global._confermaPagamento = confirmPayment;
    global._confermaComboPagamento = async function (index, confirmed) {
      if (!confirmed) return confirmPayment(index, false);
      const proposal = (global._pagDaConfermare || [])[index];
      if (!proposal || !proposal.mov || !Array.isArray(proposal.fatture)) return false;
      try { const result = await reconcileGroup(proposal.fatture, [proposal.mov]); global._pagDaConfermare.splice(index, 1); if (typeof global.renderRiconciliazione === 'function') global.renderRiconciliazione(); return result; }
      catch (error) { report(error); return false; }
    };
    global._applicaGruppoRiconciliazione = async function (selected, movements) {
      if (selected && selected.length === 1 && movements && movements.length === 1) {
        try { const result = await reconcile(selected[0].id, movements[0].id, selected[0]); render(); return result; } catch (error) { report(error); return false; }
      }
      try { return await reconcileGroup(selected, movements); } catch (error) { report(error); return false; }
    };
    global.salvaMovimentoBanca = blockedWriter('Associa il movimento con Riconcilia: l’estratto conto non si modifica come una riga libera.', destinations.bank);
    global.gestioneFornConfermaRinomina = function () { return unsupported('La correzione del nome di un fornitore e delle fatture collegate si esegue dall’Anagrafica.', destinations.suppliers); };
    global.gestioneFornElimina = function () { return unsupported('Gestisci l’anagrafica e i suoi collegamenti dal modulo Fornitori.', destinations.suppliers); };
    global.askDel = function (id) {
      requireWrite(); id = identifier(id);
      const invoice = findInvoice(id); if (!invoice) return false;
      const title = 'Archivia fattura';
      const description = 'Archiviare la fattura di ' + String(invoice.fornitore || '') + ' n° ' + String(invoice.numero || '') + '? Il gestionale controllerà i movimenti e le entità collegate. Il ripristino del vecchio cestino non è disponibile.';
      if (typeof global.openMo === 'function') {
        const escape = typeof bridge().escape === 'function' ? bridge().escape : value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
        global.openMo(title, escape(description), async function () { if (typeof global.closeMo === 'function') global.closeMo(); return archiveFromUi(id); }, 'user', { okLabel: 'Archivia' }); return true;
      }
      if (typeof global.confirm === 'function' && global.confirm(description)) return archiveFromUi(id);
      return false;
    };
  }
  global.CeraldiBridgeActions = Object.freeze({ install, pay, reconcile, reconcileGroup, candidates, update, updatePartial, insert, saveSupplier, remove });
})(window);
