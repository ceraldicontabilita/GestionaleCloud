/* Scadenziario nello stile Ceraldi. Legge e usa esclusivamente i writer del Gestionale. */
(function () {
  'use strict';
  const states = new WeakMap();
  const transport = window.CeraldiBridge;
  if (transport?.addApiRule) {
    transport.addApiRule(/^\/api\/fiscalita\/calendario\/\d{4}$/, ['GET']);
    transport.addApiRule(/^\/api\/fiscalita\/calendario\/(?:completa|riapri)\/[^/]+$/, ['POST']);
    transport.addApiRule(/^\/api\/scadenze\/tutte$/, ['GET']);
    transport.addApiRule(/^\/api\/fiscal\/f24-rows$/, ['GET']);
    transport.addApiRule(/^\/api\/originale\/f24\/[^/]+$/, ['GET']);
  }
  const months = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre'];
  const unavailable = 'Dato non disponibile';
  const euro = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
    ? Number(value).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' }) : unavailable;
  const date = value => /^\d{4}-\d{2}-\d{2}/.test(String(value || ''))
    ? String(value).slice(0, 10).split('-').reverse().join('/') : unavailable;
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function link(text, path) {
    const node = el('a', 'fi-act-btn', text);
    node.href = path; node.target = '_blank'; node.rel = 'noopener';
    node.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;min-height:44px;text-decoration:none;white-space:normal';
    return node;
  }
  function button(text, action, cls) {
    const node = el('button', cls || 'fi-act-btn', text);
    node.type = 'button'; node.style.minHeight = '44px';
    node.addEventListener('click', action); return node;
  }
  async function json(bridge, path, options) {
    const response = await bridge.api(path, options);
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('Risposta non valida dal Gestionale'); }
    if (!response.ok || data?.success === false) {
      const detail = data?.detail || data?.error || data?.message;
      throw new Error(typeof detail === 'string' ? detail : detail?.message || detail?.messaggio || `Lettura non riuscita (${response.status})`);
    }
    return data;
  }
  function field(label, node) {
    const wrapper = el('div', 'field'); wrapper.style.cssText = 'flex:1 1 120px;margin-bottom:0';
    const caption = el('label', '', label); caption.append(node); wrapper.append(caption); return wrapper;
  }
  function select(options, current, change) {
    const node = el('select');
    options.forEach(([value, title]) => { const option = el('option', '', title); option.value = value; node.append(option); });
    node.value = String(current); node.addEventListener('change', () => change(node.value)); return node;
  }
  function message(container, text, error) {
    const node = el('div', 'tot-card', text);
    node.style.cssText = 'font-size:13px;line-height:1.5;margin-bottom:12px;overflow-wrap:anywhere';
    if (error) { node.setAttribute('role', 'alert'); node.style.color = 'var(--red)'; }
    container.append(node); return node;
  }
  function card(label, value) {
    const node = el('div', 'tot-card'), number = el('div', 'tv', value);
    if (value === unavailable) number.style.fontSize = '15px';
    node.append(el('div', 'tl', label), number); return node;
  }
  function sourceLabel(row) {
    if (row.provenienza_stato === 'quietanza_f24') return 'Adempimento da quietanza F24';
    if (row.provenienza_stato === 'conferma_manuale') return 'Conferma manuale';
    if (row.completato === true) return 'Conferma storica da verificare';
    if (row.completato === false) return 'Da adempiere';
    return 'Stato non disponibile';
  }
  function periodMatches(row, state) {
    const day = String(row.data || row.data_scadenza || '');
    return !state.month || day.slice(5, 7) === state.month;
  }
  async function download(state, path, filename, output) {
    try {
      const response = await state.bridge.api(path);
      if (!response.ok) {
        let detail; try { detail = await response.json(); } catch (_) { /* HTTP status remains visible. */ }
        throw new Error(typeof detail?.detail === 'string' ? detail.detail : `Documento non disponibile (${response.status})`);
      }
      const blob = await response.blob();
      if (!blob.size) throw new Error('Il documento è vuoto');
      const url = URL.createObjectURL(blob); const anchor = el('a');
      anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) { message(output, error.message, true); }
  }
  function f24Detail(state, id, actions) {
    const section = el('details', 'rcard'); section.style.cssText = 'margin-top:10px;box-shadow:none;border:1px solid var(--sep)';
    const summary = el('summary', 'rcard-hd', 'Dettaglio F24 e documento'); summary.style.minHeight = '44px';
    const content = el('div'); content.style.padding = '0 12px 12px'; section.append(summary, content); actions.append(section);
    let loaded = false;
    section.addEventListener('toggle', async () => {
      if (!section.open || loaded) return;
      content.replaceChildren(); message(content, 'Caricamento F24…');
      try {
        const data = await json(state.bridge, `/api/fiscal/f24-rows?document_id=${encodeURIComponent(id)}&limit=1000`);
        if (!Array.isArray(data.items)) throw new Error('Il dettaglio F24 non contiene le righe attese');
        content.replaceChildren();
        if (!data.items.length) message(content, 'Nessuna riga F24 disponibile per questo documento.');
        data.items.forEach(row => {
          const box = el('div', 'fi-meta'); box.style.cssText = 'padding:8px 0;border-bottom:1px solid var(--sep);white-space:normal';
          box.append(el('strong', '', `Tributo ${row.tax_code || row.codice_tributo || unavailable}`),
            el('div', '', `Debito ${euro(row.debit_amount)} · Credito ${euro(row.credit_amount)}`),
            el('div', '', `Periodo ${row.reference_period || unavailable} · ${row.evidence_state || 'Stato documento non disponibile'}`));
          content.append(box);
        });
        if (Number(data.total) > data.items.length) message(content, `Mostrate ${data.items.length} di ${data.total} righe. La scheda completa contiene tutte le righe.`);
        const controls = el('div', 'fi-actions-main'); controls.style.marginTop = '10px';
        controls.append(button('Scarica documento', () => download(state, `/api/originale/f24/${encodeURIComponent(id)}?scarica=true`, `F24_${id}.pdf`, content)),
          link('Riscontro e tributi', `/fiscale/f24/${encodeURIComponent(id)}`));
        content.append(controls); loaded = true;
      } catch (error) { content.replaceChildren(); message(content, error.message, true); }
    });
  }
  async function changeCalendar(state, row, reopen, output, control) {
    const note = window.prompt(reopen ? 'Motivo della riapertura (almeno 3 caratteri)' : 'Descrivi la prova verificata per questo adempimento');
    if (note === null) return;
    if (note.trim().length < 3) { message(output, 'Inserisci una motivazione di almeno 3 caratteri.', true); return; }
    if (!window.confirm(reopen ? 'Riaprire questa scadenza? La correzione sarà registrata.' : 'Confermare manualmente la scadenza con la prova indicata? La conferma sarà registrata.')) return;
    control.disabled = true;
    try {
      const params = new URLSearchParams({ anno: String(state.year), [reopen ? 'motivo' : 'note']: note.trim() });
      await json(state.bridge, `/api/fiscalita/calendario/${reopen ? 'riapri' : 'completa'}/${encodeURIComponent(row.id)}?${params}`, { method: 'POST' });
      await load(state);
    } catch (error) { message(output, error.message, true); }
    finally { control.disabled = false; }
  }
  function calendarRow(state, row) {
    const node = el('div', 'fi');
    node.append(el('div', `fi-stripe ${row.completato ? 'fi-stripe-ok' : 'fi-stripe-parz'}`));
    const inner = el('div', 'fi-inner'), body = el('div', 'fi-body'), top = el('div', 'fi-top');
    const name = el('div', 'fi-nome', row.descrizione || unavailable); name.style.whiteSpace = 'normal';
    top.append(name); body.append(top, el('div', 'fi-meta', `${date(row.data)} · ${row.tipo || unavailable}`),
      el('div', 'fi-meta', sourceLabel(row)), el('div', 'fi-meta', 'Previsione dal calendario fiscale del Gestionale'));
    if (row.applicabilita === 'da_verificare') body.append(el('div', 'fi-meta', 'Applicabilità da verificare'));
    const codes = Array.isArray(row.codici_attesi) ? row.codici_attesi : row.codice_tributo ? [row.codice_tributo] : [];
    if (codes.length) body.append(el('div', 'fi-meta', `Codici attesi: ${codes.join(', ')}`));
    if (row.conferma_senza_f24) { const warn = el('div', 'fi-meta', 'Conferma manuale senza F24 atteso: da verificare'); warn.style.color = 'var(--red)'; body.append(warn); }
    const actions = el('div', 'fi-actions');
    (Array.isArray(row.piano_voci) ? row.piano_voci : []).forEach(voice => {
      const text = el('div', 'fi-meta', `${voice.etichetta || 'Piano tributi'} · ${voice.etichetta_stato || voice.stato || unavailable} · ${euro(voice.importo)}`);
      actions.append(text);
      const seen = new Set();
      (Array.isArray(voice.versamenti) ? voice.versamenti : []).forEach(payment => {
        if (!payment.f24_id || seen.has(String(payment.f24_id))) return;
        seen.add(String(payment.f24_id)); f24Detail(state, payment.f24_id, actions);
      });
    });
    const canWrite = state.bridge.canWrite ?? state.bridge.writable?.();
    if (canWrite && row.id && row.provenienza_stato === 'conferma_manuale') {
      const control = button('Riapri conferma manuale', () => changeCalendar(state, row, true, actions, control)); actions.append(control);
    } else if (canWrite && row.id && row.completato === false && /^\d{4}-\d{2}-\d{2}$/.test(row.data || '') && row.data <= new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })) {
      const control = button('Conferma con prova verificata', () => changeCalendar(state, row, false, actions, control)); actions.append(control);
    }
    body.append(actions); inner.append(el('div', 'fi-ic ic-b', '📅'), body); node.append(inner); return node;
  }
  function dueRow(state, row) {
    const node = el('div', 'fi'), inner = el('div', 'fi-inner'), body = el('div', 'fi-body'), top = el('div', 'fi-top');
    node.append(el('div', `fi-stripe ${row.pagata === true ? 'fi-stripe-ok' : 'fi-stripe-parz'}`));
    const name = el('div', 'fi-nome', row.descrizione || row.fornitore || unavailable); name.style.whiteSpace = 'normal';
    top.append(name); body.append(top, el('div', 'fi-meta', `${date(row.data || row.data_scadenza)} · ${row.tipo || unavailable}`),
      el('div', 'fi-meta', euro(row.importo)), el('div', 'fi-meta', row.pagata === true ? 'Pagamento registrato: verifica la prova nella scheda' : row.completata === true ? 'Scadenza completata' : 'Da verificare / adempiere'));
    if (row.note) body.append(el('div', 'fi-meta', row.note));
    const actions = el('div', 'fi-actions-main'); actions.style.marginTop = '8px';
    if (row.f24_id) f24Detail(state, row.f24_id, body);
    actions.append(link('Apri gestione scadenze', '/scadenze')); body.append(actions); inner.append(el('div', 'fi-ic ic-a', '🗓️'), body); node.append(inner); return node;
  }
  function render(state) {
    const out = state.output; out.replaceChildren();
    if (state.loading) message(out, 'Aggiornamento delle fonti del Gestionale…');
    if (state.calendarError) message(out, `Calendario non disponibile: ${state.calendarError}`, true);
    if (state.dueError) message(out, `Scadenze non disponibili: ${state.dueError}`, true);
    const calendar = state.calendar?.scadenze;
    const filteredCalendar = Array.isArray(calendar) ? calendar.filter(row => periodMatches(row, state) && (!state.status || (state.status === 'completed' ? row.completato === true : row.completato !== true))) : [];
    const grid = el('div', 'tot-grid');
    grid.append(card('Previsioni nel periodo', Array.isArray(calendar) ? filteredCalendar.length : unavailable),
      card('Confermate nel periodo', Array.isArray(calendar) ? filteredCalendar.filter(row => row.completato === true).length : unavailable));
    out.append(grid);
    const navigation = el('div', 'filtri');
    [['calendar','Calendario fiscale'],['due','Scadenze registrate']].forEach(([key, title]) => navigation.append(button(title, () => { state.tab = key; render(state); }, `fil-btn${state.tab === key ? ' active' : ''}`)));
    out.append(navigation);
    if (state.tab === 'calendar') {
      if (Array.isArray(calendar)) {
        if (!filteredCalendar.length && !state.loading) message(out, 'Nessuna previsione corrisponde ai filtri.');
        filteredCalendar.slice().sort((a,b) => String(a.data || '').localeCompare(String(b.data || ''))).forEach(row => out.append(calendarRow(state, row)));
      }
    } else if (Array.isArray(state.due)) {
      const filtered = state.due.filter(row => periodMatches(row, state));
      message(out, `Caricate ${state.due.length} di ${state.dueTotal === null ? unavailable : state.dueTotal} scadenze. ${state.month ? 'La lista è filtrata per mese.' : ''}`);
      if (!filtered.length && !state.loading) message(out, 'Nessuna scadenza registrata corrisponde ai filtri.');
      filtered.forEach(row => out.append(dueRow(state, row)));
      if (state.hasMore) out.append(button('Carica altre scadenze', () => loadDue(state, true), 'btn btn-s'));
    }
    if (state.updated) message(out, `Ultima lettura ${state.updated.toLocaleTimeString('it-IT')} · aggiornamento automatico ogni minuto mentre questa pagina è aperta.`);
  }
  async function fetchDue(state, offset) {
    const params = new URLSearchParams({ anno: String(state.year), include_passate: 'true', limit: '100', offset: String(offset) });
    const data = await json(state.bridge, `/api/scadenze/tutte?${params}`);
    if (!Array.isArray(data.scadenze) || data.totale === null || data.totale === undefined || !Number.isInteger(Number(data.totale)) || Number(data.totale) < 0) throw new Error('Risposta scadenze incompleta');
    return data;
  }
  async function loadDue(state, append) {
    if (state.loading) return;
    const generation = state.generation; state.loading = true; state.dueError = ''; render(state);
    try {
      const offset = append ? state.due.length : 0; const data = await fetchDue(state, offset);
      if (generation !== state.generation) return;
      state.due = append ? state.due.concat(data.scadenze) : data.scadenze;
      state.dueTotal = Number(data.totale); state.hasMore = state.due.length < state.dueTotal && data.scadenze.length > 0; state.updated = new Date();
    } catch (error) { if (generation === state.generation) state.dueError = error.message; }
    finally { if (generation === state.generation) { state.loading = false; render(state); } }
  }
  async function load(state) {
    const generation = ++state.generation;
    state.loading = true; state.calendar = null; state.due = null; state.dueTotal = null;
    state.calendarError = ''; state.dueError = ''; state.hasMore = false; render(state);
    const year = state.year;
    const results = await Promise.allSettled([json(state.bridge, `/api/fiscalita/calendario/${encodeURIComponent(year)}`), fetchDue(state, 0)]);
    if (generation !== state.generation) return;
    const [calendar, due] = results;
    if (calendar.status === 'fulfilled' && Array.isArray(calendar.value.scadenze)) state.calendar = calendar.value;
    else state.calendarError = calendar.status === 'rejected' ? calendar.reason.message : 'Risposta calendario incompleta';
    if (due.status === 'fulfilled') {
      state.due = due.value.scadenze; state.dueTotal = Number(due.value.totale);
      state.hasMore = state.due.length < state.dueTotal && state.due.length > 0;
    } else state.dueError = due.reason.message;
    state.loading = false; state.updated = new Date(); render(state);
  }
  function mount(root, bridge) {
    const previous = states.get(root);
    if (previous?.output?.isConnected) return;
    if (previous) { previous.generation += 1; clearInterval(previous.interval); }
    const state = { root, bridge, year: new Date().getFullYear(), month: '', status: '', tab: 'calendar', generation: 0, calendar: null, due: null, dueTotal: null };
    states.set(root, state); root.replaceChildren();
    const heading = el('div', 'tot-card'); heading.append(el('strong', '', 'Scadenziario fiscale'), el('div', 'fi-meta', 'Calendario, F24 e scadenze collegati alle fonti del Gestionale.'));
    const controls = el('div'); controls.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;align-items:end';
    const year = el('input'); year.type = 'number'; year.min = '2000'; year.max = '2100'; year.value = state.year;
    year.addEventListener('change', () => { const value = Number(year.value); if (!Number.isInteger(value) || value < 2000 || value > 2100) { year.value = state.year; return; } state.year = value; load(state); });
    controls.append(field('Anno', year), field('Mese', select([['','Tutto l’anno'], ...months.map((name,index) => [String(index + 1).padStart(2,'0'),name])], '', value => { state.month = value; render(state); })),
      field('Calendario', select([['','Tutti gli stati'],['open','Da adempiere'],['completed','Confermati']], '', value => { state.status = value; render(state); })),
      button('Aggiorna', () => load(state), 'fil-btn'));
    heading.append(controls); root.append(heading);
    const shortcuts = el('div', 'fi-actions-main'); shortcuts.style.cssText = 'margin-bottom:14px;flex-wrap:wrap';
    shortcuts.append(link('Piano tributi e F24', '/situazione-fiscale/piano'), link('Gestione scadenze', '/scadenze')); root.append(shortcuts);
    state.output = el('div'); state.output.setAttribute('aria-live', 'polite'); root.append(state.output);
    render(state);
    const interval = setInterval(() => {
      if (!state.output.isConnected) { clearInterval(interval); return; }
      if (!document.hidden && root.getClientRects().length && !state.loading) load(state);
    }, 60000);
    state.interval = interval;
  }
  window.CeraldiGestionaleModules.register({ id: 'fiscale_gc', title: 'Scadenziario fiscale', icon: '📅', mount,
    onOpen(root, bridge) { mount(root, bridge); const state = states.get(root); state.bridge = bridge; return load(state); } });
})();
