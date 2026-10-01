import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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

  it('separa BPM e Mastercard SumUp e dice che sono saldi di Prima Nota', async () => {
    api.get.mockResolvedValue({ data: {
      ...summary,
      sumup: { entrate: 20, uscite: 0, riporto: 0, saldo: 20 },
    } });
    render(<Finanziaria />);

    expect(await screen.findByTestId('finanziaria-riga-sumup')).toHaveTextContent('Mastercard SumUp');
    expect(screen.getByText('Banca BPM')).toBeInTheDocument();
    expect(screen.getByTestId('finanziaria-nota-prima-nota')).toHaveTextContent(
      'non saldi certificati'
    );
  });

  it('IVA con fatture da classificare: nessun saldo inventato', async () => {
    api.get.mockResolvedValue({ data: {
      ...summary,
      vat_credit: null,
      vat_balance: null,
      vat_status: 'Da classificare (3 fatture senza IVA detraibile)',
      vat_da_classificare: 3,
    } });
    render(<Finanziaria />);

    expect(await screen.findByTestId('finanziaria-iva-saldo')).toHaveTextContent('Dato non disponibile');
    expect(screen.getAllByText(/Da classificare \(3 fatture/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Dato non disponibile').length).toBeGreaterThanOrEqual(3);
  });

  it('mostra un errore reale senza convertirlo in valori zero', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));
    render(<Finanziaria />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Dati finanziari non disponibili');
    expect(screen.getByRole('alert')).toHaveTextContent('servizio non disponibile');
  });

  it('dice fino a quando e aggiornato ogni conto e avvisa se manca un estratto conto', async () => {
    api.get.mockResolvedValue({ data: {
      ...summary,
      cassa: { ...summary.cassa, aggiornato_al: '2026-09-18' },
      banca: { ...summary.banca, aggiornato_al: '2026-09-28' },
      avvisi_aggiornamento: [{
        conto: 'banca',
        messaggio: "Banca BPM: l'ultimo estratto conto arriva al 31/03/2026.",
        azione: { etichetta: 'Carica estratto conto', percorso: '/documenti/import' },
      }],
    } });
    render(<MemoryRouter><Finanziaria /></MemoryRouter>);

    expect(await screen.findByTestId('finanziaria-aggiornato-cassa')).toHaveTextContent('aggiornato al 18/09/2026');
    expect(screen.getByTestId('finanziaria-aggiornato-banca')).toHaveTextContent('aggiornato al 28/09/2026');
    expect(screen.getByTestId('finanziaria-avviso-banca')).toHaveTextContent('31/03/2026');
    expect(screen.getByRole('link', { name: 'Carica estratto conto' })).toHaveAttribute('href', '/documenti/import');
  });

  it('senza data dell ultimo movimento lo dice, non la inventa', async () => {
    render(<Finanziaria />);
    expect(await screen.findByTestId('finanziaria-aggiornato-cassa')).toHaveTextContent('data ultimo movimento non nota');
  });
});
