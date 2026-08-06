import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DashboardRelazionale from './DashboardRelazionale';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

function risposta(url) {
  if (url.startsWith('/api/alerts/lista')) {
    return Promise.resolve({ data: { alerts: [], stats: { non_risolti: 0 } } });
  }
  if (url === '/api/partite-aperte/stats') {
    return Promise.resolve({
      data: { fattura_fornitore: { count: 1, totale_residuo: 100 } },
    });
  }
  if (url === '/api/riconciliazione/stats') {
    return Promise.resolve({
      data: {
        stati: {
          riconciliati: { count: 2, totale: 200 },
          da_riconciliare: { count: 1, totale: 100 },
        },
        sezioni: {
          estratto_conto: { totale: 3, riconciliati: 2, da_riconciliare: 1 },
        },
        quadratura: { ok: true, valori: '3 = 2 + 1' },
      },
    });
  }
  if (url === '/api/partite-aperte/lista') {
    return Promise.resolve({
      data: {
        partite: [{
          id: 'pa-1',
          tipo: 'fattura_fornitore',
          documento_id: 'fatt-1',
          controparte_nome: 'Fornitore prova',
          importo_originale: 100,
          residuo: 100,
          data_scadenza: '2026-02-01',
          stato: 'aperta',
        }],
      },
    });
  }
  return Promise.reject(new Error(`Chiamata inattesa: ${url}`));
}

describe('DashboardRelazionale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(risposta);
  });

  it('applica l anno globale a partite e riconciliazione', async () => {
    render(<DashboardRelazionale />);

    expect(await screen.findByRole('button', { name: /Partite Aperte/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/api/partite-aperte/stats',
        { params: { anno: 2026 } },
      );
      expect(api.get).toHaveBeenCalledWith(
        '/api/riconciliazione/stats',
        { params: { anno: 2026 } },
      );
    });
  });

  it('non trasforma un errore della fonte partite in un falso zero', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/partite-aperte/stats') {
        return Promise.reject(new Error('partite offline'));
      }
      return risposta(url);
    });

    render(<DashboardRelazionale />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Partite 2026 non disponibili');
    expect(screen.getByRole('alert')).toHaveTextContent('I valori mancanti non sono zero');
    expect(screen.queryByText('Nessuna partita aperta')).not.toBeInTheDocument();
  });

  it('elenca le partite dell anno senza pulsanti contabili manuali', async () => {
    render(<DashboardRelazionale />);
    fireEvent.click(await screen.findByRole('button', { name: /Partite Aperte/ }));

    expect(await screen.findByText('Fornitore prova')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/partite-aperte/lista', {
      params: { stato: 'aperta', anno: 2026, limit: 50 },
    });
    expect(screen.queryByRole('button', { name: 'Cassa' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Banca' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apri Prima Nota' })).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
