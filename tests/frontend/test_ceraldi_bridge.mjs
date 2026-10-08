import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const publicDir = path.join(repo, 'frontend/public');

async function loadDataAdapter() {
  const context = vm.createContext({ window: {}, Response, Request, Headers, URL, URLSearchParams, console });
  const source = await fs.readFile(path.join(publicDir, 'ceraldi-bridge-data.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'ceraldi-bridge-data.js' });
  assert.equal(typeof context.window.CeraldiBridgeData?.request, 'function');
  return context.window.CeraldiBridgeData;
}

function apiFixture(routes) {
  const calls = [];
  const api = async (url, opts = {}) => {
    calls.push({ url: String(url), opts });
    const endpoint = new URL(String(url), 'https://gestionale.example').pathname;
    if (!Object.hasOwn(routes, endpoint) && endpoint.startsWith('/api/invoices/') && Object.hasOwn(routes, '/api/invoices') && (!opts.method || opts.method === 'GET')) {
      const source = routes['/api/invoices'];
      const rows = typeof source === 'function' ? await source(url, opts) : source;
      assert.ok(Array.isArray(rows), 'invoice detail fallback fixture needs a canonical invoice array');
      const identifier = decodeURIComponent(endpoint.slice('/api/invoices/'.length));
      const row = rows.find(value => String(value.id) === identifier);
      return new Response(JSON.stringify(row || { detail: 'Fattura non trovata' }), { status: row ? 200 : 404, headers: { 'Content-Type': 'application/json' } });
    }
    assert.ok(Object.hasOwn(routes, endpoint), 'unexpected API endpoint: ' + url);
    const value = routes[endpoint];
    const payload = typeof value === 'function' ? await value(url, opts) : value;
    return payload instanceof Response ? payload : new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  return { api, calls };
}

async function loadAuthenticatedBridge(status = 200, user = { email: 'test@example.invalid', name: 'Test', role: 'admin' }, responses = {}) {
  const elements = new Map();
  const calls = [];
  const redirects = [];
  const nativeValues = new Map([['cf_fatture_cache', JSON.stringify([{ id: 'old-project-record' }])], ['cf_auth_v1', 'old-project-token']]);
  const nativeStorage = { getItem: key => nativeValues.get(String(key)) ?? null, setItem: (key, value) => nativeValues.set(String(key), String(value)), removeItem: key => nativeValues.delete(String(key)) };
  const location = { origin: 'https://gestionale.example', href: 'https://gestionale.example/primanota-ceraldi.html', replace: url => redirects.push(url) };
  const createElement = () => ({ style: {}, innerHTML: '', setAttribute() {}, appendChild() {}, addEventListener() {}, remove() { elements.delete(this.id); } });
  const document = {
    readyState: 'complete', getElementById: id => elements.get(id) || null,
    createElement, querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
    body: { appendChild: el => elements.set(el.id, el) },
  };
  let initialized = 0;
  const window = {
    localStorage: nativeStorage, init: async () => { initialized++; },
    dispatchEvent() {}, CeraldiBridgeData: { request: async () => new Response('[]') },
    fetch: async (url, opts) => {
      calls.push({ url: String(url), opts });
      const endpoint = new URL(url, location.origin).pathname;
      if (Object.hasOwn(responses, endpoint)) return new Response(JSON.stringify(responses[endpoint]), { status: 200 });
      return new Response(JSON.stringify(endpoint === '/api/auth/verify' ? { ok: status === 200, user } : []), { status });
    },
  };
  const context = vm.createContext({ window, document, location, navigator: {}, Response, Request, Headers, URL, URLSearchParams, console, CustomEvent: class { constructor(type, data) { this.type = type; this.detail = data?.detail; } } });
  const source = await fs.readFile(path.join(publicDir, 'ceraldi-bridge.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'ceraldi-bridge.js' });
  return { bridge: window.CeraldiBridge, window, calls, redirects, elements, nativeValues, initialized: () => initialized, runScript: async file => vm.runInContext(await fs.readFile(path.join(publicDir, file), 'utf8'), context, { filename: file }) };
}

async function loadSemanticActions(routes, records = []) {
  const fixture = apiFixture(routes);
  const messages = [], fields = new Map();
  let bankReloads = 0;
  const window = {
    fatture: records, fornitori: [], gv: name => fields.get(name)?.value || '',
    document: { getElementById: id => fields.get(id) || null }, confirm: () => true,
    toast: message => messages.push(message), loadMovimentiBanca: async () => { bankReloads++; },
    CeraldiBridge: { api: fixture.api, canWrite: true, requireWrite() { if (!this.canWrite) { const error = new Error('Sola lettura'); error.status = 403; throw error; } }, showUnsupported() {} },
  };
  const context = vm.createContext({ window, Response, Request, Headers, URL, URLSearchParams, FormData, Blob, TextEncoder, console });
  for (const file of ['ceraldi-bridge-data.js', 'ceraldi-bridge-actions.js']) vm.runInContext(await fs.readFile(path.join(publicDir, file), 'utf8'), context, { filename: file });
  assert.equal(typeof window.CeraldiBridgeActions?.install, 'function');
  window.CeraldiBridgeActions.install();
  return { actions: window.CeraldiBridgeActions, window, calls: fixture.calls, fields, messages, bankReloads: () => bankReloads };
}

// Read actual inline declarations rather than duplicating their implementation.
// Native parsing finds the first balanced function body, including braces in
// comments, regexes and templates, without introducing a parser dependency.
function inlineFunction(html, name) {
  const declaration = new RegExp('^(?:async\\s+)?function\\s+' + name + '\\s*\\(', 'm').exec(html);
  assert.ok(declaration, 'missing original UI function: ' + name);
  const tail = html.slice(declaration.index);
  for (const end of tail.matchAll(/}/g)) {
    const source = tail.slice(0, end.index + 1);
    try { new vm.Script(source); return source; } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  assert.fail('unbalanced original UI function: ' + name);
}

function decodeHtmlAttribute(value) {
  return value.replace(/&(quot|apos|amp|lt|gt|#\d+|#x[0-9a-f]+);/gi, (_match, entity) => {
    if (entity[0] === '#') return String.fromCodePoint(parseInt(entity.slice(entity[1].toLowerCase() === 'x' ? 2 : 1), entity[1].toLowerCase() === 'x' ? 16 : 10));
    return { quot: '"', apos: "'", amp: '&', lt: '<', gt: '>' }[entity.toLowerCase()];
  });
}

async function loadOriginalInvoiceUi(routes) {
  const html = await fs.readFile(path.join(publicDir, 'primanota-ceraldi.html'), 'utf8');
  const fixture = apiFixture(routes), savedRows = [], rendered = [], opened = [], scheduled = [], messages = [], requests = [];
  const elements = new Map(['fattMo', 'fattMoBody', 'fattMoTitle', 'fattMoSub', 'fattMoElimina'].map(id => [id, { style: {}, innerHTML: '', textContent: '' }]));
  const context = vm.createContext({
    window: {}, Response, Request, Headers, URL, URLSearchParams, atob,
    fatture: [], fornitori: [], _fattMoDdtId: null,
    location: { hash: '', pathname: '/primanota-ceraldi.html', search: '' },
    history: { replaceState() {} }, document: { getElementById: id => elements.get(id) || null },
    setTimeout: (fn, delay) => { scheduled.push({ fn, delay }); }, toast: text => messages.push(text),
    console: { log() {}, warn() {}, error() {} },
    _loadCache: () => null, _cacheMaxTs: () => 0, _saveCache: rows => savedRows.push(rows), cacheSet() {},
    renderFatturaXML: (xml, invoice) => { rendered.push({ xml, id: invoice.id }); return '<rendered-document>'; }, autoEstraiPrezzi() {},
  });
  vm.runInContext(await fs.readFile(path.join(publicDir, 'ceraldi-bridge-data.js'), 'utf8'), context, { filename: 'ceraldi-bridge-data.js' });
  context.sbFetch = async (resource, opts = {}) => {
    requests.push(resource);
    if (resource.startsWith('impostazioni?')) return [];
    const response = await context.window.CeraldiBridgeData.request(resource, opts, fixture.api);
    assert.equal(response.status, 200, 'original UI read failed: ' + resource);
    return response.json();
  };
  const slim = html.match(/^const SLIM_COLS_FATTURE\s*=\s*'[^']*';/m)?.[0];
  assert.ok(slim, 'the original loadAll list projection must be exercised');
  vm.runInContext(slim, context);
  for (const name of ['_numeroDbFacoltativo', 'dbToApp', 'sbFetchAll', 'loadAll', '_arricchisciConFlagAllegati', 'fetchAllegataSingola', 'esc', 'fmt', '_haXml', '_btnXml', 'pnIdJs', 'pnModifica', 'pnStorico', '_apriFatturaDaLink', 'aprifatturaAllegata', '_mostraFatturaDataUrl']) {
    vm.runInContext(inlineFunction(html, name), context, { filename: 'primanota-ceraldi.html:' + name });
  }
  const actualOpen = context.aprifatturaAllegata;
  context.aprifatturaAllegata = id => {
    const pending = actualOpen(id);
    opened.push({ id, pending });
    return pending;
  };
  return { context, calls: fixture.calls, savedRows, rendered, opened, scheduled, messages, requests, elements };
}

test('login returns to the Ceraldi page and rejects external or disguised destinations', async () => {
  const login = await fs.readFile(path.join(repo, 'frontend/src/pages/Login.jsx'), 'utf8');
  const source = login.match(/export function destinazioneDopoLogin\([^]*?\n\}/)?.[0];
  assert.ok(source, 'the login destination function must exist');
  const context = vm.createContext({ URLSearchParams, window: { location: { search: '' } } });
  vm.runInContext(source.replace('export ', ''), context);
  assert.equal(context.destinazioneDopoLogin('?next=%2Fprimanota-ceraldi.html'), '/primanota-ceraldi.html');
  assert.equal(context.destinazioneDopoLogin('?next=%2Flotti%2F'), '/lotti/');
  for (const destination of ['https://example.com/primanota-ceraldi.html', '//example.com', '/primanota-ceraldi.html/evil', '/primanota-ceraldi.html?evil=1', '/%2fexample.com', '/%70rimanota-ceraldi.html']) {
    assert.equal(context.destinazioneDopoLogin('?next=' + encodeURIComponent(destination)), '', destination);
  }
});

test('invoice reads preserve text IDs and do not turn missing payment state into paid', async () => {
  const bridge = await loadDataAdapter();
  const { api } = apiFixture({
    '/api/invoices': [
      { id: 'historic-text-00001', invoice_number: 'A/1', invoice_date: '2026-10-01', supplier_name: 'Fornitore Uno', total_amount: 100 },
      { id: '550e8400-e29b-41d4-a716-446655440000', invoice_number: 'A/2', invoice_date: '2026-10-02', supplier_name: 'Fornitore Due', total_amount: 200, pagato: false },
    ],
  });
  const response = await bridge.request('fatture?select=*&order=data.asc', {}, api);
  assert.equal(response.status, 200);
  const rows = await response.json();
  assert.equal(rows.length, 2);
  assert.equal(rows[0].id, 'historic-text-00001');
  assert.equal(rows[1].id, '550e8400-e29b-41d4-a716-446655440000');
  assert.ok(rows.every(row => row.stato !== 'pagata' && !row.riconciliata));
});

test('legacy filters and inclusive Range are applied after mapping and stable order', async () => {
  const bridge = await loadDataAdapter();
  const { api } = apiFixture({
    '/api/invoices': [
      { id: 'a', invoice_date: '2026-09-15', total_amount: 20, supplier_name: 'Uno' },
      { id: 'b', invoice_date: '2026-10-01', total_amount: 10, supplier_name: 'Due' },
      { id: 'c', invoice_date: '2026-10-02', total_amount: 30, supplier_name: 'Tre' },
      { id: 'd', invoice_date: '2026-10-03', total_amount: 40, supplier_name: 'Quattro' },
    ],
  });
  const response = await bridge.request('fatture?select=id,data,importo&data=gte.2026-10-01&importo=gt.15&order=data.desc', { headers: { Range: '1-1' } }, api);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), [{ id: 'c', data: '2026-10-02', importo: 30 }]);
});

test('unsupported writes return 501 without forwarding a raw or sensitive write', async () => {
  const bridge = await loadDataAdapter();
  const { api, calls } = apiFixture({});
  for (const [resource, opts] of [
    ['unknown_table', { method: 'POST', body: JSON.stringify({ valore: 'qualcosa' }) }],
    ['fatture?id=eq.invoice-one', { method: 'PATCH', body: JSON.stringify({ stato: 'pagata', riconciliata: true }) }],
    ['movimenti_banca?id=eq.bank-one', { method: 'PATCH', body: JSON.stringify({ abbinata: true, fattura_id: 'invoice-one' }) }],
    ['rpc/backup_adesso', { method: 'POST', body: '{}' }],
  ]) {
    const response = await bridge.request(resource, opts, api);
    assert.equal(response.status, 501, resource);
  }
  assert.equal(calls.length, 0, 'unsupported mutations must not send network writes');
});

test('invoice collection pagination does not truncate to the first canonical API page', async () => {
  const bridge = await loadDataAdapter();
  const all = Array.from({ length: 1003 }, (_, i) => ({ id: 'invoice-' + String(i).padStart(4, '0'), invoice_date: '2026-10-01', total_amount: i + 1 }));
  const { api, calls } = apiFixture({
    '/api/invoices': url => {
      const params = new URL(String(url), 'https://gestionale.example').searchParams;
      const skip = Number(params.get('skip') || 0);
      const limit = Number(params.get('limit') || 100);
      return all.slice(skip, skip + limit);
    },
  });
  const response = await bridge.request('fatture?select=id&order=id.asc', { headers: { Range: '1000-1002' } }, api);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), [{ id: 'invoice-1000' }, { id: 'invoice-1001' }, { id: 'invoice-1002' }]);
  assert.ok(calls.some(call => Number(new URL(call.url, 'https://gestionale.example').searchParams.get('skip')) > 0));
});

test('an invoice opened by exact ID reads its XML from the canonical detail endpoint', async () => {
  const bridge = await loadDataAdapter();
  const xml = '<FatturaElettronica><DatiGeneraliDocumento/></FatturaElettronica>';
  const { api, calls } = apiFixture({ '/api/invoices/historic-text-id': { id: 'historic-text-id', invoice_date: '2026-10-08', total_amount: 100, xml_content: xml } });
  const response = await bridge.request('fatture?id=eq.historic-text-id&select=id,fattura_allegata', {}, api);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), [{ id: 'historic-text-id', fattura_allegata: xml }]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/invoices/historic-text-id');
});

