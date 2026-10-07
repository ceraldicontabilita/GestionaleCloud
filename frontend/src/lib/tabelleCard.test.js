import { describe, it, expect, beforeEach } from 'vitest';
import { adattaTabella, BREAKPOINT_CARD, ciSta, etichettaTabella, FATTORE_LEGGIBILITA } from './tabelleCard';

describe('ciSta: tabella o card misurato sullo spazio, non sul dispositivo', () => {
  it('sotto il telefono e\' sempre card, anche se ci starebbe', () => {
    expect(ciSta({ disponibile: 700, minima: 300, finestra: BREAKPOINT_CARD })).toBe(false);
  });

  it('su tablet e desktop conta solo lo spazio: ci sta con un po\' d\'aria oltre il minimo', () => {
    // iPad con la colonna a sinistra (07/10/2026): 930 px per una tabella larga 850 al minimo
    expect(ciSta({ disponibile: 930, minima: 850, finestra: 1194 })).toBe(false);
    expect(ciSta({ disponibile: 1098, minima: 850, finestra: 1366 })).toBe(true);
    expect(ciSta({ disponibile: Math.ceil(300 * FATTORE_LEGGIBILITA), minima: 300, finestra: 1024 })).toBe(true);
    expect(ciSta({ disponibile: 300, minima: 300, finestra: 1024 })).toBe(false);
  });

  it('senza misura non decide: resta tabella', () => {
    expect(ciSta({ disponibile: 0, minima: 0, finestra: 1024 })).toBe(true);
  });
});

describe('adattaTabella', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('sotto il telefono marca la tabella stretta senza misurare; sopra, senza misura, la lascia tabella', () => {
    document.body.innerHTML = '<div><table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></div>';
    const t = document.querySelector('table');
    etichettaTabella(t);
    adattaTabella(t, 390);
    expect(t.dataset.stretta).toBe('');
    // jsdom non ha layout: clientWidth 0 = nessuna misura, quindi tabella
    adattaTabella(t, 1366);
    expect(t.dataset.stretta).toBeUndefined();
    expect(t.style.width).toBe('');
  });

  it('non tocca una tabella non etichettata o con data-card="no"', () => {
    document.body.innerHTML = '<div><table data-card="no"><tr><td>1</td></tr></table></div>';
    const t = document.querySelector('table');
    adattaTabella(t, 390);
    expect(t.dataset.stretta).toBeUndefined();
  });
});

const monta = html => {
  document.body.innerHTML = html;
  return document.querySelector('table');
};

describe('etichettaTabella', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('copia le intestazioni nei td e marca la tabella come card', () => {
    const t = monta(`<table><thead><tr><th>Data</th><th>Importo</th></tr></thead>
      <tbody><tr><td>01/10</td><td>5,00</td></tr></tbody></table>`);
    etichettaTabella(t);
    expect(t.dataset.card).toBe('si');
    const td = t.querySelectorAll('tbody td');
    expect(td[0].dataset.label).toBe('Data');
    expect(td[1].dataset.label).toBe('Importo');
  });

  it('una riga con colspan (nessun dato) non riceve etichetta', () => {
    const t = monta(`<table><thead><tr><th>A</th><th>B</th></tr></thead>
      <tbody><tr><td colspan="2">Nessun dato</td></tr></tbody></table>`);
    etichettaTabella(t);
    expect(t.querySelector('td').dataset.label).toBeUndefined();
  });

  it('intestazione a più livelli: etichetta = cella più in basso, il gruppo solo dove non c\'è altro', () => {
    const t = monta(`<table><thead>
      <tr><th rowspan="2">Data</th><th colspan="2">Registratore</th></tr>
      <tr><th>Corrispettivo</th><th>Elettronico</th></tr></thead>
      <tbody><tr><td>01/01</td><td>10</td><td>20</td></tr></tbody></table>`);
    etichettaTabella(t);
    expect(t.dataset.card).toBe('si');
    const td = t.querySelectorAll('tbody td');
    expect([...td].map(c => c.dataset.label)).toEqual(['Data', 'Corrispettivo', 'Elettronico']);
  });

  it('colspan nell\'intestazione senza foglia: etichetta del gruppo; data-card="no" resta com\'è', () => {
    const span = monta(`<table><thead><tr><th colspan="2">A</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>`);
    etichettaTabella(span);
    expect(span.querySelectorAll('td')[1].dataset.label).toBe('A');
    const no = monta(`<table data-card="no"><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>`);
    etichettaTabella(no);
    expect(no.querySelector('td').dataset.label).toBeUndefined();
  });

  it('tabella senza thead con prima riga di th', () => {
    const t = monta(`<table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr></table>`);
    etichettaTabella(t);
    expect(t.rows[1].cells[1].dataset.label).toBe('Y');
    expect(t.rows[0].cells[0].dataset.label).toBeUndefined();
  });

  it('tabella senza intestazione con poche colonne: pila chiave-valore; con molte colonne resta com\'e\'', () => {
    const kv = monta(`<table><tbody><tr><td>Cassa</td><td>10,00</td></tr><tr><td>Banca</td><td>5,00</td></tr></tbody></table>`);
    etichettaTabella(kv);
    expect(kv.dataset.card).toBe('si');
    expect(kv.dataset.chiaveValore).toBeDefined();
    const larga = monta(`<table><tbody><tr><td>1</td><td>2</td><td>3</td><td>4</td></tr></tbody></table>`);
    etichettaTabella(larga);
    expect(larga.dataset.card).toBeUndefined();
  });
});
