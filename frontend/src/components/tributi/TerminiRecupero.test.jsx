import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api', () => ({ default: { get: vi.fn() } }));

import api from '../../api';
import Tributi from '../../pages/Tributi';
import TerminiRecupero, { AVVISO_TERMINI } from './TerminiRecupero';

const riga = (extra = {}) => ({
  chiave: 'INPS_DIP|11/2021|2021-12-16', codice: 'INPS_DIP', tributo: 'Contributi INPS dipendenti (DM10 / RC01)',
  tipo: 'mensile', periodo: '11/2021', scadenza: '2021-12-16', stato: 'MANCANTE', stato_label: 'Versamento non trovato',
  esito: 'VERSAMENTO NON TROVATO', pagato_cents: null, ha_f24: false, termine_ordinario: '2026-12-16',
  slittamento_covid: 'Nessuno slittamento Covid', recuperabile_entro: '2026-12-16', giorni_rimasti: 76,
  situazione: 'ANCORA_RECUPERABILE', situazione_label: "Ancora recuperabile dall'ente", urgente: true,
  ...extra,
});

const RISPOSTA = {
  oggi: '2026-10-01', avviso: AVVISO_TERMINI, soglia_urgenza_giorni: 120, totale: 3,
  voci: [
    riga(),
    riga({ chiave: 'CXX|02/2026|2026-03-16', codice: 'CXX', tributo: 'Contributi INPS (CXX)', periodo: '02/2026', scadenza: '2026-03-16',
      stato: 'F24_SENZA_QUIETANZA', stato_label: 'F24 senza quietanza', esito: 'F24 SENZA QUIETANZA', ha_f24: true,
      termine_ordinario: '2030-03-16', recuperabile_entro: '2030-03-16', giorni_rimasti: 1262, urgente: false }),
    riga({ chiave: 'INPS_DIP|10/2020|2020-11-16', periodo: '10/2020', scadenza: '2020-11-16', termine_ordinario: '2026-05-17',
      recuperabile_entro: '2026-05-17', slittamento_covid: 'Covid: prescrizione sospesa 182 giorni (art. 37 c. 2 DL 18/2020)',
      giorni_rimasti: null, situazione: 'TERMINE_SCADUTO', situazione_label: "Termine scaduto (salvo atti gia' notificati)", urgente: false }),
  ],
  conteggi: { righe: 110, aperte: 98, ancora_recuperabili: 27, urgenti: 9, scadute: 71, da_verificare: 0 },
  primo_termine: { recuperabile_entro: '2026-12-16', giorni_rimasti: 76, codice: 'INPS_DIP', periodo: '11/2021' },
  facets: {
    stati: [{ id: 'MANCANTE', label: 'Versamento non trovato', n: 76 }, { id: 'PAGATO', label: 'Pagato', n: 251 }],
    situazioni: [
      { id: 'ANCORA_RECUPERABILE', label: "Ancora recuperabile dall'ente", n: 27 },
      { id: 'TERMINE_SCADUTO', label: "Termine scaduto (salvo atti gia' notificati)", n: 71 },
    ],
    codici: [{ id: 'CXX', n: 8 }, { id: 'INPS_DIP', n: 11 }],
  },
};