test('invoice list metadata marks original documents without downloading their bodies and preserves unknown answers', async () => {
  const bridge = await loadDataAdapter();
  const originals = [
    { id: 'filename-xml', filename: 'fattura.xml' },
    { id: 'filename-pdf', fattura_allegata_name: 'fattura.pdf' },
    { id: 'document-reference', document_original_ref: { drive_file_id: 'drive-document' } },
    { id: 'source-reference', source_document_id: 'source-document' },
    { id: 'server-no-document', filename: 'historic-name.xml', has_allegata: false },
    { id: 'server-unknown', filename: 'historic-name.xml', has_allegata: null },
    { id: 'no-evidence' },
  ];
  const { api } = apiFixture({ '/api/invoices': originals });
  const response = await bridge.request('fatture?select=id,has_allegata,fattura_allegata&order=id.asc', {}, api);
  assert.equal(response.status, 200);
  const rows = await response.json();
  for (const row of rows) {
    const expected = ['server-unknown', 'no-evidence'].includes(row.id) ? null : row.id !== 'server-no-document';
    assert.equal(row.has_allegata, expected, row.id);
    assert.equal(row.fattura_allegata, null, 'list metadata must not become a fabricated document body');
  }
});

test('the original list, document buttons and lazy viewer preserve canonical document metadata and text IDs', async () => {
  const identifiers = ['550e8400-e29b-41d4-a716-446655440000', '000042', '9007199254740993'];
  const invoices = identifiers.map((id, i) => ({ id, invoice_number: 'XML/' + i, invoice_date: '2026-10-08', supplier_name: 'Fornitore Uno', filename: id + '.xml', total_amount: 100 }));
  invoices.push(
    { id: 'explicit-false', invoice_date: '2026-10-08', filename: 'historic.xml', source: 'aruba', has_allegata: false },
    { id: 'explicit-null', invoice_date: '2026-10-08', filename: 'historic.xml', has_allegata: null },
    { id: 'pdf-original', invoice_date: '2026-10-08', fattura_allegata_name: 'originale.pdf' },
    { id: 'source-original', invoice_date: '2026-10-08', source_document_id: 'document-id' },
  );
  const routes = { '/api/invoices': invoices, '/api/suppliers': [] };
  for (const id of identifiers) routes['/api/invoices/' + encodeURIComponent(id)] = { ...invoices.find(invoice => invoice.id === id), xml_content: '<FatturaElettronica><Numero>' + id + '</Numero></FatturaElettronica>' };
  const current = await loadOriginalInvoiceUi(routes);
  assert.equal(await current.context.loadAll(true), true);
  const loaded = current.context.fatture;
  assert.equal(loaded.length, invoices.length);
  assert.equal(current.savedRows.length, 1);
  for (const id of [...identifiers, 'pdf-original', 'source-original']) {
    assert.equal(current.savedRows[0].find(row => row.id === id).has_allegata, true, 'enrichment must preserve canonical list evidence for ' + id);
    assert.equal(loaded.find(row => row.id === id).hasAllegata, true, 'dbToApp must retain the document flag for ' + id);
  }
  assert.equal(current.savedRows[0].find(row => row.id === 'explicit-false').has_allegata, false);
  assert.equal(current.savedRows[0].find(row => row.id === 'explicit-null').has_allegata, null);
  assert.equal(current.context._btnXml(loaded.find(row => row.id === 'explicit-false')), '');
  assert.equal(current.context._btnXml(loaded.find(row => row.id === 'explicit-null')), '');
  assert.ok(current.requests.some(resource => resource.includes('has_allegata')), 'the actual slim projection/enrichment must request attachment metadata');
  assert.ok(current.requests.every(resource => !/[?&](?:foto|fattura_allegata)=/.test(resource)), 'list enrichment must not query an omitted original body');
  assert.equal(current.rendered.length, 0);
  assert.ok(loaded.every(invoice => !invoice.fatturaAllegata), 'the list leaves original XML for lazy loading');
  for (const id of identifiers) {
    const invoice = loaded.find(row => row.id === id);
    const button = current.context._btnXml(invoice, 'mini');
    const dataset = decodeHtmlAttribute(button.match(/\bdata-fx="([^"]*)"/)?.[1] || '');
    const handler = decodeHtmlAttribute(button.match(/\bonclick="([^"]*)"/)?.[1] || '');
    assert.equal(dataset, id);
    assert.ok(handler, 'the rendered original document button must have a click handler');
    const click = vm.runInContext('(function(event){' + handler + '})', current.context);
    let propagationStopped = false;
    click.call({ dataset: { fx: dataset } }, { stopPropagation() { propagationStopped = true; } });
    assert.equal(propagationStopped, true);
    assert.equal(current.opened.at(-1).id, id, 'rendered button must retain ID type and value');
    await current.opened.at(-1).pending;
    assert.equal(current.context._fattMoDdtId, id);
    assert.deepEqual(current.rendered.at(-1), { xml: routes['/api/invoices/' + encodeURIComponent(id)].xml_content, id });
    assert.equal(invoice.fatturaAllegata, current.rendered.at(-1).xml);
  }
  const detailCalls = current.calls.filter(call => new URL(call.url, 'https://gestionale.example').pathname.startsWith('/api/invoices/'));
  assert.deepEqual(detailCalls.map(call => call.url), identifiers.map(id => '/api/invoices/' + encodeURIComponent(id)));
});

