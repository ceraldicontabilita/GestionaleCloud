/**
 * Comportamento della pagina reale, senza servizi esterni.
 * Eseguire con: node --test tests/colazioni/pacchetti_ui.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { createContext, runInContext } from 'node:vm';

const html = readFileSync(new URL('../../frontend_colazioni/index.html', import.meta.url), 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'))
  .replace(/\nrender\(\);\s*$/, '\n');
const offerta = {
  nome: 'Colazione B&B €4', prezzo: 4, acquistabile: true, abilitata: true,
  formule: [
    { codice: 'classica', nome: 'Italiana classica', prodotti: [{ id: 152788, nome: 'Croissant' }] },
    { codice: 'napoletana', nome: 'Dolce napoletana', prodotti: [{ id: 153867, nome: 'Sfogliatella frolla' }] },
    { codice: 'salata', nome: 'Colazione salata', prodotti: [{ id: 153886, nome: 'Parigina' }] },
  ],
  bevande: [{ id: 153756, nome: 'Espresso', tipo: 'calda' }, { id: 153754, nome: 'Cappuccino', tipo: 'calda' },
    { id: 153895, nome: 'Acqua 33 cl', tipo: 'fredda' }, { id: 153898, nome: 'Coca-Cola', tipo: 'fredda' }],
  vincoli: { parigina_prodotto_id: 153886, parigina_bevanda_id: 153895 },
  regole: ['Un prodotto e una sola bevanda a scelta.'],
};
const buono = () => ({ id: 'ABC123', pacchetto_id: 'pack-1', qta: 1, usate: 0, annullato: false, struttura: 'B&B Test', offerta,
  scelta: null, bar: { bar_nome: 'Ceraldi Caffè' } });
const normale = value => JSON.parse(JSON.stringify(value));

function pagina(storage = new Map()) {
  const elements = new Map();
  const events = [];
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      value: '', innerHTML: '', textContent: '', hidden: false, disabled: false,
      style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {} },
      querySelectorAll() { return []; }, querySelector() { return null; },
      appendChild() {}, remove() {}, focus() {}, scrollIntoView() {},
      addEventListener() {}, setAttribute() {},
    });
    return elements.get(selector);
  };
  const context = createContext({
    console, URL, URLSearchParams, Date, JSON, Math, Promise,
    setTimeout, clearTimeout, setInterval, clearInterval,
    crypto: { randomUUID: () => `richiesta-${events.length + 1}` },
    location: { href: 'https://esempio.test/convenzioni/', hash: '' },
    navigator: { clipboard: { writeText: async () => {} } },
    sessionStorage: { getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)), removeItem: key => storage.delete(key) },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {}, confirm: () => true,
    document: { querySelector: element, querySelectorAll: () => [],
      getElementById: id => element(`#${id}`), createElement: () => element(`new-${elements.size}`),
      body: { appendChild() {}, dataset: {} } },
    fetch: async () => { throw new Error('Rete vietata nel collaudo UI'); },
  });
  context.window = context;
  runInContext(script, context, { filename: 'frontend_colazioni/index.html' });
  runInContext('toast = messaggio => __eventi.push(messaggio)', Object.assign(context, { __eventi: events }));
  return { context, element, events, storage,
    esegui: codice => runInContext(codice, context),
    imposta: (nome, valore) => { context.__dato = valore; runInContext(`${nome} = __dato`, context); },
  };
}

test('il QR mantiene il collegamento ospite pubblico, riconoscibile dallo scanner', () => {
  const p = pagina();
  const link = p.esegui('linkOspite("ABC123")');
  assert.equal(link, 'https://esempio.test/convenzioni/#/ospite/ABC123');
  p.context.__link = link;
  assert.equal(p.esegui('codiceDaScan(__link)'), 'ABC123');
});

test('le tre quantità restano distinte e si sommano anche se serializzate come testo', () => {
  const p = pagina();
  p.context.__lista = [{ qta: '10', consumate: '2', residue: '8' }, { qta: 5, consumate: 3, residue: 2 }];
  assert.deepEqual(normale(p.esegui('pacchettiTotali(__lista)')), { qta: 15, consumate: 5, residue: 10 });
  assert.deepEqual(normale(p.esegui('pacchettiTotali([])')), { qta: 0, consumate: 0, residue: 0 });
});

test('scegliere la parigina toglie altre bevande; cambiare formula azzera la scelta precedente', () => {
  const p = pagina();
  p.context.__buono = buono();
  p.esegui('PVIEWS.guest=pacchettoVista(__buono)');
  p.esegui('pacchettoScegli("guest","formula","classica");pacchettoScegli("guest","prodotto","152788");pacchettoScegli("guest","bevanda","153898")');
  assert.equal(p.esegui('pacchettoSceltaValida(PVIEWS.guest)'), true);
  p.esegui('pacchettoScegli("guest","formula","salata");pacchettoScegli("guest","prodotto","153886")');
  assert.equal(p.esegui('PVIEWS.guest.bevanda'), '');
  assert.deepEqual(normale(p.esegui('pacchettoBevande(PVIEWS.guest.d.offerta,PVIEWS.guest.prodotto).map(b=>b.id)')), [153895]);
  p.esegui('pacchettoScegli("guest","bevanda","153898")');
  assert.equal(p.esegui('pacchettoSceltaValida(PVIEWS.guest)'), false);
  p.esegui('pacchettoScegli("guest","bevanda","153895")');
  assert.equal(p.esegui('pacchettoSceltaValida(PVIEWS.guest)'), true);
  p.esegui('pacchettoScegli("guest","formula","napoletana")');
  assert.deepEqual(normale(p.esegui('[PVIEWS.guest.prodotto,PVIEWS.guest.bevanda]')), ['', '']);
});

test('l’ospite apre soltanto il proprio buono senza sessione o account e non esegue il riscatto', async () => {
  const p = pagina();
  const calls = [];
  p.context.__rpc = async (name, args) => { calls.push({ name, args: normale(args) }); return buono(); };
  p.esegui('rpc=__rpc');
  await p.esegui('ospite("ABC123")');
  assert.equal(p.esegui('sess'), null);
  assert.deepEqual(calls, [{ name: 'bb_ospite', args: { vid: 'ABC123' } }]);
  assert.match(p.element('#app').innerHTML, /Un prodotto e una sola bevanda/);
  assert.doesNotMatch(p.element('#app').innerHTML, /password|type="password"|Saldo borsellino/);
});

test('il probe del QR pacchetto è in sola lettura; il doppio click non avvia due verifiche', async () => {
  const p = pagina();
  const calls = [];
  let finish;
  p.imposta('sess', { p: 'tk:bar', r: 'tit' });
  p.context.__rpc = (name, args) => { calls.push({ name, args: normale(args) }); return new Promise(resolve => { finish = resolve; }); };
  p.esegui('rpc=__rpc');
  const first = p.esegui('doScan("ABC123")');
  const duplicate = p.esegui('doScan("ABC123")');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, 'bb_tit_pacchetto_voucher');
  finish(buono());
  await Promise.all([first, duplicate]);
  assert.equal(calls.length, 1);
  assert.match(p.element('#scr').innerHTML, /Conferma una consegna/);
});

test('il banco conferma scelta e consegna con una sola chiamata atomica, anche con doppio click', async () => {
  const p = pagina();
  const calls = [];
  let finish;
  p.imposta('sess', { p: 'tk:bar', r: 'tit' });
  p.context.__buono = buono();
  p.esegui('PVIEWS.scan=pacchettoVista(__buono);PVIEWS.scan.formula="classica";PVIEWS.scan.prodotto="152788";PVIEWS.scan.bevanda="153754"');
  p.context.__rpc = (name, args) => { calls.push({ name, args: normale(args) }); return new Promise(resolve => { finish = resolve; }); };
  p.esegui('rpc=__rpc');
  const first = p.esegui('consegnaPacchetto()');
  const duplicate = p.esegui('consegnaPacchetto()');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, 'bb_tit_pacchetto_consegna');
  assert.deepEqual(calls[0].args, { p: 'tk:bar', vid: 'ABC123', pformula: 'classica', pprodotto: 152788, pbevanda: 153754 });
  finish({ ok: true, msg: 'Colazione consegnata', pacchetto: { qta: 3, consumate: 1, residue: 2 },
    voucher: { id: 'ABC123', pacchetto_id: 'pack', qta: 1, usate: 1, struttura: 'B&B Test', voci: [{ nome: 'Croissant' }, { nome: 'Cappuccino' }] } });
  await Promise.all([first, duplicate]);
  assert.equal(calls.length, 1);
  assert.equal(p.esegui('PVIEWS.scan'), null);
  assert.match(p.element('#scr').innerHTML, /Da consumare/);
});

function acquistoPronto(p) {
  p.imposta('sess', { p: 'tk:hotel', s: 'hotel-1', r: 'alb' });
  p.imposta('ALB', { struttura: { id: 'hotel-1', nome: 'B&B Test', saldo: 100 } });
  p.imposta('PCK', { contesto: 'alb', sid: 'hotel-1', dati: { offerta, strutture_abilitate: ['hotel-1'], pacchetti: [] }, richiesta: null, inviando: false });
  p.element('#pk_qta').value = '10';
  p.esegui('pacchettiCarica=async()=>{};pacchettoApri=()=>{}');
}

test('un acquisto con esito incerto conserva la stessa idempotenza al retry e non riparte durante l’invio', async () => {
  const p = pagina();
  acquistoPronto(p);
  const calls = [];
  let firstResolve;
  p.context.__rpc = (name, args) => {
    calls.push({ name, args: normale(args) });
    if (calls.length === 1) return new Promise((resolve, reject) => { firstResolve = () => reject(new Error('Connessione interrotta')); });
    return Promise.resolve({ ok: true, pacchetto: { id: 'pack-1' }, saldo: 60 });
  };
  p.esegui('rpc=__rpc');
  const first = p.esegui('pacchettoAcquista()');
  await p.esegui('pacchettoAcquista()');
  assert.equal(calls.length, 1);
  firstResolve();
  await first;
  const originalId = calls[0].args.pidempotenza;
  assert.equal(p.esegui('PCK.richiesta.id'), originalId);
  await p.esegui('pacchettoAcquista()');
  assert.equal(calls.length, 2);
  assert.equal(calls[1].args.pidempotenza, originalId);
  assert.equal(p.esegui('PCK.richiesta'), null);
  assert.equal(p.esegui('ALB.struttura.saldo'), 60);
});

test('offerta disabilitata blocca l’acquisto UI ma i QR già acquistati restano stampabili dallo snapshot', async () => {
  const p = pagina();
  acquistoPronto(p);
  p.esegui('PCK.dati.offerta={nome:"Colazione B&B",prezzo:4,acquistabile:false,abilitata:false,motivo:"Offerta non attiva"};PCK.dati.strutture_abilitate=[]');
  let requests = 0;
  p.context.__rpc = async () => { requests++; };
  p.esegui('rpc=__rpc;pacchettoCosto()');
  assert.equal(p.element('#pk_buy').disabled, true);
  await p.esegui('pacchettoAcquista()');
  assert.equal(requests, 0);
  p.context.__pack = { id: 'pack-1', struttura: 'B&B Test', offerta, vouchers: [buono()] };
  const card = p.esegui('pacchettoScheda(__pack,__pack.vouchers[0])');
  assert.match(card.sopra, /Colazione B&B €4/);
  assert.equal(card.qr, 'https://esempio.test/convenzioni/#/ospite/ABC123');
});

test('il refresh riprende lo stesso acquisto incerto anche con saldo ormai speso e offerta disabilitata', async () => {
  const first = pagina();
  acquistoPronto(first);
  const attempts = [];
  first.context.__rpc = async (name, args) => {
    attempts.push(normale(args));
    throw new Error('Risposta persa dopo l’addebito');
  };
  first.esegui('rpc=__rpc');
  await first.esegui('pacchettoAcquista()');
  const request = first.esegui('pacchettoRichiestaPendente()');
  assert.equal(request.id, attempts[0].pidempotenza);

  const refreshed = pagina(first.storage);
  assert.equal(refreshed.esegui('PCK.richiesta.id'), request.id);
  acquistoPronto(refreshed);
  refreshed.esegui('ALB.struttura.saldo=0;PCK.dati.offerta={...PCK.dati.offerta,acquistabile:false,abilitata:false}');
  refreshed.context.__rpc = async (name, args) => {
    attempts.push(normale(args));
    return { ok: true, ripetuta: true, pacchetto: { id: 'pack-gia-pagato' }, saldo: 0 };
  };
  refreshed.esegui('rpc=__rpc;pacchettoCosto()');
  assert.equal(refreshed.element('#pk_buy').disabled, false);
  await refreshed.esegui('pacchettoAcquista()');
  assert.equal(attempts.length, 2);
  assert.equal(attempts[1].pidempotenza, request.id);
  assert.equal(refreshed.esegui('pacchettoRichiestaPendente()'), null);
});

test('un rifiuto SQL certo libera la richiesta; un errore di rete impedisce di cambiare quantità', async () => {
  const p = pagina();
  acquistoPronto(p);
  let calls = 0;
  p.context.__rpc = async () => {
    calls++;
    const error = new Error('Saldo insufficiente');
    if (calls === 1) error.esitoNoto = true;
    throw error;
  };
  p.esegui('rpc=__rpc');
  await p.esegui('pacchettoAcquista()');
  assert.equal(p.esegui('pacchettoRichiestaPendente()'), null);
  await p.esegui('pacchettoAcquista()');
  assert.ok(p.esegui('pacchettoRichiestaPendente()'));
  p.element('#pk_qta').value = '20';
  await p.esegui('pacchettoAcquista()');
  assert.equal(calls, 2);
  p.esegui('pacchettoNuovaRichiesta()');
  assert.equal(p.element('#pk_qta').value, 10);
});

test('un errore di sessione al retry non cancella il riferimento del primo acquisto dall’esito incerto', async () => {
  const first = pagina();
  acquistoPronto(first);
  const attempts = [];
  first.context.__rpc = async (name, args) => {
    attempts.push(normale(args));
    throw new Error('Timeout dopo il possibile addebito');
  };
  first.esegui('rpc=__rpc');
  await first.esegui('pacchettoAcquista()');
  const requestId = attempts[0].pidempotenza;

  const refreshed = pagina(first.storage);
  acquistoPronto(refreshed);
  refreshed.context.__rpc = async (name, args) => {
    attempts.push(normale(args));
    const error = new Error('Sessione albergatore scaduta');
    error.esitoNoto = true;
    error.code = 'P0001';
    throw error;
  };
  refreshed.esegui('rpc=__rpc');
  await refreshed.esegui('pacchettoAcquista()');
  assert.equal(refreshed.esegui('pacchettoRichiestaPendente().id'), requestId);
  refreshed.esegui('sess.p="tk:nuova-sessione"');
  refreshed.context.__ripresa = async (name, args) => {
    attempts.push(normale(args));
    return { ok: true, ripetuta: true, pacchetto: { id: 'primo-acquisto-committato' }, saldo: 60 };
  };
  refreshed.esegui('rpc=__ripresa');
  await refreshed.esegui('pacchettoAcquista()');
  assert.equal(attempts.length, 3);
  assert.ok(attempts.every(args => args.pidempotenza === requestId));
  assert.equal(attempts[2].p, 'tk:nuova-sessione');
  assert.equal(refreshed.esegui('pacchettoRichiestaPendente()'), null);
});

test('un rifiuto business dopo il lookup idempotente risolve anche una richiesta precedentemente incerta', async () => {
  for (const code of ['PBB01', 'PBB02', 'PBB03']) {
    const p = pagina();
    acquistoPronto(p);
    const calls = [];
    p.context.__rpc = async (name, args) => {
      calls.push(normale(args));
      if (calls.length === 1) throw new Error('Risposta persa');
      const error = new Error('Acquisto rifiutato definitivamente');
      error.esitoNoto = true;
      error.code = code;
      throw error;
    };
    p.esegui('rpc=__rpc');
    await p.esegui('pacchettoAcquista()');
    assert.ok(p.esegui('pacchettoRichiestaPendente()'));
    await p.esegui('pacchettoAcquista()');
    assert.equal(calls.length, 2);
    assert.equal(calls[1].pidempotenza, calls[0].pidempotenza);
    assert.equal(p.esegui('pacchettoRichiestaPendente()'), null, code);
    assert.equal(p.element('#pk_qta').disabled, false, code);
  }
});

