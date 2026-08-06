import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DatiIsa from './DatiIsa';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2025 }),
}));

const riepilogo = {
  anno: 2025,
  indicatori_acquisti: {
    caffe_kg_acquistati: 2526,
    caffe_costo_netto: 12000,
  },
  indicatori_disponibili: true,
  energia: {
    mensili: [{ anno: 2025, mese: 1, f1_kwh: 10, f2_kwh: 20, f3_kwh: 30, totale_kwh: 60 }],
    totali: { f1_kwh: 10, f2_kwh: 20, f3_kwh: 30, totale_kwh: 60 },
    disponibile: true,
  },
  avvertenze: ['Dato documentale, da verificare.'],
};

const fasce = {
  fascia_attuale: 'F3',
  azione: 'Conviene produrre',
  regole: [],
};

describe('DatiIsa', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => Promise.resolve({
      data: url.includes('/api/dati-isa/') ? riepilogo : fasce,
    }));
  });

  it('mostra i kg acquistati usando il contratto restituito dal backend', async () => {
    render(<DatiIsa />);

    expect(await screen.findByText(/^(?:2\.526|2526) kg$/)).toBeInTheDocument();
    expect(screen.getByText('60 kWh')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/dati-isa/riepilogo?anno=2025');
  });

  it('non trasforma un errore di caricamento in indicatori tutti a zero', async () => {
    api.get.mockRejectedValue(new Error('servizio ISA non disponibile'));
    render(<DatiIsa />);

    expect(await screen.findByRole('alert')).toHaveTextContent('servizio ISA non disponibile');
    expect(screen.queryByText('0 kg')).not.toBeInTheDocument();
    expect(screen.queryByText('0 kWh')).not.toBeInTheDocument();
  });

  it('distingue una fotografia annuale assente da valori contabili pari a zero', async () => {
    api.get.mockImplementation(url => Promise.resolve({
      data: url.includes('/api/dati-isa/')
        ? {
          anno: 2026,
          indicatori_acquisti: {},
          indicatori_disponibili: false,
          energia: { mensili: [], totali: {}, disponibile: false },
          avvertenze: [],
        }
        : fasce,
    }));

    render(<DatiIsa />);

    expect((await screen.findAllByText('Non calcolato')).length).toBeGreaterThanOrEqual(5);
    expect(screen.getByText('Non disponibile')).toBeInTheDocument();
    expect(screen.queryByText('0 kg')).not.toBeInTheDocument();
  });
});