test('original ID expressions and invoice links preserve zeroes, unsafe integer text and encoded identifiers', async () => {
  const identifiers = ['550e8400-e29b-41d4-a716-446655440000', '000042', '9007199254740993', 'quoted\'"/identity'];
  const current = await loadOriginalInvoiceUi({});
  const opened = [];
  const edited = [], histories = [];
  current.context.aprifatturaAllegata = id => { opened.push(id); };
  current.context.openEdit = id => { edited.push(id); };
  current.context.editId = 'prior-editor';
  current.context._stApri = () => { histories.push(current.context.editId); };
  current.context.fatture = identifiers.map(id => ({ id }));
  for (const id of identifiers) {
    const expression = decodeHtmlAttribute(current.context.pnIdJs(id));
    assert.equal(vm.runInContext(expression, current.context), id, 'pnIdJs must round-trip a text ID through its rendered HTML');
    vm.runInContext('pnModifica(' + expression + ');pnStorico(' + expression + ')', current.context);
    assert.equal(edited.at(-1), id);
    assert.equal(histories.at(-1), id);
    assert.equal(current.context.editId, 'prior-editor');
    current.context.location.hash = '#fattura=' + encodeURIComponent(id);
    current.context._apriFatturaDaLink();
    assert.equal(opened.at(-1), id, 'hash link must open the exact canonical record');
  }
  assert.equal(current.scheduled.length, 0, 'loaded records must be found immediately without numeric coercion');
});

