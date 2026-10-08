/* Archivio paghe HR canonico: stessa grafica Ceraldi, nessuna anagrafica o contabilità parallela. */
(function () {
  'use strict';
  const states = new WeakMap();
  const transport = window.CeraldiBridge;
  if (transport?.addApiRule) {
    transport.addApiRule(/^\/hr\/api\/dipendenti$/, ['GET']);
    transport.addApiRule(/^\/hr\/api\/dipendenti-cloud\/paghe\/associazioni-bonifici(?:\/export-excel)?$/, ['GET']);
    transport.addApiRule(/^\/hr\/api\/dipendenti-cloud\/paghe\/pagamento-esito\/[^/]+\/pdf$/, ['GET']);
    transport.addApiRule(/^\/hr\/api\/dipendenti-cloud\/paghe\/conferma-associazione$/, ['POST']);
    transport.addApiRule(/^\/hr\/api\/cedolini\/[^/]+\/download$/, ['GET']);
    transport.addApiRule(/^\/hr\/api\/posizione-dipendente\/dipendente\/[^/]+$/, ['GET']);
  }
  const API = '/hr/api/dipendenti-cloud/paghe';
  const unavailable = 'Dato non disponibile';
  const months = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre','Tredicesima','Quattordicesima'];
  const statuses = { pagato: 'Pagamento confermato', parziale: 'Parzialmente riconciliato', da_verificare: 'Da verificare', da_pagare: 'Da pagare', in_attesa_busta: 'In attesa della busta', in_attesa_pagamento: 'In attesa del pagamento' };
  const sources = { banca: 'Movimenti bancari', documento_da_verificare: 'Documenti: manca riscontro bancario', prima_nota: 'Prima nota', manuale: 'Inserimento manuale' };
  const amount = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const euro = value => amount(value) === null ? unavailable : amount(value).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  const date = value => /^\d{4}-\d{2}-\d{2}/.test(String(value || '')) ? String(value).slice(0,10).split('-').reverse().join('/') : unavailable;
  function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = String(text); return node; }
  function button(text, action, cls) { const node = el('button', cls || 'fi-act-btn', text); node.type = 'button'; node.style.minHeight = '44px'; node.addEventListener('click', action); return node; }
  function link(text, path) { const node = el('a', 'fi-act-btn', text); node.href = path; node.target = '_blank'; node.rel = 'noopener'; node.style.cssText = 'display:inline-flex;min-height:44px;align-items:center;justify-content:center;text-decoration:none;white-space:normal'; return node; }
  function message(container, text, error) { const node = el('div', 'tot-card', text); node.style.cssText = 'font-size:13px;line-height:1.5;margin-bottom:12px;overflow-wrap:anywhere'; if (error) { node.setAttribute('role','alert'); node.style.color = 'var(--red)'; } container.append(node); return node; }
  function field(label, input) { const node = el('div', 'field'); node.style.cssText = 'flex:1 1 130px;margin-bottom:0'; const caption = el('label', '', label); caption.append(input); node.append(caption); return node; }
  function select(options, current, change) { const node = el('select'); options.forEach(([value, title]) => { const option = el('option', '', title); option.value = value; node.append(option); }); node.value = String(current); node.addEventListener('change', () => change(node.value)); return node; }
  async function json(state, path, options) {
    const response = await state.bridge.api(path, options); let data;
    try { data = await response.json(); } catch (_) { throw new Error('Risposta non valida dal Gestionale'); }
    if (!response.ok || data?.success === false) { const detail = data?.detail || data?.error || data?.message; throw new Error(typeof detail === 'string' ? detail : detail?.message || detail?.messaggio || `Lettura non riuscita (${response.status})`); }
    return data;
  }
  async function download(state, path, filename, output) {
    try {
      const response = await state.bridge.api(path);
      if (!response.ok) { let data; try { data = await response.json(); } catch (_) { /* Keep the HTTP error visible. */ } throw new Error(typeof data?.detail === 'string' ? data.detail : `Documento non disponibile (${response.status})`); }
      const blob = await response.blob(); if (!blob.size) throw new Error('Il documento è vuoto');
      const url = URL.createObjectURL(blob), anchor = el('a'); anchor.href = url; anchor.download = filename;
      document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) { message(output, error.message, true); }
  }
  function sum(rows, getter) {
    if (!rows.length) return null;
    const values = rows.map(getter).map(amount);
    return values.some(value => value === null) ? null : values.reduce((total,value) => total + Math.round(value * 100), 0) / 100;
  }
  function stat(label, value) { const node = el('div', 'tot-card'); const number = el('div','tv',value); if (value === unavailable) number.style.fontSize = '15px'; node.append(el('div','tl',label),number); return node; }
  function busta(row) { return row.stato === 'in_attesa_busta' ? null : row.busta; }
  function documented(row) {
    if (!Array.isArray(row.bonifici)) return null;
    const docs = row.bonifici.filter(value => value.pdf_key);
    return docs.length ? sum(docs, value => value.importo) : null;
  }
  function bank(row) { return row.fonte === 'banca' ? row.bonifico : null; }
  function filtered(state) { return state.data.righe.filter(row => (!state.employee || String(row.dipendente_id) === state.employee) && (!state.status || row.stato === state.status) && (!state.search || String(row.dipendente || '').toLocaleLowerCase('it-IT').includes(state.search.toLocaleLowerCase('it-IT')))); }
  async function confirmAssociation(state, row, output, control, revoke) {
    if (!window.confirm(revoke ? 'Annullare la conferma manuale di questa associazione?' : 'Confermare il collegamento dei movimenti bancari a questa busta?')) return;
    control.disabled = true;
    try {
      await json(state, `${API}/conferma-associazione`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dipendente_id: row.dipendente_id, anno: row.anno, mese: row.mese, riconciliato: !revoke }) });
      await load(state);
    } catch (error) { message(output, error.message, true); }
    finally { control.disabled = false; }
  }
  function payrollRow(state, row) {
    const node = el('div','fi'), inner = el('div','fi-inner'), body = el('div','fi-body'), top = el('div','fi-top');
    node.append(el('div', `fi-stripe ${row.stato === 'pagato' && row.riconciliato === true ? 'fi-stripe-ok' : row.stato === 'da_pagare' ? 'fi-stripe-da' : 'fi-stripe-parz'}`));
    const name = el('div','fi-nome',row.dipendente || unavailable); name.style.whiteSpace = 'normal'; top.append(name);
    body.append(top, el('div','fi-meta',`${months[Number(row.mese) - 1] || 'Periodo non disponibile'} ${row.anno || ''}`),
      el('div','fi-meta',`${statuses[row.stato] || 'Stato non disponibile'} · ${sources[row.fonte] || 'Fonte del pagamento non disponibile'}`));
    const amounts = el('div','tot-grid'); amounts.style.cssText = 'gap:7px;margin:10px 0';
    [['Dovuto in busta',busta(row)],['Bonifici documentati',documented(row)],['Riscontro in banca',bank(row)],['Residuo del registro',row.saldo]].forEach(([label,value]) => {
      const item = stat(label,euro(value)); item.style.cssText = 'padding:9px;box-shadow:none;background:var(--surface2)'; item.querySelector('.tv').style.fontSize = '14px'; amounts.append(item);
    }); body.append(amounts);
    body.append(el('div','fi-meta',`Acconti registrati: ${euro(row.acconti)} · Erogato nel registro: ${euro(row.erogato)}`));
    if (row.fonte !== 'banca' && amount(row.bonifico) !== null && amount(row.bonifico) > 0) body.append(el('div','fi-meta','La disposizione o il pagamento registrato richiedono il riscontro sul conto.'));
    if (row.acconti_non_ammessi) { const warn = el('div','fi-meta',`${row.acconti_non_ammessi} acconti esclusi dal saldo: verificare nella posizione dipendente`); warn.style.color = 'var(--red)'; body.append(warn); }
    if (row.busta_manuale) body.append(el('div','fi-meta',`Busta corretta manualmente${row.busta_nota ? `: ${row.busta_nota}` : ''}`));
    const actions = el('div','fi-actions-main'); actions.style.cssText = 'margin-top:10px;flex-wrap:wrap';
    if (row.cedolino_id && row.cedolino_pdf) actions.append(button('Scarica cedolino PDF', () => download(state, `/hr/api/cedolini/${encodeURIComponent(row.cedolino_id)}/download`, `Cedolino_${row.anno}_${row.mese}.pdf`, body)));
    const canWrite = state.bridge.canWrite ?? state.bridge.writable?.();
    if (canWrite && row.fonte === 'banca' && Array.isArray(row.bonifici) && row.bonifici.length && !row.riconciliato) {
      const control = button('Conferma riscontro bancario', () => confirmAssociation(state,row,body,control,false)); actions.append(control);
    }
    if (canWrite && row.riconciliato === true && row.riconciliato_auto === false) {
      const control = button('Annulla conferma manuale', () => confirmAssociation(state,row,body,control,true)); actions.append(control);
    }
    body.append(actions);
    const detail = el('details','rcard'); detail.style.cssText = 'margin:10px 0 0;box-shadow:none;border:1px solid var(--sep)';
    const heading = el('summary','rcard-hd','Bonifici e acconti'); heading.style.minHeight = '44px'; const content = el('div'); content.style.padding = '0 12px 12px';
    const transfers = Array.isArray(row.bonifici) ? row.bonifici : null;
    if (transfers === null) message(content,'Dettaglio bonifici non disponibile.',true);
    else if (!transfers.length) content.append(el('div','fi-meta','Nessun bonifico collegato in questo periodo.'));
    else transfers.forEach(transfer => {
      const item = el('div','fi-meta'); item.style.cssText = 'padding:8px 0;border-bottom:1px solid var(--sep);overflow-wrap:anywhere';
      item.append(el('strong','',`${date(transfer.data)} · ${euro(transfer.importo)}`), el('div','',`Beneficiario: ${transfer.beneficiario || unavailable}`),
        el('div','',`Causale: ${transfer.causale || unavailable}`), el('div','',`CRO/riferimento: ${transfer.riferimento || unavailable}`));
      if (transfer.modificato) item.append(el('div','','Importo o periodo modificati manualmente'));
      if (transfer.pdf_key) item.append(button('Scarica PDF bonifico', () => download(state, `${API}/pagamento-esito/${encodeURIComponent(transfer.pdf_key)}/pdf`, `Bonifico_${row.anno}_${row.mese}.pdf`, content)));
      content.append(item);
    });
    if (Array.isArray(row.acconti_dettaglio) && row.acconti_dettaglio.length) {
      content.append(el('strong','fi-meta','Acconti registrati (distinti dal saldo)'));
      row.acconti_dettaglio.forEach(value => content.append(el('div','fi-meta',`${date(value.data)} · ${euro(value.importo)}`)));
    }
    detail.append(heading,content); body.append(detail); inner.append(el('div','fi-ic ic-k','👤'),body); node.append(inner); return node;
  }
  async function employeePosition(state, id, container, generation) {
    container.replaceChildren(); message(container,'Caricamento della posizione dipendente…');
    try {
      const data = await json(state, `/hr/api/posizione-dipendente/dipendente/${encodeURIComponent(id)}?anno=${state.year}`);
      if (generation !== state.generation || id !== state.employee) return;
      if (!Array.isArray(data.righe)) throw new Error('Posizione dipendente incompleta');
      container.replaceChildren(); const grid = el('div','tot-grid');
      grid.append(stat('Saldo iniziale',euro(data.apertura)),stat('Saldo finale',euro(data.chiusura))); container.append(grid);
      (Array.isArray(data.avvisi) ? data.avvisi : []).forEach(value => message(container,value));
      data.righe.forEach(row => {
        const box = el('div','fi-meta'); box.style.cssText = 'padding:8px 0;border-bottom:1px solid var(--sep);line-height:1.5';
        box.append(el('strong','',`${date(row.data)} · ${row.descrizione || unavailable}`),
          el('div','',`Dare ${euro(row.dare)} · Avere ${euro(row.avere)} · Saldo ${euro(row.saldo)}`)); container.append(box);
      });
    } catch (error) { if (generation === state.generation) { container.replaceChildren(); message(container,error.message,true); } }
  }
  function render(state) {
    const output = state.output; output.replaceChildren();
    if (state.loading) message(output,'Aggiornamento dell’archivio paghe HR…');
    if (state.error) message(output,`Paghe non disponibili: ${state.error}`,true);
    if (state.employeesError) message(output,`Anagrafica HR non disponibile: ${state.employeesError}`,true);
    if (!state.data) return;
    const rows = filtered(state), grid = el('div','tot-grid');
    grid.append(stat('Buste nel periodo',rows.length),stat('Dovuto',euro(sum(rows,busta))),
      stat('Residuo del registro',euro(sum(rows,row => row.saldo))),stat('Da verificare',rows.filter(row => row.stato === 'da_verificare').length)); output.append(grid);
    message(output,'Dovuto, pagamenti, acconti e residuo provengono dal registro HR. Il documento di bonifico e il riscontro bancario sono mostrati separatamente.');
    if (!rows.length && !state.loading) message(output,'Nessuna busta o pagamento corrisponde ai filtri.');
    rows.slice(0,state.visible).forEach(row => output.append(payrollRow(state,row)));
    if (rows.length > state.visible) output.append(button(`Mostra altre buste (${rows.length - state.visible})`, () => { state.visible += 100; render(state); },'btn btn-s'));
    if (state.employee) {
      const section = el('details','rcard'); section.style.marginTop = '14px'; const summary = el('summary','rcard-hd','Posizione dipendente e saldo progressivo'); summary.style.minHeight = '44px';
      const content = el('div'); content.style.padding = '0 12px 12px'; section.append(summary,content); output.append(section);
      let loaded = false; section.addEventListener('toggle', () => { if (section.open && !loaded) { loaded = true; employeePosition(state,state.employee,content,state.generation); } });
    }
    if (state.updated) message(output,`Ultima lettura ${state.updated.toLocaleTimeString('it-IT')} · aggiornamento automatico ogni minuto mentre questa pagina è aperta.`);
  }
  function updateEmployees(state) {
    const previous = state.employee;
    state.employeeSelect.replaceChildren(el('option','','Tutti i dipendenti'));
    state.employeeSelect.firstChild.value = '';
    (state.employees || []).forEach(value => { if (!value.id) return; const option = el('option','',value.nome_completo || [value.cognome,value.nome].filter(Boolean).join(' ') || value.id); option.value = value.id; state.employeeSelect.append(option); });
    state.employeeSelect.value = previous;
    if (state.employeeSelect.value !== previous) { state.employee = ''; state.employeeSelect.value = ''; }
  }
  async function load(state) {
    const generation = ++state.generation; state.loading = true; state.data = null; state.error = ''; state.employeesError = ''; render(state);
    const params = new URLSearchParams({ anno: String(state.year) }); if (state.month) params.set('mese',state.month);
    const results = await Promise.allSettled([json(state,`${API}/associazioni-bonifici?${params}`),json(state,'/hr/api/dipendenti?limit=10000')]);
    if (generation !== state.generation) return;
    const [payroll,employees] = results;
    if (payroll.status === 'fulfilled' && Array.isArray(payroll.value.righe)) state.data = payroll.value;
    else state.error = payroll.status === 'rejected' ? payroll.reason.message : 'Risposta paghe incompleta';
    if (employees.status === 'fulfilled' && Array.isArray(employees.value)) {
      state.employees = employees.value; updateEmployees(state);
      if (employees.value.length === 10000) state.employeesError = 'L’anagrafica ha raggiunto il limite di 10000 righe: usa la gestione HR completa.';
    }
    else state.employeesError = employees.status === 'rejected' ? employees.reason.message : 'Risposta anagrafica incompleta';
    state.loading = false; state.updated = new Date(); render(state);
  }
  function mount(root,bridge) {
    const previous = states.get(root);
    if (previous?.output?.isConnected) return;
    if (previous) { previous.generation += 1; clearInterval(previous.interval); }
    const state = { root,bridge,year:new Date().getFullYear(),month:'',employee:'',status:'',search:'',visible:100,generation:0,data:null };
    states.set(root,state); root.replaceChildren();
    const heading = el('div','tot-card'); heading.append(el('strong','','Paghe e cedolini'),el('div','fi-meta','Dipendenti HR, buste, bonifici, acconti e saldi nello stesso registro del Gestionale.'));
    const controls = el('div'); controls.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;align-items:end';
    const year = el('input'); year.type = 'number'; year.min = '2000'; year.max = '2100'; year.value = state.year;
    year.addEventListener('change', () => { const value = Number(year.value); if (!Number.isInteger(value) || value < 2000 || value > 2100) { year.value = state.year; return; } state.year = value; state.visible = 100; load(state); });
    state.employeeSelect = select([['','Tutti i dipendenti']], '', value => { state.employee = value; state.visible = 100; render(state); });
    const search = el('input'); search.type = 'search'; search.placeholder = 'Nome o cognome'; search.addEventListener('input', () => { state.search = search.value.trim(); state.visible = 100; render(state); });
    controls.append(field('Anno',year),field('Mese',select([['','Tutto l’anno'],...months.map((value,index) => [String(index + 1),value])],'',value => { state.month = value; state.visible = 100; load(state); })),
      field('Dipendente',state.employeeSelect),field('Stato',select([['','Tutti gli stati'],...Object.entries(statuses)],'',value => { state.status = value; state.visible = 100; render(state); })),field('Ricerca',search),button('Aggiorna',() => load(state),'fil-btn'));
    heading.append(controls); root.append(heading);
    const shortcuts = el('div','fi-actions-main'); shortcuts.style.cssText = 'flex-wrap:wrap;margin-bottom:14px';
    shortcuts.append(link('Importa e gestisci paghe HR','/hr/'),button('Excel del periodo · tutti i dipendenti',() => { const params = new URLSearchParams({anno:String(state.year)}); if (state.month) params.set('mese',state.month); if (state.status) params.set('stato',state.status); download(state,`${API}/associazioni-bonifici/export-excel?${params}`,`Paghe_${state.year}${state.month ? `_${state.month}` : ''}.xlsx`,state.output); })); root.append(shortcuts);
    state.output = el('div'); state.output.setAttribute('aria-live','polite'); root.append(state.output); render(state);
    const interval = setInterval(() => { if (!state.output.isConnected) { clearInterval(interval); return; } if (!document.hidden && root.getClientRects().length && !state.loading) load(state); },60000);
    state.interval = interval;
  }
  window.CeraldiGestionaleModules.register({id:'paghe_gc',title:'Paghe e cedolini',icon:'👥',mount,
    onOpen(root,bridge) { mount(root,bridge); const state = states.get(root); state.bridge = bridge; return load(state); }});
})();
