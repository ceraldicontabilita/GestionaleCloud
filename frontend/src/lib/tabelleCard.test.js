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