test('the original invoice conversion and display distinguish missing monetary values from confirmed zero', async () => {
  const current = await loadOriginalInvoiceUi({});
  for (const unknown of [null, undefined, '', '  ', 'invalid', false]) {
    const invoice = current.context.dbToApp({ id: 'unknown-money', importo: unknown, iva: unknown, totale_imponibile: unknown, totale_imposta: unknown });
    for (const field of ['importo', 'iva', 'totaleImponibile', 'totaleImposta']) assert.equal(invoice[field], null, field);
    assert.equal(current.context.fmt(unknown), '—', 'an unknown amount must not display as a confirmed zero');
  }
  for (const zero of [0, '0', '0.00']) {
    const invoice = current.context.dbToApp({ id: 'zero-money', importo: zero, iva: zero, totale_imponibile: zero, totale_imposta: zero });
    for (const field of ['importo', 'iva', 'totaleImponibile', 'totaleImposta']) assert.equal(invoice[field], 0, field);
    assert.equal(current.context.fmt(zero), '€ 0,00');
  }
});

test('manual bank rows use the canonical writer and preserve the pending bank state', async () => {
  const bridge = await loadDataAdapter();
  const pending = { id: 'bank-new-uuid', data: '2026-10-08', tipo: 'uscita', importo: 100, descrizione: 'Spesa da verificare', categoria: 'Altro', source: 'manuale_banca_senza_evidenza', provvisorio: true, stato: 'DA_VERIFICARE', in_attesa_estratto_ufficiale: true, riconciliato: false };
  const { api, calls } = apiFixture({
    '/api/prima-nota/banca': (url, opts) => opts.method === 'POST' ? { id: pending.id } : { movimenti: [pending], totale: 1, saldo: 0 },
    '/api/prima-nota/cassa': { movimenti: [], totale: 0 },
  });
  const response = await bridge.request('prima_nota_movimenti', { method: 'POST', body: JSON.stringify({ conto: 'banca', data: pending.data, tipo: pending.tipo, importo: pending.importo, descrizione: pending.descrizione, categoria: pending.categoria }) }, api);
  assert.equal(response.status, 200);
  const rows = await response.json();
  assert.equal(rows[0].id, pending.id);
  assert.ok(rows[0].provvisorio || rows[0].in_attesa_estratto_ufficiale, 'the manual bank row remains pending');
  assert.notEqual(rows[0].riconciliato, true);
  const write = calls.find(call => call.opts.method === 'POST');
  assert.ok(write, 'the canonical endpoint must perform the write');
  assert.equal(new URL(write.url, 'https://gestionale.example').pathname, '/api/prima-nota/banca');
  const payload = JSON.parse(write.opts.body);
  assert.notEqual(payload.riconciliato, true);
  assert.notEqual(payload.stato, 'riconciliato');
  assert.notEqual(payload.source, 'estratto_conto_auto');
});

test('bank payment requests preserve the canonical pending result instead of marking the invoice paid', async () => {
  const bridge = await loadDataAdapter();
  const pending = { success: true, pagata: false, riconciliata: false, stato: 'in_attesa_estratto_conto', importo_in_attesa: 100 };
  const { api, calls } = apiFixture({ '/api/fatture-ricevute/paga-manuale': pending });
  const response = await bridge.request('rpc/paga_fattura', { method: 'POST', body: JSON.stringify({ fattura_id: 'invoice-historic-text-id', metodo: 'banca', importo: 100, data_pagamento: '2026-10-08' }) }, api);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), pending);
  assert.equal(calls.length, 1);
  assert.deepEqual(JSON.parse(calls[0].opts.body), { fattura_id: 'invoice-historic-text-id', metodo: 'banca', importo: 100, data_pagamento: '2026-10-08' });
});

test('bank reconciliation forwards exact document and statement IDs and propagates ambiguous-result errors', async () => {
  const bridge = await loadDataAdapter();
  const { api, calls } = apiFixture({ '/api/fatture-ricevute/riconcilia-con-estratto-conto': new Response(JSON.stringify({ detail: 'Movimento già associato' }), { status: 409 }) });
  const response = await bridge.request('rpc/riconcilia_fattura', { method: 'POST', body: JSON.stringify({ fattura_id: 'invoice/uuid', movimento_id: 'statement-uuid' }) }, api);
  assert.equal(response.status, 409);
  assert.deepEqual(JSON.parse(calls[0].opts.body), { fattura_id: 'invoice/uuid', movimento_id: 'statement-uuid' });
  const blocked = await bridge.request('rpc/riconcilia_fattura', { method: 'POST', body: JSON.stringify({ fattura_id: 'invoice/uuid', movimento_id: 'statement-uuid', riconciliata: true, force: true }) }, api);
  assert.equal(blocked.status, 501);
  assert.equal(calls.length, 1);
});

test('a paid invoice with a legacy reconciliation flag alone is not bank evidence', async () => {
  const bridge = await loadDataAdapter();
  const { api } = apiFixture({ '/api/invoices': [{ id: 'paid-with-flag', invoice_date: '2026-10-08', total_amount: 100, stato: 'pagata', riconciliato: true, payment_method: 'banca' }] });
  const response = await bridge.request('fatture?select=id,stato,riconciliata', {}, api);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), [{ id: 'paid-with-flag', stato: 'pagata', riconciliata: false }]);
});

test('unsupported filters are rejected even when an earlier filter excludes every row', async () => {
  const bridge = await loadDataAdapter();
  const { api } = apiFixture({ '/api/invoices': [] });
  const response = await bridge.request('fatture?data=gte.2026-10-01&numero=unsupported.A', {}, api);
  assert.equal(response.status, 501);
});

