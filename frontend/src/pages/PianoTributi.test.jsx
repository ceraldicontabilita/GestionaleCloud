import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import PianoTributi from './PianoTributi';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));

const dati = {
  anno: 2026, multi: false,
  voci: [{
    voce: { id: 'rit', etichetta: 'Ritenute lavoro dipendente', gruppo: 'Lavoro', codici: ['1001'], obbligatorio: true, periodo: 'mese' },
    caselle: [
      { periodo: '4', etichetta_periodo: '04/2026', stato: 'pagato', etichetta_stato: 'Pagato in banca', scadenza: '2026-05-18', modelli: [] },
      { periodo: '5', etichetta_periodo: '05/2026', stato: 'manca_f24', etichetta_stato: 'F24 scaduto, nessun pagamento', scadenza: '2026-06-16', modelli: [] },
    ],
  }],
  conteggi: { pagato: 1 },
  etichette: { manca_f24: 'F24 scaduto, nessun pagamento' },
  mancano: [{ voce: 'Ritenute lavoro dipendente', codici: ['1001'], periodo: '05/2026', scadenza: '2026-06-16', giorni_scaduto: 100, stato: 'manca_f24' }],
  fuori_piano: [], modelli_doppi: 0,
};

describe('Piano tributi: card cliccabili', () => {
  beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: dati }); });

  it('le card del riepilogo filtrano le caselle e «Mostra tutto» toglie il filtro', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    await screen.findByText('Ritenute lavoro dipendente', { selector: 'strong' });
    expect(screen.getByLabelText(/04\/2026: Pagato in banca/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Mancano o scaduti/ }));
    expect(screen.getByTestId('piano-filtro-attivo')).toHaveTextContent('Mancano o scaduti');
    expect(screen.queryByLabelText(/04\/2026: Pagato in banca/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/05\/2026: F24 scaduto/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mostra tutto' }));
    expect(screen.queryByTestId('piano-filtro-attivo')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/04\/2026: Pagato in banca/)).toBeInTheDocument();
  });

  it('una card «Da guardare subito» apre il tributo per codice', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    const card = await screen.findByTestId('piano-card-mancante');
    expect(card).toHaveAttribute('href', '/situazione-fiscale/tributi-per-codice?cerca=1001');
  });
});
