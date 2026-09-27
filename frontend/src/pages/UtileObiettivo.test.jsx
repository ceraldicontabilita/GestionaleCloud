import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import UtileObiettivo, { euroODato, statoDaRisposta } from './UtileObiettivo';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const senzaTarget = {
  anno: 2026,
  target: { utile_target_annuo: null, margine_medio_atteso: null, configurato: false },
  reale: { ricavi_totali: 1000, costi_totali: null, utile_corrente: null,
           personale_motivo: 'Nessuna busta paga registrata nel periodo' },
  analisi: { percentuale_target_annuo: null, gap_target_annuo: null, surplus_target_annuo: null },
};

describe('UtileObiettivo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('non inventa target, margine ne zeri quando il backend risponde null', () => {
    const stato = statoDaRisposta(senzaTarget);
    expect(stato.target_utile).toBeNull();
    expect(stato.margine_atteso).toBeNull();
    expect(stato.costi_totali).toBeNull();
    expect(stato.percentuale_raggiungimento).toBeNull();
    expect(euroODato(null)).toBe('Dato non disponibile');
  });

  it('senza target mostra la richiesta di impostarlo e i dati non disponibili', async () => {
    api.get.mockResolvedValue({ data: senzaTarget });
    render(<UtileObiettivo />);

    expect(await screen.findByTestId('utile-obiettivo-non-confrontabile')).toHaveTextContent(
      'Nessun target impostato'
    );
    expect(screen.getAllByText('Dato non disponibile').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('Obiettivo raggiunto')).not.toBeInTheDocument();
    expect(screen.getByTestId('input-target-utile')).toHaveValue(null);
  });
});
