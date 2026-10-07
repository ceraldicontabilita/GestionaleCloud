import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ArchivioFattureRicevute from './ArchivioFattureRicevute';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));
vi.mock('../components/ModalFattura', () => ({
  default: ({ fatturaId }) => <div data-testid="fattura-aperta">{fatturaId}</div>,
}));
vi.mock('../components/ScegliPagamentoFattura', () => ({ default: () => null }));

const fattura = (extra = {}) => ({
  id: 'f-1', invoice_number: 'INV-1', invoice_date: '2026-05-02',
  supplier_name: 'Fornitore di prova', total_amount: 100, ...extra,
});

function rispondi({ archivio = [], dettaglio = fattura() } = {}) {
  api.get.mockImplementation(url => {
    if (url.startsWith('/api/fatture-ricevute/archivio?')) return Promise.resolve({ data: { fatture: archivio } });
    if (url.startsWith('/api/fatture-ricevute/fattura/')) return Promise.resolve({ data: dettaglio });
    if (url.startsWith('/api/fatture-ricevute/fornitori?')) return Promise.resolve({ data: { items: [] } });
    if (url.startsWith('/api/fatture-ricevute/statistiche')) return Promise.resolve({ data: null });
    return Promise.reject(new Error(`URL inatteso: ${url}`));
  });
}

function monta(url = '/fatture') {
  return render(<MemoryRouter initialEntries={[url]}><ArchivioFattureRicevute /></MemoryRouter>);
}

describe('Collegamenti e disponibilità archivio fatture', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, '', '/fatture');
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(cleanup);

  it('raggiunge la fattura di un altro anno anche quando l elenco corrente è vuoto', async () => {
    rispondi({ dettaglio: fattura({ id: 'storica', invoice_date: '2024-03-10' }) });
    monta('/fatture?invoice_id=storica');
    fireEvent.click(await screen.findByRole('button', { name: 'Vedi la fattura adesso' }));
    expect(screen.getByTestId('fattura-aperta')).toHaveTextContent('storica');
  });

  it('il parametro testuale riconosce anche gli ID storici numerici già in elenco', async () => {
    rispondi({ archivio: [fattura({ id: 123 })] });
    monta('/fatture?invoice_id=123');
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    expect(api.get.mock.calls.some(([url]) => url.startsWith('/api/fatture-ricevute/fattura/'))).toBe(false);
    expect(screen.queryByRole('button', { name: 'Vedi la fattura adesso' })).not.toBeInTheDocument();
  });

  it('un errore nella verifica della fattura non afferma che sia stata eliminata', async () => {
    rispondi();
    const normale = api.get.getMockImplementation();
    api.get.mockImplementation(url => url.startsWith('/api/fatture-ricevute/fattura/')
      ? Promise.reject({ response: { status: 503, data: { detail: { message: 'Servizio occupato' } } } }) : normale(url));
    monta('/fatture?invoice_id=f-1');
    expect(await screen.findByText(/Impossibile verificare la fattura richiesta: Servizio occupato/)).toBeInTheDocument();
    expect(screen.queryByText(/non esiste più o è stata eliminata/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('un errore iniziale non si presenta come assenza di fatture e si può riprovare', async () => {
    rispondi();
    const normale = api.get.getMockImplementation();
    let fallisce = true;
    api.get.mockImplementation(url => url.startsWith('/api/fatture-ricevute/archivio?') && fallisce
      ? Promise.reject(new Error('Archivio temporaneamente non disponibile')) : normale(url));
    monta();
    expect(await screen.findByRole('alert')).toHaveTextContent('Archivio temporaneamente non disponibile');
    expect(screen.queryByText('Nessuna fattura trovata')).not.toBeInTheDocument();
    fallisce = false;
    fireEvent.click(screen.getByRole('button', { name: 'Riprova' }));
    expect(await screen.findByText('Nessuna fattura trovata')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('un filtro fallito non lascia le vecchie fatture né la loro selezione esportabile', async () => {
    rispondi({ archivio: [fattura()] });
    const normale = api.get.getMockImplementation();
    api.get.mockImplementation(url => url.includes('mese=3')
      ? Promise.reject(new Error('Filtro non disponibile')) : normale(url));
    monta();
    fireEvent.click(await screen.findByTestId('seleziona-fattura-f-1'));
    fireEvent.change(screen.getByLabelText('Mese'), { target: { value: '3' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Filtro non disponibile');
    expect(screen.queryByText('INV-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('barra-selezione-fatture')).not.toBeInTheDocument();
  });

  it('una risposta del vecchio filtro arrivata tardi non sostituisce quello corrente', async () => {
    let risolviVecchia;
    rispondi();
    const normale = api.get.getMockImplementation();
    api.get.mockImplementation(url => {
      if (!url.startsWith('/api/fatture-ricevute/archivio?')) return normale(url);
      if (url.includes('mese=3')) return Promise.resolve({ data: { fatture: [fattura({ id: 'marzo', invoice_number: 'MARZO' })] } });
      return new Promise(resolve => { risolviVecchia = resolve; });
    });
    monta();
    fireEvent.change(screen.getByLabelText('Mese'), { target: { value: '3' } });
    expect(await screen.findByText('MARZO')).toBeInTheDocument();
    await act(async () => risolviVecchia({ data: { fatture: [fattura({ invoice_number: 'VECCHIA' })] } }));
    expect(screen.getByText('MARZO')).toBeInTheDocument();
    expect(screen.queryByText('VECCHIA')).not.toBeInTheDocument();
  });
});
