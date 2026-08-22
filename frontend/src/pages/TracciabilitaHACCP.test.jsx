import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TracciabilitaHACCP from './TracciabilitaHACCP';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('../api', () => ({ default: { get, post } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ isAdmin: true, canWrite: true }) }));

describe('TracciabilitaHACCP', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation(url => {
      if (url.endsWith('/overview')) return Promise.resolve({ data: { purchase_lines: 1, requiring_review: 1, lots: 0, expired_lots: 0, register_entries: 0, open_expectations: 0, recipes: 0, productions: 0 } });
      if (url.endsWith('/purchase-lines')) return Promise.resolve({ data: { items: [{
        canonical_id: 'line-1', description: 'Farina 00', supplier_name: 'Forni Campania',
        invoice_number: '10', invoice_date: '2026-02-03', quantity: '25', unit: 'KG',
        status: 'DA_VERIFICARE', document_lot_number: '', document_expiry_date: '',
      }] } });
      if (url.endsWith('/register-types')) return Promise.resolve({ data: { items: [{ id: 'TEMPERATURA_POSITIVA', label: 'Temperature positive', unit: '°C' }] } });
      return Promise.resolve({ data: { items: [] } });
    });
  });

  it('mostra righe fattura 2026 e richiede lotto e scadenza osservati', async () => {
    render(<TracciabilitaHACCP />);
    expect(await screen.findByText('Farina 00')).toBeInTheDocument();
    expect(screen.getByText(/fattura 10 del 03\/02\/2026/)).toBeInTheDocument();
    expect(screen.getByLabelText('Numero lotto Farina 00')).toBeRequired();
    expect(screen.getByLabelText('Scadenza Farina 00')).toBeRequired();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(9));
  });

  it('espone registri, ricette, produzioni, attrezzature e manuale nella stessa area', async () => {
    render(<TracciabilitaHACCP />);
    await screen.findByText('Farina 00');
    for (const label of ['Controlli HACCP', 'Ricette', 'Produzioni', 'Attrezzature', 'Registro e manuale']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Controlli HACCP' }));
    expect(await screen.findByText('Nuovo controllo')).toBeInTheDocument();
    expect(screen.getByText('Nessun controllo registrato per l’anno.')).toBeInTheDocument();
  });
});
