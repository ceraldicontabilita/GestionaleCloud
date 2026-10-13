import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';
import Scadenze from './Scadenze';
const context = vi.hoisted(() => ({ anno: 2026 }));
vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), defaults: {baseURL: ''} } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => context }));
vi.mock('../components/ui/ConfirmDialog', () => ({useConfirm: () => vi.fn().mockResolvedValue(true)}));
vi.mock('../components/ModalFattura', () => ({default: () => null}));
vi.mock('sonner', () => ({toast: {error: vi.fn(), success: vi.fn()}}));
afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); context.anno = 2026; });
const row = (descrizione, extra = {}) => ({id: 'n1', source: 'custom', tipo: 'CUSTOM', data:'2026-10-20', descrizione, importo_cents:10000, giorni_mancanti:7, ...extra});
const response = (rows, extra={}) => ({data:{scadenze:rows, totale:rows.length, ...extra}});
const page = () => <MemoryRouter><Scadenze /></MemoryRouter>;

it('ignora una risposta del vecchio anno arrivata dopo quella corrente', async () => {
  let oldResolve, currentResolve;
  const old = new Promise(resolve => {oldResolve = resolve;});
  const current = new Promise(resolve => {currentResolve = resolve;});
  context.anno = 2025;
  api.get.mockImplementation(url => url.includes('anno=2025') ? old : current);
  const view = render(page());
  context.anno = 2026; view.rerender(page());
  await act(async () => currentResolve(response([row('Corretta 2026')])));
  await act(async () => oldResolve(response([row('Superata 2025')])));
  expect(screen.getByText('Corretta 2026')).toBeInTheDocument();
  expect(screen.queryByText('Superata 2025')).not.toBeInTheDocument();
});
it('ignora carica altre del vecchio filtro e usa una sola API', async () => {
  let moreResolve;
  api.get.mockImplementation(url => {
    if (url.includes('offset=1')) return new Promise(resolve => {moreResolve=resolve;});
    if (url.includes('stato=chiuse')) return Promise.resolve(response([row('Pagata corrente',{completata:true})]));
    return Promise.resolve(response([row('Aperta vecchia')],{totale:2}));
  });
  render(page());
  fireEvent.click(await screen.findByRole('button',{name:'Carica altre scadenze'}, {timeout:5000}));
  fireEvent.change(screen.getByLabelText('Stato'),{target:{value:'chiuse'}});
  await screen.findByText('Pagata corrente');
  await act(async () => moreResolve(response([row('Altra vecchia')],{totale:2})));
  expect(screen.queryByText('Altra vecchia')).not.toBeInTheDocument();
  expect(api.get.mock.calls.every(([url])=>url.startsWith('/api/scadenze/tutte?'))).toBe(true);
});
it('una completata non espone nuovamente completa', async () => {
  api.get.mockResolvedValue(response([row('Completata già',{completata:true})]));
  render(page()); await screen.findByText('Completata già');
  expect(screen.queryByRole('button',{name:'Segna come completata'})).not.toBeInTheDocument();
});
it('mostra ricevute e cartelle pendenti anche senza verbali o scadenze', async () => {
  api.get.mockResolvedValue(response([],{documenti_da_verificare:[
    {id:'ricevute',titolo:'Ricevute da associare',conteggio:3,url:'/riconciliazione/pagopa'},
    {id:'cartelle',titolo:'Cartelle da verificare',conteggio:2,url:'/situazione-fiscale/ader'},
  ]}));
  render(page());
  expect(await screen.findByRole('link',{name:'Cartelle da verificare: 2'})).toHaveAttribute('href','/situazione-fiscale/ader');
  expect(screen.getByRole('link',{name:'Ricevute da associare: 3'})).toHaveAttribute('href','/riconciliazione/pagopa');
  expect(screen.getByText('Archivio completo, tutti gli anni')).toBeInTheDocument();
});
it('un promemoria FATTURA senza fattura_id non può pagare una fattura inesistente', async () => {
  api.get.mockResolvedValue(response([row('Promemoria fattura',{tipo:'FATTURA'})]));
  render(page()); await screen.findByText('Promemoria fattura');
  expect(screen.queryByRole('button',{name:'Paga'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Apri fattura'})).not.toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});
it('un errore di caricamento non mostra zero né righe del vecchio anno', async () => {
  api.get.mockResolvedValueOnce(response([row('Precedente')]));
  const view=render(page()); await screen.findByText('Precedente');
  api.get.mockRejectedValueOnce(new Error('Fonte quietanze non disponibile'));
  context.anno=2025; view.rerender(page());
  expect(await screen.findByRole('alert')).toHaveTextContent('Fonte quietanze non disponibile');
  expect(screen.queryByText('Precedente')).not.toBeInTheDocument();
  expect(screen.queryByText('Residuo documentato')).not.toBeInTheDocument();
  api.get.mockResolvedValueOnce(response([row('Ripristinata')]));
  fireEvent.click(screen.getByRole('button', {name:'Riprova'}));
  expect(await screen.findByText('Ripristinata')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('carica la cinquantunesima scadenza e mantiene quelle già lette', async () => {
  const first = Array.from({length:50}, (_, i) => row(`Obbligo ${i + 1}`, {id:`r-${i}`,source:'tributo'}));
  api.get.mockImplementation(url => Promise.resolve(url.includes('offset=50')
    ? response([row('Obbligo 51',{id:'r-50',source:'tributo'})], {totale:51})
    : response(first,{totale:51})));
  render(page());
  fireEvent.click(await screen.findByRole('button',{name:'Carica altre scadenze'},{timeout:5000}));
  expect(await screen.findByText('Obbligo 51',{}, {timeout:5000})).toBeInTheDocument();
  expect(screen.getByText('Obbligo 1')).toBeInTheDocument();
  expect(screen.getByText('Obbligo 50')).toBeInTheDocument();
  expect(api.get.mock.calls[1][0]).toContain('offset=50');
  expect(screen.queryByRole('button',{name:'Carica altre scadenze'})).not.toBeInTheDocument();
}, 15000);
