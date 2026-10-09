import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import api from '../api';
import CartellePagamento from './CartellePagamento';

vi.mock('../api', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

const CARTELLA = {
  id: 'cartella:1', numero_cartella: '071 2026 00000001 11/000', ente_creditore: 'Comune di Prova',
  totale: '118.88', diritti_notifica: '5.88', iuv: '80070000000000123', importi_quadrano: true,
  expectation_status: 'ATTESO', data_notifica: null, scadenza: null,
  verbali: [{ numero_verbale: '111/V/2025', targa: 'AB123CD' }], verbali_collegati: [],
};

describe('CartellePagamento', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra la cartella da pagare senza inventare la scadenza e salva la notifica', async () => {
    api.get.mockResolvedValue({ data: { cartelle: [CARTELLA] } });
    api.put.mockResolvedValue({ data: { success: true, scadenza: '2026-09-23' } });

    render(<CartellePagamento />);

    expect(await screen.findByText('Da pagare')).toBeInTheDocument();
    expect(screen.getByText(/ancora da indicare/)).toBeInTheDocument();
    expect(screen.getByText(/non ancora in archivio/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Data di notifica della cartella/), { target: { value: '2026-07-25' } });
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pagopa/cartelle/cartella%3A1/notifica', { data_notifica: '2026-07-25' },
    ));
  });

  it('senza cartelle non disegna niente', async () => {
    api.get.mockResolvedValue({ data: { cartelle: [] } });
    const { container } = render(<CartellePagamento />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
