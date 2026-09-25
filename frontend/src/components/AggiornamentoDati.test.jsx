import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import AggiornamentoDati, { dataOra, giorno } from './AggiornamentoDati';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  messaggioErrore: (e, predefinito) => e?.message || predefinito,
}));

const FONTI = {
  generato_at: '2026-09-25T06:00:00+00:00',
  fonti: [
    { ordine: 1, codice: 'banca', nome: 'Banca Banco BPM', stato: 'giallo',
      testo: "Il giro gira, ma l'ultimo movimento in archivio e' del 21/09/2026",
      ultimo_aggiornamento: '2026-09-25T04:34:06+00:00', ultimo_dato: '2026-09-21',
      conteggi: { movimenti: 2223, file_in_attesa: null }, nota: null },
    { ordine: 3, codice: 'corrispettivi', nome: 'Corrispettivi', stato: 'rosso',
      testo: 'Ultima giornata 18/09/2026: mancano 6 giorni di apertura.',
      ultimo_aggiornamento: null, ultimo_dato: '2026-09-18', conteggi: { giornate: 647 }, nota: null },
  ],
};

describe('Aggiornamento dati', () => {
  beforeEach(() => vi.clearAllMocks());

  it('formatta date in gg/mm/aaaa (ora di Roma) e non inventa un dato assente', () => {
    expect(dataOra('2026-09-25T04:34:06+00:00')).toBe('25/09/2026 06:34');
    expect(dataOra(null)).toBe('non disponibile');
    expect(giorno('2026-09-18')).toBe('18/09/2026');
    expect(giorno(undefined)).toBe('non disponibile');
  });

  it('mostra ogni fonte con stato in parole, date e conteggi', async () => {
    api.get.mockResolvedValue({ data: FONTI });
    render(<AggiornamentoDati />);
    const banca = await screen.findByTestId('fonte-banca');
    expect(banca.textContent).toContain('Attenzione');
    expect(banca.textContent).toContain('25/09/2026 06:34');
    expect(banca.textContent).toContain('movimenti in archivio: 2223');
    expect(banca.textContent).toContain('file in attesa: non disponibile');
    const corr = screen.getByTestId('fonte-corrispettivi');
    expect(corr.textContent).toContain('Fermo');
    expect(corr.textContent).toContain('Ultimo giro: non disponibile');
    expect(corr.textContent).toContain('18/09/2026');
    expect(api.get).toHaveBeenCalledWith('/api/dashboard/aggiornamento-dati', { timeout: 20000 });
  });

  it('se il servizio non risponde lo dice, con riferimento e Rileggi', async () => {
    api.get.mockRejectedValueOnce({ code: 'ECONNABORTED' });
    render(<AggiornamentoDati />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Servizio temporaneamente non disponibile');
    expect(screen.getByRole('alert')).toHaveTextContent('ECONNABORTED');
    api.get.mockResolvedValueOnce({ data: FONTI });
    fireEvent.click(screen.getByRole('button', { name: /Rileggi/ }));
    await waitFor(() => expect(screen.getByTestId('fonte-banca')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Lettura diretta Banco BPM nella riga banca', () => {
  beforeEach(() => vi.clearAllMocks());

  const conBanca = (eb) => ({
    ...FONTI,
    fonti: [{ ...FONTI.fonti[0], enable_banking: eb }],
  });

  it('spenta: lo dice e non offre comandi', async () => {
    api.get.mockResolvedValue({ data: conBanca({ attivo: false, configurato: false, collegata: false }) });
    render(<AggiornamentoDati />);
    const riga = await screen.findByTestId('lettura-diretta');
    expect(riga).toHaveTextContent('Lettura diretta spenta');
    expect(riga.querySelector('button')).toBeNull();
  });

  it('collegata: anteprima con i conteggi, senza scrivere', async () => {
    api.get.mockResolvedValueOnce({ data: conBanca({ attivo: true, configurato: true, collegata: true, valida_fino: '2026-12-22T10:00:00+00:00' }) });
    render(<AggiornamentoDati />);
    expect(await screen.findByTestId('lettura-diretta')).toHaveTextContent('valido fino al 22/12/2026');
    api.get.mockResolvedValueOnce({ data: { periodo: ['2026-06-27', '2026-09-24'], conteggi: { letti: 516, nuovi: 2, gia_presenti: 514, da_verificare: 0 } } });
    fireEvent.click(screen.getByRole('button', { name: /Anteprima/ }));
    const ant = await screen.findByTestId('anteprima-banca');
    expect(ant).toHaveTextContent('nuovi: 2');
    expect(ant).toHaveTextContent('già presenti: 514');
    expect(api.get).toHaveBeenLastCalledWith('/api/banca/enable-banking/anteprima', { timeout: 90000 });
  });
});
