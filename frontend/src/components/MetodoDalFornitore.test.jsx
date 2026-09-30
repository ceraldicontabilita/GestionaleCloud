import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import MetodoDalFornitore from './MetodoDalFornitore';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const fornitore = {
  id: 381,
  ragione_sociale: 'BIG FOOD SRL',
  metodo_pagamento: 'cassa',
  metodo_pagamento_dal: '2025-01-01',
};

const piano = {
  dry_run: true,
  dal: '2025-01-01',
  fatture_dal: 6,
  da_chiudere_in_cassa: [
    { id: 'a1', numero: 'V1065518', data: '2026-09-23', importo: 784.43, residuo: 784.43 },
    { id: 'a2', numero: 'V1066190', data: '2026-09-25', importo: 425.08, residuo: 425.08 },
  ],
  residuo_da_chiudere: 1209.51,
  gia_in_cassa: [{ id: 'p1' }],
  conflitto_banca_o_assegno: [
    { id: 'b1', numero: 'V1049978', data: '2026-07-16', importo: 663.69, motivo: 'pagata con prova in banca o assegno: non si sposta in Cassa' },
  ],
  non_forzate: [],
  pagate_senza_riga: [],
};

describe('Cassa dal … (metodo del fornitore nel tempo)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('prima mostra l\'elenco in anteprima (dry_run) e non scrive', async () => {
    api.post.mockResolvedValue({ data: piano });
    render(<MetodoDalFornitore fornitore={fornitore} id={381} onChiudi={vi.fn()} onFatto={vi.fn()} />);

    expect(await screen.findByText('V1065518')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/api/suppliers/381/applica-metodo-dal', null, {
      params: { dry_run: true },
    });
    expect(screen.getByText(/Pagate in banca o con assegno: non si toccano/)).toBeInTheDocument();
    expect(screen.getByText(/pagata con prova in banca o assegno/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registra 2 in Cassa' })).toBeInTheDocument();
  });

  it('alla conferma parte senza dry_run e attende l\'esito in sottofondo', async () => {
    api.post
      .mockResolvedValueOnce({ data: piano })
      .mockResolvedValueOnce({ data: { dry_run: false, avviato: true } });
    api.get.mockResolvedValue({ data: { stato: 'completato', registrate: 2, scartate: 0 } });
    const onFatto = vi.fn();
    render(<MetodoDalFornitore fornitore={fornitore} id={381} onChiudi={vi.fn()} onFatto={onFatto} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Registra 2 in Cassa' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenLastCalledWith('/api/suppliers/381/applica-metodo-dal', null, {
        params: { dry_run: false },
      })
    );
    expect(await screen.findByText(/Registrate 2, scartate 0/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(onFatto).toHaveBeenCalled();
  });

  it('senza fatture da registrare non offre il pulsante', async () => {
    api.post.mockResolvedValue({ data: { ...piano, da_chiudere_in_cassa: [], residuo_da_chiudere: 0 } });
    render(<MetodoDalFornitore fornitore={fornitore} id={381} onChiudi={vi.fn()} onFatto={vi.fn()} />);
    expect(await screen.findByText(/Niente da registrare in Cassa/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Registra/ })).not.toBeInTheDocument();
  });

  it('un metodo non applicabile (banca) mostra il motivo del rifiuto', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Si applica solo il metodo Cassa' } } });
    render(<MetodoDalFornitore fornitore={fornitore} id={381} onChiudi={vi.fn()} onFatto={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Si applica solo il metodo Cassa');
  });
});