test('401 opens the shared login with an explicit return path, while 503 keeps access closed', async () => {
  const unauthorized = await loadAuthenticatedBridge(401);
  await unauthorized.bridge.bootstrap();
  assert.equal(unauthorized.bridge.authorized, false);
  assert.equal(unauthorized.initialized(), 0);
  assert.deepEqual(unauthorized.redirects, ['/login?next=%2Fprimanota-ceraldi.html']);
  const unavailable = await loadAuthenticatedBridge(503);
  await unavailable.bridge.bootstrap();
  assert.equal(unavailable.bridge.authorized, false);
  assert.equal(unavailable.initialized(), 0);
  assert.deepEqual(unavailable.redirects, []);
  assert.match(unavailable.elements.get('ceraldiSessionGate').innerHTML, /temporaneamente non disponibile/);
});

test('shared session enables only authenticated API calls and isolates old project cache', async () => {
  const current = await loadAuthenticatedBridge();
  await current.bridge.bootstrap();
  assert.equal(current.bridge.authorized, true);
  assert.equal(current.initialized(), 1);
  assert.equal(current.window.localStorage.getItem('cf_fatture_cache'), null);
  assert.equal(current.window.localStorage.getItem('cf_auth_v1'), null);
  assert.ok(current.nativeValues.has('cf_fatture_cache'), 'the old browser data is never imported or erased');
  await current.bridge.api('/api/invoices', { headers: { apikey: 'old-key', Authorization: 'Bearer old-token' } });
  const actual = current.calls.at(-1).opts;
  assert.equal(actual.credentials, 'same-origin');
  assert.equal(actual.headers.get('apikey'), null);
  assert.equal(actual.headers.get('Authorization'), null);
  await assert.rejects(current.window.fetch('https://example.com/rest/v1/fatture'), error => error.status === 501);
  await assert.rejects(current.bridge.api('/api/raw-collection', { method: 'POST', body: '{}' }), error => error.status === 501);
});

test('read-only shared sessions may load data but cannot forward a write', async () => {
  const current = await loadAuthenticatedBridge(200, { email: 'test@example.invalid', role: 'sola_lettura' });
  await current.bridge.bootstrap();
  assert.equal(current.bridge.authorized, true);
  await current.bridge.api('/api/invoices');
  const before = current.calls.length;
  await assert.rejects(current.bridge.api('/api/prima-nota/cassa', { method: 'POST', body: '{}' }), error => error.status === 403);
  await assert.rejects(current.window.fetch('/ceraldi-compat/rest/v1/prima_nota_movimenti', { method: 'POST', body: '{}' }), error => error.status === 403);
  assert.equal(current.calls.length, before);
});

test('manual invoice notes use the explicitly allowed canonical endpoint', async () => {
  const current = await loadAuthenticatedBridge();
  await current.bridge.bootstrap();
  const response = await current.bridge.api('/api/fatture-ricevute/fattura/historic-text-id', { method: 'PUT', body: JSON.stringify({ note: 'Nota di verifica' }) });
  assert.equal(response.status, 200);
  assert.equal(new URL(current.calls.at(-1).url).pathname, '/api/fatture-ricevute/fattura/historic-text-id');
});

test('the actions installer registers the finite canonical group route in the authenticated transport', async () => {
  const current = await loadAuthenticatedBridge();
  await current.runScript('ceraldi-bridge-actions.js');
  await current.bridge.bootstrap();
  const response = await current.bridge.api('/api/operazioni-da-confermare/smart/riconcilia-manuale', { method: 'POST', body: JSON.stringify({ movimento_id: 'statement-id', tipo: 'fattura', associazioni: [{ id: 'invoice-id', quota_cents: 1000 }] }) });
  assert.equal(response.status, 200);
  await assert.rejects(current.bridge.api('/api/operazioni-da-confermare/smart/other', { method: 'POST', body: '{}' }), error => error.status === 501);
});

test('HR reads obtain a derived session from the shared login and keep that token in the tab', async () => {
  const current = await loadAuthenticatedBridge(200, { email: 'test@example.invalid', role: 'admin' }, { '/hr/api/auth/session': { access_token: 'test-derived-hr-token' }, '/hr/api/dipendenti': [] });
  await current.runScript('ceraldi-paghe.js');
  await current.bridge.bootstrap();
  assert.equal(current.bridge.canWrite, true);
  await current.bridge.api('/hr/api/dipendenti');
  await current.bridge.api('/hr/api/dipendenti');
  const exchanges = current.calls.filter(call => new URL(call.url, 'https://gestionale.example').pathname === '/hr/api/auth/session');
  assert.equal(exchanges.length, 1);
  const hr = current.calls.filter(call => new URL(call.url, 'https://gestionale.example').pathname === '/hr/api/dipendenti');
  assert.equal(hr.length, 2);
  assert.ok(hr.every(call => call.opts.headers.get('Authorization') === 'Bearer test-derived-hr-token'));
  assert.ok([...current.nativeValues.values()].every(value => !value.includes('test-derived-hr-token')));
});

test('automation status uses its canonical endpoint and legacy aliases do not start raw writes', async () => {
  const current = await loadAuthenticatedBridge(200, { email: 'test@example.invalid', role: 'admin' }, {
    '/api/sync/stato-sincronizzazione': { ultimo_esito: { ok: true } },
    '/lotti/api/auth/session': { token: 'test-derived-lotti-token' },
    '/lotti/api/gestionale-fatture/stato': { ok: true },
  });
  await current.runScript('ceraldi-automazioni.js');
  await current.bridge.bootstrap();
  const status = await current.bridge.runAutomation('sincronizzazione', { action: 'status' });
  assert.equal(status.state, 'stato_letto');
  const aliased = await current.window.autoEstraiPrezzi({ id: 'fixture-xml' });
  assert.equal(aliased.managed_by, 'GestionaleCloud');
  assert.equal(aliased.state, 'stato_letto');
  assert.ok(current.calls.some(call => new URL(call.url, 'https://gestionale.example').pathname === '/api/sync/stato-sincronizzazione'));
  assert.ok(current.calls.every(call => !call.opts?.method || call.opts.method === 'GET'), 'opening or refreshing the recovered page performs no automated writes');
  const before = current.calls.length;
  await assert.rejects(current.bridge.runAutomation('_purgaCestinoScaduto'), error => error.status === 501);
  assert.equal(current.calls.length, before);
});

test('reopening a module keeps one mounted panel and refreshes its data without duplicating handlers', async () => {
  const current = await loadAuthenticatedBridge();
  await current.bridge.bootstrap();
  const root = { classList: { add() {} }, replaceChildren(...children) { this.children = children; } };
  current.elements.set('ceraldiModuleView', root);
  let mounted = 0, opened = 0, originalPanel;
  current.window.CeraldiGestionaleModules.register({ id: 'fixture_module', title: 'Fixture', mount(panel) { mounted++; originalPanel = panel; panel.draft = 'saved input'; }, onOpen() { opened++; } });
  current.window.CeraldiGestionaleModules.register({ id: 'fixture_other', title: 'Other', mount() {} });
  await current.window.CeraldiGestionaleModules.open('fixture_module');
  await current.window.CeraldiGestionaleModules.open('fixture_other');
  await current.window.CeraldiGestionaleModules.open('fixture_module');
  assert.equal(mounted, 1);
  assert.equal(opened, 2);
  assert.equal(root.children[0], originalPanel);
  assert.equal(root.children[0].draft, 'saved input');
});

