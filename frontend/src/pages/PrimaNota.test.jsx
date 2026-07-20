import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import { CartaNexi, MovimentoModal } from './PrimaNota';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const rispostaVuota = {
  data: { verifica: { addebiti_trovati: 0, dettagli: [] } },
};

describe('Carta Nexi e anno globale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(rispostaVuota);
  });

  it('passa sempre l’anno globale al backend e ricarica quando cambia', async () => {
    const { rerender } = render(<CartaNexi anno={2025} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/nexi/stato?anno=2025'));

    rerender(<CartaNexi anno={2026} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/nexi/stato?anno=2026'));
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('ignora la risposta lenta dell’anno precedente', async () => {
    let completa2025;
    let completa2026;
    api.get.mockImplementation(url => new Promise(resolve => {
      if (url.endsWith('2025')) completa2025 = resolve;
      else completa2026 = resolve;
    }));

    const { rerender } = render(<CartaNexi anno={2025} />);
    await waitFor(() => expect(completa2025).toBeTypeOf('function'));
    rerender(<CartaNexi anno={2026} />);
    await waitFor(() => expect(completa2026).toBeTypeOf('function'));

    completa2026({ data: { verifica: {
      addebiti_trovati: 1,
      dettagli: [{ periodo: '2026-01', data_addebito: '2026-02-16', importo: 10, stato: 'estratto_mancante' }],
    } } });
    expect(await screen.findByText(/periodo 2026-01/)).toBeInTheDocument();

    completa2025({ data: { verifica: {
      addebiti_trovati: 1,
      dettagli: [{ periodo: '2025-01', data_addebito: '2025-02-16', importo: 20, stato: 'estratto_mancante' }],
    } } });
    await waitFor(() => expect(screen.queryByText(/periodo 2025-01/)).not.toBeInTheDocument());
    expect(screen.getByText(/periodo 2026-01/)).toBeInTheDocument();
  });
});

describe('Numero assegno in Prima Nota Banca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.put.mockResolvedValue({ data: { message: 'salvato' } });
  });

  it('mostra, modifica e salva il numero assegno sulla riga banca', async () => {
    const onSaved = vi.fn();
    render(<MovimentoModal
      tipo="banca"
      movimento={{
        id: 'mov-1', data: '2026-05-31', tipo: 'uscita', importo: 1098.28,
        descrizione: 'Fattura fornitore', categoria: 'Fatture', assegno_numero: '208769300',
      }}
      onClose={vi.fn()}
      onSaved={onSaved}
    />);

    const numero = screen.getByLabelText('Numero assegno');
    expect(numero).toHaveValue('208769300');
    fireEvent.change(numero, { target: { value: '208769333' } });
    fireEvent.click(screen.getByRole('button', { name: '💾 Salva' }));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/prima-nota/banca/mov-1',
      expect.objectContaining({ numero_assegno: '208769333', importo: 1098.28 }),
    ));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});
