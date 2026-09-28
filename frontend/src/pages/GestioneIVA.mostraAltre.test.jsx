import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import GestioneIVA, { intervalloPeriodo } from './GestioneIVA';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));

const fattura = n => ({
  id: `f${n}`, supplier_name: `Fornitore ${n}`, invoice_number: `N-${n}`,
  periodo_iva_attribuito: '2026-04', iva_esposta: 1, iva_detraibile: 1,
  percentuale_detraibilita_iva: 100, detraibilita_valutata: true,
  stato_detrazione_iva: 'DA_INSERIRE',
});
const giornata = n => ({
  id: `c${n}`, data: '2026-04-01', matricola_rt: `RT${n}`, totale: 10, totale_iva: 1,
  totale_imponibile: 9, pagato_contanti: 10, pagato_elettronico: 0,
});

describe('Gestione IVA a pagine di 200 righe', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 3, 15));
    api.get.mockImplementation(url => {
      if (url.startsWith('/api/iva/fatture?periodo=2026-04&limit=200&skip=200')) {
        return Promise.resolve({ data: { fatture: [fattura(200), fattura(201)], totale: 202 } });
      }
      if (url.startsWith('/api/iva/fatture?periodo=2026-04&limit=200')) {
        return Promise.resolve({ data: {
          fatture: Array.from({ length: 200 }, (_, i) => fattura(i)), totale: 202,
          totale_iva_esposta: 202, totale_iva_detraibile: 202, totale_iva_disponibile: 202,
          totale_da_verificare: 0,
        } });
      }
      if (url.startsWith('/api/corrispettivi/periodo?data_da=2026-04-01&data_a=2026-04-30&limit=200&skip=200')) {
        return Promise.resolve({ data: { corrispettivi: [giornata(200)], totale: 201 } });
      }
      if (url.startsWith('/api/corrispettivi/periodo?data_da=2026-04-01&data_a=2026-04-30&limit=200')) {
        return Promise.resolve({ data: {
          corrispettivi: Array.from({ length: 200 }, (_, i) => giornata(i)), totale: 201,
          copie_escluse: 3,
          totali: { totale: 2010, imponibile: 1809, iva: 201, contanti: 2010, elettronico: 0 },
        } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('intervallo del periodo: anno intero o mese', () => {
    expect(intervalloPeriodo(2026, 2, false)).toEqual({ start: '2026-02-01', end: '2026-02-28' });
    expect(intervalloPeriodo(2026, 2, true)).toEqual({ start: '2026-01-01', end: '2026-12-31' });
  });

  it('mostra i totali del server e accoda fatture e giornate con «Mostra altre»', async () => {
    render(<MemoryRouter><GestioneIVA /></MemoryRouter>);

    const altreFatture = await screen.findByTestId('iva-mostra-altre-fatture');
    expect(altreFatture).toHaveTextContent('Mostra altre 2 · 2 rimanenti');
    expect(screen.getByText('202 fatture · 201 giornate XML')).toBeInTheDocument();
    expect(screen.getByText('3 copie escluse')).toBeInTheDocument();
    // Totale del periodo dal server, non dalle 200 righe caricate.
    expect(screen.getAllByText('€ 2.010,00').length).toBeGreaterThan(0);

    fireEvent.click(altreFatture);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/iva/fatture?periodo=2026-04&limit=200&skip=200'));
    expect(await screen.findByText('Fornitore 201')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('iva-mostra-altre-fatture')).not.toBeInTheDocument());

    fireEvent.click(screen.getByTestId('iva-mostra-altri-corrispettivi'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/corrispettivi/periodo?data_da=2026-04-01&data_a=2026-04-30&limit=200&skip=200',
    ));
    expect(await screen.findByText('RT200')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('iva-mostra-altri-corrispettivi')).not.toBeInTheDocument());
    vi.useRealTimers();
  });
});
