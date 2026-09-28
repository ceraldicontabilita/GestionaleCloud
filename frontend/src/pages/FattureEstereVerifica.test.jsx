import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import FattureEstereVerifica from './FattureEstereVerifica';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const confermata = {
  id: 'f-1', supplier_name: 'FORNITORE ESTERO', invoice_number: 'E-1', invoice_date: '2025-10-07',
  total_amount: 100, verifica_ai: 'confermata', verifica_ai_at: '2026-09-28T19:39:58+00:00',
  pagamento: { codice: 'da_collegare', pagata: false, testo: 'Pagamento da collegare' },
  candidati_paypal: [{
    transaction_id: 'TX-1', data: '2025-10-06', importo: 100, valuta: 'EUR',
    controparte: 'MARCHIO DEL GRUPPO', riferimento: 'ORD-1', addebito_banca: true,
    associabile: false, evidenze: ['importo', 'valuta'],
  }],
};

const risposte = verificate => url => Promise.resolve({ data: {
  '/api/fatture-estere/da-verificare': { fatture: [] },
  '/api/fatture-estere/affidabilita': { fornitori: [] },
  '/api/fatture-estere/verificate': { fatture: verificate },
}[url] });

describe('Fatture estere confermate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('la fattura confermata resta visibile col pagamento e i candidati PayPal', async () => {
    api.get.mockImplementation(risposte([confermata]));
    api.post.mockResolvedValue({ data: { pagamento: { testo: 'PayPal · addebito in banca trovato' } } });
    render(<FattureEstereVerifica />);

    expect(await screen.findByTestId('fatture-estere-confermate')).toBeInTheDocument();
    expect(screen.getByText('Pagamento da collegare')).toBeInTheDocument();
    expect(screen.getByText(/MARCHIO DEL GRUPPO/)).toBeInTheDocument();
    expect(screen.getByText(/addebito in banca trovato/)).toBeInTheDocument();
    expect(screen.getByText(/Da confermare tu/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('collega-paypal-TX-1'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/fatture-estere/f-1/collega-paypal', { transaction_id: 'TX-1' }));
  });
});
