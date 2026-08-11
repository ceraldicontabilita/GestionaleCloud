import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import PannelloSumUp from './PannelloSumUp';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

describe('Pannello SumUp', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra solo lo stato tecnico e non sincronizza dati operativi', async () => {
    api.get.mockResolvedValue({
      data: {
        connessione_ok: true,
        esercente: 'Ceraldi Group',
        chiave_visibile: '...08Wr',
        merchant_code: 'MFNRDMC4',
      },
    });

    render(
      <MemoryRouter>
        <PannelloSumUp />
      </MemoryRouter>
    );

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/sumup/stato'));
    expect(await screen.findByText('Collegato')).toBeInTheDocument();
    expect(screen.getByText(/Esercente:/)).toHaveTextContent('Ceraldi Group');
    expect(screen.getByRole('button', { name: 'Apri Prima Nota SumUp' })).toBeInTheDocument();
    expect(screen.queryByText(/Incassi SumUp/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Accrediti SumUp/)).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('non avvia la sincronizzazione se SumUp non e configurato', async () => {
    api.get.mockResolvedValue({
      data: { connessione_ok: false, messaggio: 'Chiave API non configurata' },
    });

    render(
      <MemoryRouter>
        <PannelloSumUp />
      </MemoryRouter>
    );

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/sumup/stato'));
    expect(api.post).not.toHaveBeenCalled();
  });
});
