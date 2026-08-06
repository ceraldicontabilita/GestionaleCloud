import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Finanziaria from './Finanziaria';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const summary = {
  anno: 2026,
  total_income: 400,
  total_expenses: 90,
  balance: 310,
  flow_balance: 310,
  opening_balance: -90,
  available_balance: 220,
  saldo_totale: 220,
  financial_note: 'I flussi escludono i trasferimenti interni.',
  cassa: { entrate: 100, uscite: 40, riporto: 10, saldo: 50 },
  banca: { entrate: 300, uscite: 50, riporto: -100, saldo: 170 },
  vat_debit: 22,
  vat_credit: 10,
  vat_balance: 12,
  vat_status: 'Da versare',
  corrispettivi: { count: 1, totale: 122 },
  fatture: { count: 1, totale: 61 },
  payables: 61,
  receivables: null,
  receivables_available: false,
  receivables_note: 'Fatture attive non gestite da una fonte canonica.',
};

describe('Finanziaria', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: summary });
  });

  it('distingue variazione annuale, riporti e disponibilita contabile', async () => {
    render(<Finanziaria />);

    expect(await screen.findByText("Variazione finanziaria dell'anno")).toBeInTheDocument();
    expect(screen.getByText('Disponibilità contabile')).toBeInTheDocument();
    expect(screen.getByText('Riporto iniziale')).toBeInTheDocument();
    expect(screen.getByText(/Include riporti iniziali/)).toBeInTheDocument();
    expect(screen.getByText(/I flussi escludono i trasferimenti interni/)).toBeInTheDocument();
    expect(screen.getByTestId('saldo-contabile-totale')).toHaveTextContent('220,00');
    expect(screen.getByTestId('saldo-contabile-totale')).not.toHaveTextContent('310,00');
  });

  it('non presenta zero come credito clienti certo quando manca la fonte', async () => {
    render(<Finanziaria />);

    expect(await screen.findByText('Non disponibile')).toBeInTheDocument();
    expect(screen.getByText('Fatture attive non gestite da una fonte canonica.')).toBeInTheDocument();
  });

  it('mostra un errore reale senza convertirlo in valori zero', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));
    render(<Finanziaria />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Dati finanziari non disponibili');
    expect(screen.getByRole('alert')).toHaveTextContent('servizio non disponibile');
  });
});