test('the Fiscal tab and legacy fiscal links open the canonical module and direct imports to the central archive', async () => {
  const current = await loadAuthenticatedBridge();
  const root = { classList: { add() {} }, replaceChildren(...children) { this.children = children; } };
  current.elements.set('ceraldiModuleView', root);
  let opened = 0;
  current.window.CeraldiGestionaleModules.register({ id: 'fiscale_gc', title: 'Fiscale', mount() {}, onOpen() { opened++; } });
  await current.bridge.bootstrap();
  await current.window.goTab('fiscale');
  await current.window.apriFiscaleSezione('tributi');
  assert.equal(opened, 2);
  current.window.apriFiscaleSezione('importazioni');
  assert.equal(opened, 2);
  assert.match(current.elements.get('ceraldiUnsupported').innerHTML, /href="\/documenti\/import"/);
});

test('installed Quick Pay saves a cash payment and publishes only the canonical readback', async () => {
  const invoice = { id: 'cash-invoice-text', invoice_number: 'F/1', invoice_date: '2026-10-08', supplier_name: 'Fornitore Uno', total_amount: 100, amount_paid: 0, stato_pagamento: 'da_pagare' };
  const displayed = { id: invoice.id, stato: 'da_pagare', importo: 999 };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture-ricevute/paga-manuale': (_url, opts) => {
      const body = JSON.parse(opts.body);
      assert.equal(body.fattura_id, invoice.id);
      assert.equal(body.importo, 100, 'the payment uses the server residual rather than the stale screen amount');
      assert.equal(body.metodo, 'cassa');
      assert.ok(body.idempotency_key.startsWith('ceraldi:'));
      invoice.amount_paid = 100; invoice.stato_pagamento = 'pagata';
      return { success: true, movimento_id: 'cash-writer-uuid', pagamento_confermato: true };
    },
  }, [displayed]);
  const outcome = await current.window._applicaQuickPay(invoice.id, 'contanti', null, null, '2026-10-08');
  assert.ok(outcome);
  assert.equal(displayed.stato, 'pagata');
  assert.equal(displayed.importo, 100);
  assert.equal(displayed.parzPagato, 100);
  assert.ok(current.calls.at(-1).url.startsWith('/api/invoices'));
  assert.equal(current.calls.filter(call => call.opts.method === 'POST').length, 1);
});

test('installed partial-payment form preserves a bank proposal as an unpaid invoice', async () => {
  const invoice = { id: 'bank-invoice-text', invoice_date: '2026-10-08', total_amount: 100, amount_paid: 0, stato_pagamento: 'da_pagare', payment_method: 'banca' };
  const displayed = { id: invoice.id, stato: 'da_pagare', importo: 100 };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture-ricevute/paga-manuale': (_url, opts) => {
      const body = JSON.parse(opts.body);
      assert.equal(body.importo, 25);
      assert.equal(body.metodo, 'banca');
      invoice.stato_finanziario = 'in_attesa_estratto_conto';
      return { success: true, movimento_id: 'bank-pending-uuid', pagamento_confermato: false, in_attesa_estratto_ufficiale: true };
    },
  }, [displayed]);
  current.window.PRP = { id: invoice.id, scelta: -1 };
  current.fields.set('ppMetodo', { value: 'bonifico' }); current.fields.set('ppData', { value: '2026-10-08' }); current.fields.set('ppAltro', { value: '25' });
  const button = { disabled: false, textContent: 'Paga' };
  const outcome = await current.window.pprpSalva(button);
  assert.equal(outcome.pending, true);
  assert.equal(displayed.stato, 'da_pagare');
  assert.equal(displayed.parzPagato, 0);
  assert.equal(displayed.riconciliata, false);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Paga');
});

test('installed invoice edits save notes while arbitrary payment-state edits are restored and rejected', async () => {
  const invoice = { id: 'editable-invoice', invoice_date: '2026-10-08', total_amount: 100, amount_paid: 0, note: 'Prima', stato_pagamento: 'da_pagare', updated_at: '2026-10-08T10:00:00Z' };
  const displayed = { id: invoice.id, stato: 'da_pagare' };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture-ricevute/fattura/editable-invoice': (_url, opts) => { assert.deepEqual(JSON.parse(opts.body), { note: 'Dopo' }); invoice.note = 'Dopo'; return { success: true }; },
  }, [displayed]);
  current.window.editId = invoice.id; current.fields.set('eNote2', { value: 'Dopo' });
  assert.ok(await current.window.salvaEdit());
  assert.equal(displayed.note, 'Dopo');
  const writes = current.calls.filter(call => call.opts.method === 'PUT').length;
  await assert.rejects(current.window.dbUpdatePartial(invoice.id, { stato: 'pagata', riconciliata: true }), error => error.status === 501);
  assert.equal(displayed.stato, 'da_pagare');
  assert.equal(displayed.riconciliata, false);
  assert.equal(current.calls.filter(call => call.opts.method === 'PUT').length, writes);
  assert.equal(await current.window.dbUpdatePartial(invoice.id, { note: 'Dopo' }), Date.parse(invoice.updated_at));
});

test('installed reconciliation selects exact IDs and refreshes the statement after the server confirms', async () => {
  const invoice = { id: 'reconciled-text-id', invoice_date: '2026-10-08', total_amount: 100, amount_paid: 0, stato_pagamento: 'da_pagare' };
  const displayed = { id: invoice.id, stato: 'da_pagare', importo: 100 };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture-ricevute/riconcilia-con-estratto-conto': (_url, opts) => {
      assert.deepEqual(JSON.parse(opts.body), { fattura_id: invoice.id, movimento_id: 'real-statement-uuid' });
      Object.assign(invoice, { stato_pagamento: 'pagata', amount_paid: 100, riconciliato: true, movimento_bancario_id: 'real-statement-uuid' });
      return { success: true };
    },
  }, [displayed]);
  current.window._nonAbbinati = [{ id: 'real-statement-uuid', abbinata: false }];
  const outcome = await current.window._cfAbbina(0, invoice.id);
  assert.ok(outcome);
  assert.equal(displayed.stato, 'pagata');
  assert.equal(displayed.riconciliata, true);
  assert.equal(current.bankReloads(), 1);
  assert.equal(current.window._nonAbbinati[0].abbinata, false, 'the screen does not invent a statement match locally');
});

