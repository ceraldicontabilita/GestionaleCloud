import { describe, it, expect, beforeEach } from 'vitest';
import { etichettaTabella } from './tabelleCard';

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

  it('intestazione a più livelli: conserva gruppo e colonna per non confondere gli importi', () => {
    const t = monta(`<table><thead>
      <tr><th rowspan="2">Data</th><th colspan="2">Registratore</th></tr>
      <tr><th>Corrispettivo</th><th>Elettronico</th></tr></thead>
      <tbody><tr><td>01/01</td><td>10</td><td>20</td></tr></tbody></table>`);
    etichettaTabella(t);
    expect(t.dataset.card).toBe('si');
    const td = t.querySelectorAll('tbody td');
    expect([...td].map(c => c.dataset.label)).toEqual(['Data', 'Registratore · Corrispettivo', 'Registratore · Elettronico']);
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

// Lo stesso markup vive in HR, nei riepiloghi con 13ª/14ª e nelle finestre ERP.
describe('righe complete delle mini app', () => {
  it('mantiene distinte 13ª e 14ª, con totali e controlli ancora nello stesso DOM', () => {
    const t = monta(`<table class="dc-table--cards"><thead>
      <tr><th rowspan="2">Dipendente</th><th colspan="2">13ª 2026</th><th colspan="2">14ª 2026</th></tr>
      <tr><th>Busta €</th><th>Pagato €</th><th>Busta €</th><th>Pagato €</th></tr></thead>
      <tbody><tr><td>Persona prova</td><td>1000</td><td>800</td><td>900</td><td><button>Gestisci</button></td></tr></tbody>
      <tfoot><tr><td colspan="3">Totale</td><td>900</td><td>0</td></tr></tfoot></table>`);
    const button = t.querySelector('button');
    etichettaTabella(t);
    expect([...t.tBodies[0].rows[0].cells].map(c => c.dataset.label)).toEqual(
      ['Dipendente', '13ª 2026 · Busta €', '13ª 2026 · Pagato €', '14ª 2026 · Busta €', '14ª 2026 · Pagato €']);
    expect(t.tFoot.rows[0].cells[1].dataset.label).toBe('14ª 2026 · Busta €');
    expect(t.querySelector('button')).toBe(button);
  });
  it('riporta il contesto delle celle unite sulle righe successive senza spostare gli importi', () => {
    const t = monta(`<table><thead><tr><th>Dipendente</th><th>Data</th><th>Importo</th></tr></thead>
      <tbody><tr><th rowspan="2">Persona prova</th><td>Gennaio</td><td>700</td></tr>
      <tr><td>Febbraio</td><td>800</td></tr><tr><td>Altra persona</td><td>Marzo</td><td>900</td></tr></tbody></table>`);
    etichettaTabella(t);
    expect(t.tBodies[0].rows[1].dataset.cardContext).toBe('Persona prova');
    expect([...t.tBodies[0].rows[1].cells].map(c => c.dataset.label)).toEqual(['Data','Importo']);
    expect(t.tBodies[0].rows[2].dataset.cardContext).toBeUndefined();
  });
});
