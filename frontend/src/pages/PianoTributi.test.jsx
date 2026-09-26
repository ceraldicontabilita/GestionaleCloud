import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import PianoTributi from './PianoTributi';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));

const casella = (periodo, stato, etichetta_stato, extra = {}) => ({
  periodo, etichetta_periodo: `${periodo}/2026`, scadenza: '2026-07-16', stato, etichetta_stato,
  importo: null, credito: null, modelli: [], modelli_doppi: 0, mandatory: true, ...extra,
});

const piano = {
  anno: 2026,
  conteggi: { pagato: 1, manca_f24: 1 },
  etichette: { manca_f24: 'Manca F24' },
  mancano: [{ voce: 'Ritenute lavoro dipendente', codici: ['1001'], periodo: '06/2026', scadenza: '2026-07-16', stato: 'manca_f24' }],
  modelli_doppi: 1,
  fuori_piano: [{ codice: '1631', descrizione: 'Somme rimborsate', versamenti: [{}] }],
  voci: [{
    voce: { id: 'ritenute_1001', gruppo: 'Erario', etichetta: 'Ritenute lavoro dipendente', codici: ['1001'], periodo: 'mese', obbligatorio: true },
    caselle: [
      casella('05', 'pagato', 'Pagato (banca)', {
        importo: '1026.51',
        modelli: [{ f24_id: 'f1', data_versamento: '2026-06-16', debito_cents: 102651, credito_cents: 0,
          pdf_url: '/api/pdf/f1', quietanze: [], movimenti: [{ id: 'm1', data: '2026-06-17', agganciato: true, link: '/riconciliazione/banca?movimento=m1' }] }],
      }),
      casella('06', 'manca_f24', 'Manca F24'),
    ],
  }],
};

describe('PianoTributi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => Promise.resolve({
      data: url.includes('/verifica-codice/')
        ? { codice_tributo: '1001', periodo_cercato: '2026', righe_f24: [] }
        : piano,
    }));
  });

  it('mostra cosa manca per primo e ogni stato scritto in parole', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    expect(await screen.findByText('Da guardare subito')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ritenute lavoro dipendente 06\/2026: Manca F24/ })).toBeInTheDocument();
    expect(screen.getByText(/registrati due volte/)).toBeInTheDocument();
    expect(screen.getByText('1631')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/f24/piano-tributi?anno=2026');
  });

  it('una casella aperta porta al PDF e al movimento bancario', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /05\/2026: Pagato/ }));
    expect(screen.getByRole('link', { name: 'apri il PDF' })).toHaveAttribute('href', '/api/pdf/f1');
    expect(screen.getByRole('link', { name: /movimento del 17\/06\/2026/ })).toHaveAttribute('href', '/riconciliazione/banca?movimento=m1');
  });

  it('cerca un codice tributo nell anno scelto', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    fireEvent.change(await screen.findByPlaceholderText(/es. 1001/), { target: { value: '1001' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cerca' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/f24-riconciliazione/verifica-codice/1001?anno=2026'));
    expect(await screen.findByText(/Nessun F24 con questo codice/)).toBeInTheDocument();
  });
});