describe('Termini di recupero', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.innerWidth = 1400;
    api.get.mockResolvedValue({ data: RISPOSTA });
  });

  it('mostra sempre il banner dei termini indicativi, anche prima che arrivino i dati', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    render(<TerminiRecupero />);
    expect(screen.getByTestId('avviso-termini')).toHaveTextContent('Termini indicativi, da confermare con il commercialista.');
  });

  it('parte dal filtro predefinito (versamento mancante) e chiama l\'endpoint dei termini', async () => {
    render(<TerminiRecupero />);
    await screen.findByTestId('tabella-termini');
    expect(api.get).toHaveBeenCalledWith('/api/f24/tributi/termini?');
  });

  it('elenca le colonne richieste con le date gg/mm/aaaa e l\'ordine del backend', async () => {
    render(<TerminiRecupero />);
    const tabella = await screen.findByTestId('tabella-termini');
    for (const colonna of ['Codice', 'Tributo', 'Periodo', 'Scadenza', 'Esito', 'Termine ordinario', 'Slittamento Covid', 'Recuperabile entro', 'Situazione']) {
      expect(within(tabella).getByText(colonna, { selector: 'th' })).toBeInTheDocument();
    }
    const righe = screen.getAllByTestId('termine-riga');
    expect(righe).toHaveLength(3);
    expect(righe[0]).toHaveTextContent('INPS_DIP');
    expect(righe[0]).toHaveTextContent('16/12/2021');                    // scadenza
    expect(righe[0]).toHaveTextContent('16/12/2026');                    // recuperabile entro
    expect(righe[2]).toHaveTextContent('Covid: prescrizione sospesa 182 giorni');
    expect(tabella.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);        // mai ISO a video
  });

  it('evidenzia sotto i 120 giorni con la scritta oltre al colore', async () => {
    render(<TerminiRecupero />);
    await screen.findByTestId('tabella-termini');
    const [prima, seconda, terza] = screen.getAllByTestId('termine-riga');
    expect(prima).toHaveAttribute('data-urgente', 'si');
    expect(prima).toHaveTextContent('Meno di 120 giorni: 76 giorni');
    expect(seconda).toHaveAttribute('data-urgente', 'no');
    expect(seconda).not.toHaveTextContent('Meno di 120 giorni');
    expect(terza).toHaveAttribute('data-urgente', 'no');
    expect(screen.getByTestId('riepilogo-termini')).toHaveTextContent('Sotto i 120 giorni: 9');
    expect(screen.getByTestId('riepilogo-termini')).toHaveTextContent('Primo termine: 16/12/2026 (76 giorni)');
  });

  it('i filtri richiamano il backend con i parametri scelti', async () => {
    render(<TerminiRecupero />);
    await screen.findByTestId('tabella-termini');
    fireEvent.change(screen.getByLabelText('Esito del controllo'), { target: { value: 'TUTTI' } });
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/f24/tributi/termini?stato=TUTTI'));
    fireEvent.change(screen.getByLabelText('Situazione del termine'), { target: { value: 'TERMINE_SCADUTO' } });
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/f24/tributi/termini?stato=TUTTI&situazione=TERMINE_SCADUTO'));
  });

  it('su telefono le righe diventano card impilate, senza tabella larga', async () => {
    window.innerWidth = 390;
    render(<TerminiRecupero />);
    expect(await screen.findByTestId('termini-card')).toBeInTheDocument();
    expect(screen.queryByTestId('tabella-termini')).toBeNull();
    expect(screen.getAllByTestId('termine-riga')[0]).toHaveTextContent('Meno di 120 giorni');
  });

  it('con 200 righe mostra «Mostra altre» per le restanti', async () => {
    const voci = Array.from({ length: 230 }, (_, i) => riga({ chiave: `k${i}`, periodo: `${String((i % 12) + 1).padStart(2, '0')}/2022` }));
    api.get.mockResolvedValue({ data: { ...RISPOSTA, voci, totale: 230 } });
    render(<TerminiRecupero />);
    await screen.findByTestId('tabella-termini');
    expect(screen.getAllByTestId('termine-riga')).toHaveLength(200);
    fireEvent.click(screen.getByText(/Mostra altre · 30 rimanenti/));
    expect(screen.getAllByTestId('termine-riga')).toHaveLength(230);
  });

  it('un errore del backend si dice, non si nasconde', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Supabase non raggiungibile' } } });
    render(<TerminiRecupero />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Supabase non raggiungibile');
  });

  it('è una scheda della pagina Tributi (?vista=termini) e non un nuovo percorso', async () => {
    api.get.mockResolvedValue({ data: RISPOSTA });
    render(<MemoryRouter initialEntries={['/tributi?vista=termini']}><Tributi /></MemoryRouter>);
    expect(await screen.findByTestId('termini-recupero')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Termini di recupero' })).toBeInTheDocument();
  });

  it('niente blu, viola o grigi freddi nei colori della pagina', () => {
    const sorgente = readFileSync(resolve(process.cwd(), 'src/components/tributi/TerminiRecupero.jsx'), 'utf8');
    expect(sorgente).not.toMatch(/#(3b82f6|2563eb|1d4ed8|6366f1|7c3aed|8b5cf6|64748b|94a3b8|6b7280)/i);
    expect(sorgente).not.toMatch(/\b(blue|indigo|violet|slate|gray)-\d{2,3}\b/);
  });
});