test('installed XML import uses multipart upload and the server-generated document ID', async () => {
  let imported = false;
  const current = await loadSemanticActions({
    '/api/invoices': () => imported ? [{ id: 'server-generated-invoice-id', invoice_date: '2026-10-08', total_amount: 100, stato_pagamento: 'da_pagare' }] : [],
    '/api/fatture/upload-xml': async (_url, opts) => {
      assert.ok(opts.body instanceof FormData);
      const file = opts.body.get('file');
      assert.equal(file.name, 'originale.xml');
      assert.match(await file.text(), /FatturaElettronica/);
      imported = true;
      return { success: true, invoice: { id: 'server-generated-invoice-id' } };
    },
  });
  const proposed = { id: 'temporary-client-id', fatturaAllegataName: 'originale.xml', fatturaAllegata: '<FatturaElettronica><DatiGeneraliDocumento/></FatturaElettronica>' };
  const rows = await current.window.dbInsert(proposed);
  assert.equal(rows[0].id, 'server-generated-invoice-id');
  assert.equal(proposed.id, 'server-generated-invoice-id');
  assert.equal(current.calls.filter(call => call.opts.method === 'POST').length, 1);
  await assert.rejects(current.window.dbInsert({ id: 'invented', importo: 100 }), error => error.status === 501);
  assert.equal(current.calls.filter(call => call.opts.method === 'POST').length, 1);
});

test('installed supplier creation uses the canonical ID and reuses an existing exact identity', async () => {
  const suppliers = [];
  const current = await loadSemanticActions({
    '/api/suppliers': (_url, opts) => {
      if (opts.method === 'POST') {
        const body = JSON.parse(opts.body);
        assert.equal(body.ragione_sociale, 'Fornitore esatto');
        assert.equal(body.id, undefined);
        suppliers.push({ id: 'supplier-server-uuid', ragione_sociale: body.ragione_sociale });
        return { id: 'supplier-server-uuid' };
      }
      return suppliers;
    },
    '/api/suppliers/supplier-server-uuid': (_url, opts) => {
      assert.deepEqual(JSON.parse(opts.body), { metodo_pagamento: 'banca' });
      suppliers[0].metodo_pagamento = 'banca'; return { success: true };
    },
  });
  assert.equal((await current.window.dbSaveForn('Fornitore esatto'))[0].id, 'supplier-server-uuid');
  await current.window.dbSaveForn('Fornitore esatto');
  assert.equal(current.calls.filter(call => call.opts.method === 'POST').length, 1);
  await current.actions.saveSupplier('Fornitore esatto', { metodo_pagamento: 'bonifico' });
  assert.deepEqual(current.window.fornitori, ['Fornitore esatto']);
});

test('installed payment confirmation retains an ambiguous proposal when the canonical service rejects it', async () => {
  const invoice = { id: 'invoice-rejected-match', invoice_date: '2026-10-08', total_amount: 100, stato_pagamento: 'da_pagare' };
  const displayed = { id: invoice.id, stato: 'da_pagare', importo: 100, riconciliata: false };
  const current = await loadSemanticActions({
    '/api/invoices': [invoice],
    '/api/fatture-ricevute/riconcilia-con-estratto-conto': new Response(JSON.stringify({ detail: 'Causale o beneficiario da verificare' }), { status: 409 }),
  }, [displayed]);
  current.window._pagDaConfermare = [{ mov: { id: 'ambiguous-statement' }, fatt: displayed }];
  assert.equal(await current.window._confermaPagamento(0, true), false);
  assert.equal(current.window._pagDaConfermare.length, 1);
  assert.equal(displayed.stato, 'da_pagare');
  assert.equal(displayed.riconciliata, false);
  assert.equal(current.bankReloads(), 0);
  assert.ok(current.messages.some(message => message.includes('da verificare')));
});

test('bank candidates remain a read-only canonical proposal with the exact invoice identity', async () => {
  const payload = { fattura_id: 'invoice-for-candidates', candidati: [{ id: 'statement-candidate', importo: 100, score: 90 }] };
  const current = await loadSemanticActions({ '/api/fatture-ricevute/candidati-bancari/invoice-for-candidates': payload });
  current.window.CeraldiBridge.canWrite = false;
  const result = await current.actions.candidates('invoice-for-candidates');
  assert.deepEqual(JSON.parse(JSON.stringify(result)), payload);
  assert.equal(current.calls.length, 1);
  assert.ok(!current.calls[0].opts.method || current.calls[0].opts.method === 'GET');
});

test('one bank movement allocates exact cents across invoices through the canonical group writer', async () => {
  const invoices = [
    { id: 'group-invoice-one', invoice_date: '2026-10-08', total_amount: 60, amount_paid: 0, stato_pagamento: 'da_pagare' },
    { id: 'group-invoice-two', invoice_date: '2026-10-08', total_amount: 40, amount_paid: 0, stato_pagamento: 'da_pagare' },
  ];
  const displayed = invoices.map(invoice => ({ id: invoice.id, stato: 'da_pagare', importo: invoice.total_amount }));
  const current = await loadSemanticActions({
    '/api/invoices': () => invoices,
    '/api/estratto-conto-movimenti/movimenti': { movimenti: [{ id: 'group-statement', data: '2026-10-08', tipo: 'uscita', importo: 100 }], totale: 1 },
    '/api/operazioni-da-confermare/smart/riconcilia-manuale': (_url, opts) => {
      const body = JSON.parse(opts.body);
      assert.deepEqual(body, { movimento_id: 'group-statement', tipo: 'fattura', associazioni: [{ id: 'group-invoice-one', quota_cents: 6000 }, { id: 'group-invoice-two', quota_cents: 4000 }] });
      invoices.forEach(invoice => Object.assign(invoice, { amount_paid: invoice.total_amount, stato_pagamento: 'pagata', riconciliato: true, movimento_bancario_id: 'group-statement' }));
      return { success: true, allocazioni: body.associazioni.map(association => ({ fattura_id: association.id, quota_cents: association.quota_cents })) };
    },
  }, displayed);
  const outcome = await current.window._applicaGruppoRiconciliazione(displayed, [{ id: 'group-statement' }]);
  assert.equal(outcome.confirmed, 1);
  assert.ok(displayed.every(invoice => invoice.stato === 'pagata' && invoice.riconciliata));
  assert.equal(current.bankReloads(), 1);
  assert.equal(current.calls.filter(call => call.opts.method === 'POST').length, 1);
});

test('groups requiring unspecified many-to-many allocations are rejected before any API call', async () => {
  const current = await loadSemanticActions({});
  await assert.rejects(current.actions.reconcileGroup([{ id: 'invoice-one' }, { id: 'invoice-two' }], [{ id: 'statement-one' }, { id: 'statement-two' }]), error => error.status === 501);
  assert.equal(current.calls.length, 0);
});

