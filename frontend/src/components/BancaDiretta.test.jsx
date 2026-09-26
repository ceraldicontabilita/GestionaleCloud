import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import BancaDiretta from './BancaDiretta';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  messaggioErrore: (e, predefinito) => e?.message || predefinito,
}));
vi.mock('./ui/ConfirmDialog', () => ({ useConfirm: () => async () => true }));

const COLLEGATA = {
  attivo: true, configurato: true, collegata: true, valida_fino: '2026-12-22T10:00:00+00:00',
  ultimo_import: '2026-09-26T19:15:00+00:00',
  giro_automatico: { eseguito_il: '2026-09-26T17:15:00+00:00', importati: 3, da_verificare_esclusi: 1 },
};

describe('Banco BPM in Prima Nota Banca', () => {
  beforeEach(() => vi.clearAllMocks());

  it('non compare a chi non e\' amministratore', async () => {
    api.get.mockRejectedValueOnce({ response: { status: 403 } });
    const { container } = render(<BancaDiretta />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('non collegata: offre solo il collegamento', async () => {
    api.get.mockResolvedValueOnce({ data: { attivo: true, configurato: true, collegata: false } });
    render(<BancaDiretta />);
    expect(await screen.findByText(/Conto non collegato/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Collega Banco BPM/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Aggiorna ora/ })).toBeNull();
  });

  it('collegata: mostra il giro automatico e «Aggiorna ora» importa solo i nuovi dopo conferma', async () => {
    api.get.mockResolvedValueOnce({ data: COLLEGATA });
    render(<BancaDiretta />);
    expect(await screen.findByTestId('banca-diretta')).toHaveTextContent('valido fino al 22/12/2026');
    expect(screen.getByTestId('banca-diretta')).toHaveTextContent('3 nuovi importati, 1 da verificare');
    api.get.mockResolvedValueOnce({ data: { conteggi: { letti: 12, nuovi: 2, gia_presenti: 9, da_verificare: 1 } } });
    api.post.mockResolvedValueOnce({ data: { importati: 2, gia_presenti: 9, da_verificare_esclusi: 1 } });
    api.get.mockResolvedValueOnce({ data: COLLEGATA });
    fireEvent.click(screen.getByRole('button', { name: /Aggiorna ora/ }));
    expect(await screen.findByTestId('esito-banca')).toHaveTextContent('Importati 2 movimenti nuovi');
    expect(api.get).toHaveBeenCalledWith('/api/banca/enable-banking/anteprima', { params: { giorni: 10 }, timeout: 90000 });
    expect(api.post).toHaveBeenCalledWith('/api/banca/enable-banking/importa', { conferma: true, giorni: 10 }, { timeout: 120000 });
  });

  it('nessun movimento nuovo: non chiede conferma e non scrive', async () => {
    api.get.mockResolvedValueOnce({ data: COLLEGATA });
    render(<BancaDiretta />);
    await screen.findByTestId('banca-diretta');
    api.get.mockResolvedValueOnce({ data: { conteggi: { letti: 9, nuovi: 0, gia_presenti: 9, da_verificare: 0 } } });
    fireEvent.click(screen.getByRole('button', { name: /Aggiorna ora/ }));
    expect(await screen.findByTestId('esito-banca')).toHaveTextContent('Importati 0 movimenti nuovi');
    expect(api.post).not.toHaveBeenCalled();
  });
});
