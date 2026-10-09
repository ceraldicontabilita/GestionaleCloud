import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ScegliPagamentoFattura, { OPZIONI_PAGAMENTO } from './ScegliPagamentoFattura';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const fattura = {
  id: 'fatt-1', invoice_number: 'N-1', invoice_date: '2026-09-25',
  supplier_name: 'FORNITORE PROVA', total_amount: 10,
};

describe('Tendina «Pagata con…»', () => {
  beforeEach(() => vi.clearAllMocks());

  it('offre cassa, banca e assegno', () => {
    expect(OPZIONI_PAGAMENTO.map(o => o.value)).toEqual(['cassa', 'banca', 'assegno']);
  });

  it('cassa: registra col motore dei provvisori e la data scelta', async () => {
    api.post.mockResolvedValue({ data: { success: true } });
    const onSuccess = vi.fn();
    render(<ScegliPagamentoFattura fattura={fattura} onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText(/Come e' stata pagata la fattura N-1/), { target: { value: 'cassa' } });
    const giorno = screen.getByLabelText('Giorno del pagamento');
    expect(giorno).toHaveValue('2026-09-25');
    fireEvent.change(giorno, { target: { value: '2026-09-26' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registra in cassa' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/prima-nota/provvisori/conferma', {
      fattura_id: 'fatt-1', metodo: 'cassa', approva_metodo_fattura: true, data_pagamento: '2026-09-26',
    }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });

  it('banca: apre subito la ricerca del movimento in estratto conto', async () => {
    api.get.mockResolvedValue({ data: { candidati: [], importo_residuo: 10 } });
    render(<ScegliPagamentoFattura fattura={fattura} onSuccess={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/Come e' stata pagata la fattura N-1/), { target: { value: 'banca' } });

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/fatture-ricevute/fattura/fatt-1/candidati-bancari'));
    expect(await screen.findByRole('dialog', { name: /Bonifici candidati per la fattura N-1/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Chiudi bonifici candidati' }));
    expect(screen.getByLabelText(/Come e' stata pagata la fattura N-1/)).toHaveValue('');
  });
});