test('a partly completed group refetches the real partial payment and reports the rejected remainder', async () => {
  const invoice = { id: 'partly-reconciled-invoice', invoice_date: '2026-10-08', total_amount: 100, amount_paid: 0, stato_pagamento: 'da_pagare' };
  const displayed = { id: invoice.id, stato: 'da_pagare', importo: 100 };
  let writes = 0;
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/estratto-conto-movimenti/movimenti': { movimenti: [{ id: 'partial-statement-one', data: '2026-10-08', tipo: 'uscita', importo: 40 }, { id: 'partial-statement-two', data: '2026-10-08', tipo: 'uscita', importo: 60 }], totale: 2 },
    '/api/operazioni-da-confermare/smart/riconcilia-manuale': (_url, opts) => {
      writes++;
      if (writes === 2) return new Response(JSON.stringify({ detail: 'Secondo movimento ambiguo' }), { status: 409 });
      const body = JSON.parse(opts.body);
      Object.assign(invoice, { amount_paid: 40, stato_pagamento: 'parziale', riconciliato: true, movimento_bancario_id: 'partial-statement-one' });
      return { success: true, allocazioni: body.associazioni.map(association => ({ fattura_id: association.id, quota_cents: association.quota_cents })) };
    },
  }, [displayed]);
  await assert.rejects(current.actions.reconcileGroup([displayed], [{ id: 'partial-statement-one' }, { id: 'partial-statement-two' }]), error => error.status === 409 && error.message.includes('1 movimenti già confermati'));
  assert.equal(displayed.stato, 'parziale');
  assert.equal(displayed.parzPagato, 40);
  assert.equal(current.bankReloads(), 1);
  assert.equal(writes, 2);
});

test('single-invoice removal requests soft archival and verifies the resulting document state', async () => {
  const invoice = { id: 'soft-archive-invoice', invoice_date: '2026-10-08', total_amount: 100, stato_pagamento: 'da_pagare', status: 'imported' };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture/soft-archive-invoice': (url, opts) => {
      assert.equal(opts.method, 'DELETE');
      const params = new URL(url, 'https://gestionale.example').searchParams;
      assert.equal(params.get('force'), 'false');
      assert.equal(params.get('hard_delete'), 'false');
      invoice.status = 'archived';
      return { success: true, invoice_id: invoice.id };
    },
  }, [{ id: invoice.id, stato: 'da_pagare' }]);
  const result = await current.actions.remove(invoice.id);
  assert.equal(result.archived, true);
  assert.equal(current.window.fatture.length, 0);
  assert.equal(current.calls.at(-1).url, '/api/invoices/soft-archive-invoice');
});

test('archival warnings require a second explicit confirmation and never request hard deletion', async () => {
  const invoice = { id: 'warning-archive-invoice', invoice_date: '2026-10-08', total_amount: 100, stato_pagamento: 'da_pagare', status: 'imported' };
  const current = await loadSemanticActions({
    '/api/invoices': () => [invoice],
    '/api/fatture/warning-archive-invoice': url => {
      const params = new URL(url, 'https://gestionale.example').searchParams;
      assert.equal(params.get('hard_delete'), 'false');
      if (params.get('force') === 'false') return { status: 'warning', require_force: true, warnings: ['La fattura ha due scritture collegate'], entita_correlate: { totale_entita: 2 } };
      assert.equal(params.get('force'), 'true');
      invoice.status = 'archived'; return { success: true, invoice_id: invoice.id };
    },
  }, [{ id: invoice.id, fornitore: 'Fornitore Uno', numero: 'F/1', stato: 'da_pagare' }]);
  const answers = [true, false, true, true], prompts = [];
  current.window.confirm = text => { prompts.push(text); return answers.shift(); };
  assert.equal((await current.window.askDel(invoice.id)).cancelled, true);
  assert.equal(current.window.fatture.length, 1);
  assert.equal(current.calls.filter(call => call.opts.method === 'DELETE').length, 1);
  assert.match(prompts[1], /La fattura ha due scritture collegate/);
  assert.match(prompts[1], /Entità collegate: 2/);
  assert.equal((await current.window.askDel(invoice.id)).archived, true);
  assert.equal(current.window.fatture.length, 0);
  const deletes = current.calls.filter(call => call.opts.method === 'DELETE');
  assert.deepEqual(deletes.map(call => new URL(call.url, 'https://gestionale.example').searchParams.get('force')), ['false', 'false', 'true']);
  assert.ok(deletes.every(call => new URL(call.url, 'https://gestionale.example').searchParams.get('hard_delete') === 'false'));
});

test('fiscal electronic receipts do not invent a terminal closure or bank credit', async () => {
  const bridge = await loadDataAdapter();
  const { api } = apiFixture({ '/api/corrispettivi': [
    { id: 'rt-one', data: '2026-10-08', totale: 100, pagato_contanti: 20, pagato_elettronico: 80 },
    { id: 'rt-two', data: '2026-10-08', totale: 50, pagato_contanti: 10, pagato_elettronico: 40 },
  ], '/api/pos-corrispettivi/controllo-due-fasi': { success: true, giorni: [{ data: '2026-10-08', pos_per_circuito: { numia: 15, sumup: null }, fonte_pos_per_circuito: { numia: 'estratto_conto_numia' }, numero_movimenti_banca: 1, accredito_banca: 15, riconciliato_banca_reale: false }] } });
  const response = await bridge.request('chiusure_giornaliere?select=data,corrispettivo_ids,totale_corrispettivi,cassa,pos,pos_numia,numia_ricostruito_da_banca,pos_banca,pos_riconciliata', {}, api);
  assert.equal(response.status, 200);
  const rows = await response.json();
  assert.equal(rows.length, 1, 'the legacy daily closure explicitly groups the fiscal records by date');
  assert.deepEqual(rows[0].corrispettivo_ids, ['rt-one', 'rt-two']);
  assert.equal(rows[0].totale_corrispettivi, 150);
  assert.equal(rows[0].cassa, 30);
  for (const row of rows) {
    assert.equal(row.pos, null);
    assert.equal(row.pos_numia, null);
    assert.equal(row.numia_ricostruito_da_banca, 15);
    assert.equal(row.pos_banca, 15);
    assert.equal(row.pos_riconciliata, false);
  }
});

test('operational files have no old Supabase project, client key, or runtime reference imports', async () => {
  const files = ['primanota-ceraldi.html', 'ceraldi-bridge.js', 'ceraldi-bridge-data.js', 'ceraldi-bridge-actions.js', 'ceraldi-fiscale.js', 'ceraldi-paghe.js', 'ceraldi-menu.js', 'ceraldi-automazioni.js'];
  for (const file of files) {
    const source = await fs.readFile(path.join(publicDir, file), 'utf8');
    assert.doesNotMatch(source, /qaqqptpprmfjlolordaq|\.supabase\.co|eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9|supabase\.createClient|@supabase\/supabase-js/, file);
    assert.doesNotMatch(source, /(?:src|href)\s*=\s*["'][^"']*reference\/ceraldi|import\s*\([^)]*automazioni-originali|import[^;]*automazioni-originali/, file);
  }
});
