/* Automazioni Ceraldi: gli stessi motori del Gestionale, nessun writer nel browser. */
(function (global) {
  'use strict';

  class AutomationError extends Error {
    constructor(status, message, details) {
      super(message); this.status = status; this.code = 'CERALDI_AUTOMAZIONE';
      this.details = details || null;
    }
  }

  const aliases = {
    autoEstraiPrezzi: 'prezzi_xml',
    _eseguiSyncIncrementale: 'sincronizzazione',
    avviaSyncAutomatico: 'sincronizzazione',
    _avviaRealtimeSync: 'sincronizzazione',
    _avviaPollingBg: 'sincronizzazione',
    caricaChiusuraGiorno: 'corrispettivi_pos',
    renderRiconciliazione: 'corrispettivi_pos',
    ricalcolaIvaFattureXml: 'iva_xml',
    avviaRicalcoloIva: 'iva_xml',
    _ncAutoAggancia: 'note_credito',
  };

  const pending = {
    _purgaCestinoScaduto: {
      message: 'La cancellazione definitiva automatica del vecchio Cestino non è applicabile ai fatti amministrativi del Gestionale.',
      plan: 'Usare archivio, storno o quarantena con audit e i comandi canonici di ripristino.',
      destination: '/admin',
    },
  };

  const definitions = {
    prezzi_xml: {
      title: 'Prezzi da fatture XML', icon: '🏷️',
      description: 'Le righe XML alimentano Lotti, listini e ricette tramite il ponte canonico all’import e il job periodico. Riavvia lo stesso ponte per gli originali già acquisiti.',
      status: '/lotti/api/gestionale-fatture/stato',
      preview: '/lotti/api/gestionale-fatture/sync?anteprima=true',
      execute: '/lotti/api/gestionale-fatture/sync?anteprima=false',
      logs: '/lotti/api/scheduler/logs?limit=10&job=sync_gestionale_fatture',
      destination: '/lotti/#listino',
      button: 'Sincronizza XML e prezzi',
    },
    documenti: {
      title: 'Elaborazione documenti', icon: '📄',
      description: 'Rilettura degli originali già acquisiti con i parser del Gestionale. La simulazione espone l’esito; l’esecuzione salva la nuova lettura accanto all’originale, senza creare fatture o pagamenti.',
      status: '/api/batch-reprocess/status', preview: '/api/batch-reprocess/preview',
      simulate: '/api/batch-reprocess/start?dry_run=true',
      execute: '/api/batch-reprocess/start?dry_run=false',
      destination: '/admin/elaborazioni', button: 'Rielabora documenti',
    },
    iva_xml: {
      title: 'Competenza IVA', icon: '🧾',
      description: 'Aliquote e riepiloghi XML sono acquisiti all’import. Questo comando ricalcola la competenza fiscale con il motore IVA e conserva l’ultimo report; non stima aliquote né riscrive gli importi XML.',
      status: '/api/iva/ricalcola-attribuzione/ultimo',
      execute: '/api/iva/ricalcola-attribuzione',
      destination: '/iva', button: 'Ricalcola competenza IVA',
    },
    corrispettivi_pos: {
      title: 'Corrispettivi, POS e banca', icon: '💳',
      description: 'Legge il confronto canonico fra corrispettivi, chiusure terminale e accrediti. Ogni prova rimane distinta; le differenze si verificano prima della riconciliazione.',
      status: '/api/pos-corrispettivi/alert-oggi',
      check: '/api/pos-corrispettivi/controllo-due-fasi',
      destination: '/riconciliazione/coerenza-pos', button: 'Controlla periodo',
    },
    sincronizzazione: {
      title: 'Aggiornamento dati condivisi', icon: '🔄',
      description: 'Rilegge i dati del Gestionale. I collegamenti e le scritture restano nei motori server: aprire la pagina non genera una seconda catena di elaborazione.',
      status: '/api/sync/stato-sincronizzazione',
      destination: '/riconciliazione/banca',
    },
    produzioni: {
      title: 'Automatismi di produzione', icon: '⚙️',
      description: 'Stato dei job operativi e ultimi log di Lotti. Controlla gli errori della pipeline, gli orari e il risultato salvato prima di rilanciare una produzione.',
      status: '/lotti/api/scheduler/stato',
      logs: '/lotti/api/scheduler/logs?limit=15',
      destination: '/lotti/',
    },
    note_credito: {
      title: 'Note di credito da XML', icon: '🔗',
      description: 'Il motore di import collega una nota solo a una fattura certa dello stesso fornitore, anche quando la nota arriva prima. Rispetta gli sganci manuali e le fatture già pagate. Qui verifichi le relazioni delle ultime 100 fatture.',
      status: '/api/invoices?limit=100&skip=0',
      destination: '/fatture',
    },
  };

  let attachedBridge = null;
  const inFlight = new Map();
  const writerInFlight = new Set();
  const registeredBridges = new WeakSet();
  function registerRules(bridge) {
    if (!bridge.addApiRule || registeredBridges.has(bridge)) return;
    const routes = [
      [/^\/lotti\/api\/gestionale-fatture\/stato$/, ['GET']],
      [/^\/lotti\/api\/gestionale-fatture\/sync$/, ['POST']],
      [/^\/lotti\/api\/scheduler\/(stato|logs)$/, ['GET']],
      [/^\/api\/batch-reprocess\/(status|preview)$/, ['GET']],
      [/^\/api\/batch-reprocess\/start$/, ['POST']],
      [/^\/api\/iva\/ricalcola-attribuzione\/ultimo$/, ['GET']],
      [/^\/api\/iva\/ricalcola-attribuzione$/, ['POST']],
      [/^\/api\/pos-corrispettivi\/(alert-oggi|controllo-due-fasi)$/, ['GET']],
      [/^\/api\/sync\/stato-sincronizzazione$/, ['GET']],
      [/^\/api\/invoices$/, ['GET']],
    ];
    routes.forEach(([path, methods]) => bridge.addApiRule(path, methods));
    registeredBridges.add(bridge);
  }

  function getBridge(explicit) {
    const bridge = explicit || attachedBridge || global.CeraldiBridge;
    if (!bridge || typeof bridge.api !== 'function') throw new AutomationError(503, 'Collegamento al Gestionale non disponibile.');
    registerRules(bridge);
    return bridge;
  }
  function canWrite(bridge) {
    return typeof bridge.canWrite === 'function' ? bridge.canWrite() === true : bridge.canWrite === true;
  }
  async function read(bridge, path, method) {
    const options = { method: method || 'GET', cache: 'no-store' };
    const response = await bridge.api(path, options);
    let data;
    try { data = await response.json(); }
    catch (_) { throw new AutomationError(response.ok ? 502 : response.status, 'Risposta non leggibile dal Gestionale.'); }
    if (!response.ok) {
      const msg = data.detail || data.message || data.error || 'Operazione non riuscita';
      throw new AutomationError(response.status, typeof msg === 'string' ? msg : JSON.stringify(msg), data);
    }
    return data;
  }
  function reportHasError(value, depth) {
    if (!value || typeof value !== 'object' || (depth || 0) > 3) return false;
    return value.ok === false || value.success === false || Boolean(value.error) ||
      Number(value.totale_errori) > 0 ||
      (Array.isArray(value.errori) && value.errori.length > 0) ||
      (Array.isArray(value.errors) && value.errors.length > 0) ||
      ['errore', 'failed', 'parziale'].includes(String(value.esito || value.stato || '').toLowerCase()) ||
      ['result', 'ultimo_esito', 'ultimo'].some(key => reportHasError(value[key], (depth || 0) + 1));
  }
  function period(args) {
    const query = new URLSearchParams();
    if (args.anno !== undefined && args.anno !== '') {
      const year = Number(args.anno);
      if (!Number.isInteger(year) || year < 2000 || year > 2100) throw new AutomationError(400, 'Anno non valido.');
      query.set('anno', String(year));
    }
    for (const name of ['data_da', 'data_a']) {
      if (args[name] === undefined || args[name] === '') continue;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(args[name]))) throw new AutomationError(400, 'Data non valida.');
      query.set(name, String(args[name]));
    }
    if (query.has('anno') && (query.has('data_da') || query.has('data_a'))) throw new AutomationError(400, 'Scegli l’anno oppure l’intervallo di date.');
    return query.toString() ? '?' + query.toString() : '';
  }

  async function runAutomation(name, args, explicitBridge) {
    args = args || {};
    if (pending[name]) throw new AutomationError(501, pending[name].message, pending[name]);
    const id = aliases[name] || name;
    const definition = definitions[id];
    if (!definition) throw new AutomationError(501, 'Automatismo «' + String(name) + '» non ancora collegato al motore canonico.', {
      plan: 'Verificare parser, writer e prova esistenti nel Gestionale prima di collegare questo automatismo.',
    });
    const action = args.action || 'status';
    if (!['status', 'preview', 'simulate', 'execute', 'check'].includes(action)) throw new AutomationError(400, 'Azione dell’automatismo non valida.');
    const bridge = getBridge(explicitBridge);
    let path = definition[action];
    if (action === 'check') path = definition.check && definition.check + period(args);
    if (id === 'iva_xml' && action === 'execute' && args.anno !== undefined) path += period({ anno: args.anno });
    if (!path) throw new AutomationError(501, 'Il motore «' + definition.title + '» non espone questa azione.', {
      destination: definition.destination, plan: definition.description,
    });
    const mutatingRequest = ['execute', 'simulate'].includes(action) || (action === 'preview' && path.includes('/sync?'));
    if (mutatingRequest && !canWrite(bridge)) throw new AutomationError(403, 'Operazione riservata al titolare autenticato.');
    const key = id + ':' + action + ':' + path;
    if (inFlight.has(key)) return inFlight.get(key);
    if (mutatingRequest && writerInFlight.has(id)) throw new AutomationError(409, 'Un comando per questo motore è già in corso. Attendi lo stato prima di riprovare.');
    if (mutatingRequest) writerInFlight.add(id);
    const task = (async function () {
      let result = await read(bridge, path, mutatingRequest ? 'POST' : 'GET');
      if (id === 'note_credito') {
        if (!Array.isArray(result)) throw new AutomationError(502, 'Elenco fatture non valido.');
        result = {
          fonte: 'Relazioni persistenti nelle fatture del Gestionale',
          esecuzione: 'Aggancio gestito dal motore di import, nessuna scrittura eseguita dalla pagina',
          scope: 'Ultime 100 fatture; non è una scansione completa dell’archivio',
          fatture_lette: result.length,
          note_credito: result.filter(invoice => /^(TD04|TD08)$/i.test(String(invoice.tipo_documento || ''))).map(invoice => ({
            id: invoice.id, numero: invoice.invoice_number || null,
            fattura_collegata_id: invoice.fattura_collegata_id || null,
            riferimenti_xml: invoice.dati_fatture_collegate || [],
          })),
        };
      }
      const output = {
        automation: id, action: action, managed_by: 'GestionaleCloud',
        requested_at: new Date().toISOString(), result: result,
        state: reportHasError(result) ? 'da_verificare' : (action === 'status' ? 'stato_letto' : action === 'check' ? 'controllo_letto' : 'risposta_ricevuta'),
      };
      if (mutatingRequest) {
        try {
          output.persisted_state = await read(bridge, definition.after || definition.status);
          output.state_verified_at = new Date().toISOString();
          if (reportHasError(output.persisted_state)) output.state = 'da_verificare';
        } catch (error) {
          output.state = 'verifica_esito_non_disponibile';
          output.verification_error = { status: error.status || 503, message: error.message };
        }
      }
      return output;
    })();
    inFlight.set(key, task);
    try { return await task; } finally { inFlight.delete(key); if (mutatingRequest) writerInFlight.delete(id); }
  }

  function node(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined) element.textContent = value;
    return element;
  }
  function dateFromReport(output) {
    const report = output.persisted_state || output.result || {};
    const last = report.ultimo || report.ultimo_esito || report;
    return report.updated_at || report.ultimo_sync || report.started_at || last.eseguito_il || last.timestamp || null;
  }
  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('it-IT');
  }
  function detail(card, title, value) {
    const details = node('details', 'gc-auto-details');
    details.append(node('summary', '', title));
    const pre = node('pre', '', JSON.stringify(value, null, 2));
    pre.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font:11px ui-monospace,monospace;max-height:320px;overflow:auto;color:var(--ink);';
    details.append(pre); card.append(details); return details;
  }

  function mount(root, bridge) {
    attachedBridge = bridge;
    registerRules(bridge);
    bridge.runAutomation = function (name, args) { return runAutomation(name, args, bridge); };
    root.replaceChildren();
    const heading = node('div', 'section-hdr');
    heading.append(node('h2', 'section-title', 'Automazioni'));
    root.append(heading);
    const intro = node('p', '', 'Gli automatismi lavorano nel Gestionale anche con questa pagina chiusa. Qui leggi lo stato reale, verifichi gli errori e richiami lo stesso motore.');
    intro.style.cssText = 'color:var(--ink3);font-size:13px;line-height:1.5;margin:0 0 16px;';
    root.append(intro);
    const controls = node('div', 'gc-auto-controls');
    controls.style.cssText = 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px;';
    const refresh = node('button', 'gc-auto-button', 'Aggiorna stato');
    refresh.type = 'button'; controls.append(refresh);
    const yearLabel = node('label', '', 'Anno IVA / POS ');
    const year = node('input'); year.type = 'number'; year.min = '2000'; year.max = '2100';
    year.value = new Date().getFullYear(); year.setAttribute('aria-label', 'Anno IVA e controllo POS');
    year.style.cssText = 'width:85px;border:1px solid var(--sep);border-radius:8px;padding:7px;background:var(--surface);color:var(--ink);';
    yearLabel.append(year); controls.append(yearLabel); root.append(controls);
    const grid = node('div', 'gc-auto-grid');
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:12px;';
    root.append(grid);
    const cards = new Map();

    for (const [id, definition] of Object.entries(definitions)) {
      const card = node('section', 'rcard gc-auto-card');
      card.style.cssText = 'padding:16px;border:1px solid var(--sep);border-radius:16px;background:var(--surface);';
      card.append(node('div', 'rcard-title', definition.icon + ' ' + definition.title));
      const description = node('p', 'rcard-sub', definition.description);
      description.style.cssText = 'font-size:12px;line-height:1.5;margin:8px 0;color:var(--ink3);'; card.append(description);
      const state = node('p', '', 'Stato da leggere'); state.style.cssText = 'font-size:12px;color:var(--ink);'; card.append(state);
      const actions = node('div'); actions.style.cssText = 'display:flex;gap:7px;flex-wrap:wrap;'; card.append(actions);
      const record = { card, state, actions, details: null, logs: null };
      cards.set(id, record);
      function addAction(label, action) {
        const button = node('button', 'gc-auto-button', label); button.type = 'button';
        button.style.cssText = 'border:1px solid var(--sep);border-radius:10px;padding:8px 10px;background:var(--surface2,var(--surface));color:var(--ink);cursor:pointer;font:inherit;font-size:12px;';
        if (['execute', 'simulate'].includes(action) || (action === 'preview' && definition.preview.includes('/sync?'))) button.disabled = !canWrite(bridge);
        button.addEventListener('click', async function () {
          button.disabled = true; state.textContent = 'Richiesta al motore in corso…';
          try { show(id, await runAutomation(id, { action, anno: year.value }, bridge)); }
          catch (error) { showError(id, error); }
          finally { button.disabled = ['execute', 'simulate'].includes(action) ? !canWrite(bridge) : false; }
        });
        actions.append(button);
      }
      if (definition.preview) addAction('Anteprima', 'preview');
      if (definition.simulate) addAction('Simula', 'simulate');
      if (definition.execute) addAction(definition.button, 'execute');
      if (definition.check) addAction(definition.button, 'check');
      const link = node('a', '', 'Apri modulo'); link.href = definition.destination;
      link.style.cssText = 'font-size:12px;color:var(--blue);padding:8px 0;'; actions.append(link);
      grid.append(card);
    }

    function show(id, output) {
      const record = cards.get(id);
      const date = dateFromReport(output);
      let label = output.action === 'status' ? 'Stato letto dal Gestionale' : output.action === 'preview' ? 'Anteprima letta' : output.action === 'check' ? 'Controllo letto dal Gestionale' : 'Richiesta ricevuta dal motore';
      if (output.state === 'da_verificare') label = 'Esito con anomalie: verifica il risultato';
      if (output.state === 'verifica_esito_non_disponibile') label = 'Richiesta inviata; rilettura dell’esito non disponibile';
      const current = output.persisted_state || output.result || {};
      if (current.running || current.in_progress) label += ' · In elaborazione';
      if (current.ultimo === null && output.action === 'status') label += ' · Nessuna esecuzione registrata';
      record.state.textContent = label + (date ? ' · Ultimo dato: ' + formatDate(date) : ' · Data ultimo esito non disponibile');
      if (record.details) record.details.remove();
      record.details = detail(record.card, 'Risultato e stato del motore', output);
    }
    function showError(id, error) {
      const record = cards.get(id);
      record.state.textContent = 'Errore ' + (error.status || '') + ': ' + error.message;
      if (record.details) record.details.remove();
      record.details = error.details ? detail(record.card, 'Dettaglio dell’errore', error.details) : null;
    }
    async function refreshAll() {
      refresh.disabled = true;
      try {
        await Promise.allSettled(Object.keys(definitions).map(async function (id) {
          const record = cards.get(id); record.state.textContent = 'Lettura stato…';
          try { show(id, await runAutomation(id, { action: 'status' }, bridge)); }
          catch (error) { showError(id, error); }
          if (definitions[id].logs) {
            if (record.logs) record.logs.remove();
            try { record.logs = detail(record.card, 'Ultimi log del motore', await read(bridge, definitions[id].logs)); }
            catch (error) { record.logs = detail(record.card, 'Log non disponibili', { status: error.status, message: error.message }); }
          }
        }));
      } finally { refresh.disabled = false; }
    }
    const note = node('section', 'rcard');
    note.style.cssText = 'margin-top:14px;padding:16px;border:1px solid var(--sep);border-radius:16px;background:var(--surface);';
    note.append(node('div', 'rcard-title', 'Collegamenti da completare'));
    for (const item of Object.values(pending)) {
      const p = node('p', 'rcard-sub', item.message + ' ' + item.plan);
      p.style.cssText = 'font-size:12px;line-height:1.5;color:var(--ink3);'; note.append(p);
    }
    root.append(note);
    refresh.addEventListener('click', refreshAll);
    root._ceraldiAutomationRefresh = refreshAll;
  }

  global.CeraldiAutomations = Object.freeze({ runAutomation, definitions, aliases });
  if (global.CeraldiBridge) global.CeraldiBridge.runAutomation = function (name, args) { return runAutomation(name, args); };
  global.CeraldiGestionaleModules.register({
    id: 'automazioni_gc', title: 'Automazioni', icon: '⚙️', mount,
    onOpen: function (root, bridge) {
      attachedBridge = bridge;
      if (!root._ceraldiAutomationRefresh || !root.querySelector('.gc-auto-grid')) mount(root, bridge);
      return root._ceraldiAutomationRefresh ? root._ceraldiAutomationRefresh() : undefined;
    },
  });
})(window);
