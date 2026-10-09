import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

import api from '../api';
import { LetturaMovimento } from './RegoleRiconoscimentoBanca';

describe('Regole banca: cosa potrebbe essere questo movimento', () => {
  beforeEach(() => vi.clearAllMocks());

  it('un addebito Nexi dice a quale estratto va riscontrato, senza chiedere a chi appartiene', async () => {
    api.get.mockResolvedValue({ data: {
      riconoscimento: { categoria: 'Addebito carta di credito', motivo: "parola chiave 'ADDEBITO NEXI'" },
      nexi: { periodo_spese: '2026-07', riconciliato: false, nota: "Addebito mensile della carta: si riscontra con l'estratto Nexi del periodo." },
      candidati: [], classifica: '/riconciliazione/banca?movimento=N1', avviso: 'Candidati per importo al centesimo: nessun collegamento e\' applicato da qui.',
    } });
    render(<LetturaMovimento movimento={{ id: 'N1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cosa potrebbe essere?' }));
    expect(await screen.findByText('Addebito carta di credito')).toBeInTheDocument();
    expect(screen.getByText(/Carta Nexi, spese di 2026-07/)).toBeInTheDocument();
    expect(screen.queryByText(/A chi appartiene/)).not.toBeInTheDocument();
  });

  it('un pagamento al Comune elenca verbali, cartelle e fatture con lo stesso importo e rimanda a Classifica e collega', async () => {
    api.get.mockResolvedValue({ data: {
      riconoscimento: { categoria: null, motivo: 'nessun pattern non ambiguo riconosciuto' },
      nexi: null,
      candidati: [
        { tipo: 'verbale', id: 'V1', etichetta: 'Verbale 111/V/2025 - AB123CD', rotta: '/verbali-noleggio' },
        { tipo: 'cartella', id: 'c1', etichetta: 'Cartella 071 2026 1 - Comune', rotta: '/riconciliazione/pagopa' },
      ],
      classifica: '/riconciliazione/banca?movimento=C1', avviso: 'Candidati per importo al centesimo.',
    } });
    render(<LetturaMovimento movimento={{ id: 'C1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cosa potrebbe essere?' }));
    expect(await screen.findByRole('link', { name: 'Verbale 111/V/2025 - AB123CD' })).toHaveAttribute('href', '/verbali-noleggio');
    expect(screen.getByRole('link', { name: 'Classifica e collega' })).toHaveAttribute('href', '/riconciliazione/banca?movimento=C1');
  });

  it('un errore del server si dice', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Movimento non trovato' } } });
    render(<LetturaMovimento movimento={{ id: 'X' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cosa potrebbe essere?' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Movimento non trovato');
  });
});
