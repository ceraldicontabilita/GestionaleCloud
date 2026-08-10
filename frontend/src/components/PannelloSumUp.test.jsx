import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    fireEvent.click(screen.getByRole('button', { name: 'Sincronizza ieri e oggi' }));

    expect(await screen.findByText('Accrediti SumUp unificati per giorno effettivo'))
      .toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('07/08/2026')).toBeInTheDocument());
    expect(screen.getByText(/98,00/)).toBeInTheDocument();
    expect(screen.getByText(/2,00/)).toBeInTheDocument();
  });
});
