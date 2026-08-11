import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import PannelloSumUp from './PannelloSumUp';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

describe('Pannello SumUp', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra gli accrediti gia unificati per data effettiva', async () => {
    api.get.mockResolvedValue({ data: { connessione_ok: true, esercente: 'Ceraldi Group' } });
    api.post.mockResolvedValue({ data: {
      message: 'Sincronizzazione completata',
      totale_netto: 100,
      giornate: [{
        data: '2026-08-06', vendite: 100, rimborsi: 0, netto: 100, transazioni: 2,
      }],
      payouts: {
        success: true,
        accrediti_per_giorno: [{
          data: '2026-08-07', accredito_mastercard: 98,
          commissioni: 2, gruppi: 2, da_verificare: 0,
        }],
      },
    } });

    render(<PannelloSumUp />);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/sumup/stato'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/sumup/sincronizza',
      expect.objectContaining({ dal: expect.any(String), al: expect.any(String) }),
    ));

    expect(await screen.findByText('Accrediti SumUp unificati per giorno effettivo'))
      .toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('07/08/2026')).toBeInTheDocument());
    expect(screen.getByText(/98,00/)).toBeInTheDocument();
    expect(screen.getByText(/2,00/)).toBeInTheDocument();
  });

  it('non avvia la sincronizzazione se SumUp non e configurato', async () => {
    api.get.mockResolvedValue({
      data: { connessione_ok: false, messaggio: 'Chiave API non configurata' },
    });

    render(<PannelloSumUp />);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/sumup/stato'));
    expect(api.post).not.toHaveBeenCalled();
  });
});
