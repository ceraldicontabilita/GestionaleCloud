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

function prepara(p){
 p.imposta('sess',{r:'alb',s:'hotel-a',p:'token-a'});
 p.imposta('PCK',{contesto:'alb',sid:'hotel-a',dati:{offerta,pacchetti:[{id:'pack-1',qta:1000,consumate:1,residue:999}]}});
}
const dettaglio=(ids,prossimo=null)=>({id:'pack-1',qta:1000,consumate:1,residue:999,offerta,
 vouchers:ids.map(id=>({id,qta:1,usate:0,annullato:false})),prossimo,limite:50});

test('il cruscotto richiede soltanto i tre conteggi e non carica elenchi o QR',async()=>{
 const p=pagina();prepara(p);const calls=[];
 p.context.__rpc=async(name,args)=>{calls.push({name,args:normale(args)});return{qta:1000,consumate:1,residue:999}};
 p.esegui('rpc=__rpc');await p.esegui('pacchettiRiepilogo("alb")');
 assert.deepEqual(calls,[{name:'bb_alb_pacchetti_totali',args:{sid:'hotel-a',p:'token-a'}}]);
 assert.match(p.element('#package_summary').innerHTML,/>1000</);
 assert.match(p.element('#package_summary').innerHTML,/>999</);
 p.imposta('sess',{r:'tit',p:'token-bar'});await p.esegui('pacchettiRiepilogo("tit")');
 assert.deepEqual(calls[1],{name:'bb_tit_pacchetti_totali',args:{p:'token-bar'}});
});

test('aprire un pacchetto da 1000 QR carica una sola pagina di 50 e prosegue dal cursore',async()=>{
 const p=pagina();prepara(p);const calls=[];
 p.context.__rpc=async(name,args)=>{calls.push({name,args:normale(args)});return args.pdopo?dettaglio(['QR051']):dettaglio(Array.from({length:50},(_,i)=>'QR'+String(i+1).padStart(3,'0')),'QR050')};
 p.esegui('rpc=__rpc');
 assert.equal(calls.length,0);
 await p.esegui('pacchettoApri("pack-1")');
 assert.deepEqual(calls,[{name:'bb_alb_pacchetto_dettaglio',args:{sid:'hotel-a',p:'token-a',pid:'pack-1',pdopo:null,plimite:50}}]);
 assert.equal(p.esegui('pacchettoCorrente().vouchers.length'),50);
 assert.match(p.element('#pk_detail').innerHTML,/data-pk-after="QR050"/);
 assert.doesNotMatch(p.element('#pk_detail').innerHTML,/QR051/);
 await p.esegui('pacchettoApri("pack-1","QR050")');
 assert.equal(calls.length,2);assert.equal(calls[1].args.pdopo,'QR050');
 assert.deepEqual(normale(p.esegui('pacchettoCorrente().vouchers.map(v=>v.id)')),['QR051']);
 assert.match(p.element('#pk_detail').innerHTML,/Torna ai primi QR/);
});

test('il dettaglio del titolare usa la RPC protetta senza pretendere la sessione hotel',async()=>{
 const p=pagina();prepara(p);p.imposta('sess',{r:'tit',p:'token-bar'});p.esegui('PCK.contesto="tit"');const calls=[];
 p.context.__rpc=async(name,args)=>{calls.push({name,args:normale(args)});return dettaglio(['QR001'])};
 p.esegui('rpc=__rpc');await p.esegui('pacchettoApri("pack-1")');
 assert.deepEqual(calls,[{name:'bb_tit_pacchetto_dettaglio',args:{p:'token-bar',pid:'pack-1',pdopo:null,plimite:50}}]);
});

test('una risposta QR tardiva non mostra dati dopo il passaggio a un altro albergatore',async()=>{
 const p=pagina();prepara(p);let resolve;
 p.context.__rpc=()=>new Promise(r=>{resolve=r});p.esegui('rpc=__rpc');
 const task=p.esegui('pacchettoApri("pack-1")');
 p.imposta('sess',{r:'alb',s:'hotel-b',p:'token-b'});p.esegui('PCK.sid="hotel-b";PCK.aperto=null');
 p.element('#pk_detail').innerHTML='Vista B';resolve(dettaglio(['RISERVATO-A']));await task;
 assert.equal(p.element('#pk_detail').innerHTML,'Vista B');
 assert.equal(p.esegui('pacchettoCorrente()'),null);
});

test('stampa ed esportazione caricano tutte le pagine soltanto dopo il comando esplicito',async()=>{
 const p=pagina();prepara(p);const calls=[],printed=[],downloaded=[];
 p.context.__rpc=async(name,args)=>{calls.push(normale(args));return args.pdopo?dettaglio(['QR003']):dettaglio(['QR001','QR002'],'QR002')};
 p.context.__stampa=rows=>printed.push(normale(rows));p.context.__download=(name,content)=>downloaded.push({name,content});
 p.esegui('rpc=__rpc;stampa=__stampa;download=__download');await p.esegui('pacchettoApri("pack-1")');
 assert.equal(calls.length,1);assert.equal(printed.length,0);assert.equal(downloaded.length,0);
 await p.esegui('pacchettoStampa()');
 assert.equal(calls.length,3);assert.deepEqual(printed[0].map(x=>x.codice),['QR001','QR002','QR003']);
 assert.deepEqual(calls.slice(1).map(x=>[x.plimite,x.pdopo]),[[100,null],[100,'QR002']]);
 await p.esegui('pacchettoEsporta()');assert.equal(downloaded.length,1);
 assert.match(downloaded[0].content,/QR003/);assert.match(downloaded[0].content,/#\/ospite\/QR003/);
});

test('il guasto di una pagina QR offre un nuovo tentativo senza avviare acquisti o consegne',async()=>{
 const p=pagina();prepara(p);const calls=[];
 p.context.__rpc=async(name)=>{calls.push(name);throw Error('Rete interrotta')};p.esegui('rpc=__rpc');
 await p.esegui('pacchettoApri("pack-1")');
 assert.deepEqual(calls,['bb_alb_pacchetto_dettaglio']);
 assert.match(p.element('#pk_detail').innerHTML,/Rete interrotta/);
 assert.match(p.element('#pk_detail').innerHTML,/data-pk-action="open"/);
});
