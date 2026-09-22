import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

import api from '../api';
import PosizioneNoleggio from './PosizioneNoleggio';

const posizione = {
  anno: 2026,
  totali: { dare: 1891.9, avere: 1863.98, saldo: 27.92, avere_non_verificato: 832.25, per_categoria: {} },
  veicoli: [
    {
      targa: 'GX037HJ',
      marca: 'BMW',
      modello: 'X1',
      fornitore_noleggio: 'ALD',
      contratto: '700913195',
      stato_contratto: 'attivo',
      driver_attuale: { driver: 'Mario Bianchi', driver_id: 'dip-2' },
      assegnazioni: [{ driver: 'Luigi Rossi', driver_id: 'dip-1', dal: '2026-01-01', al: '2026-03-31' }],
      riepilogo: {
        dare: 1013.64,
        avere: 1013.64,
        saldo: 0,
        avere_non_verificato: 0,
        per_categoria: {
          canoni: { dare: 850.34, avere: 850.34, saldo: 0 },
          bollo: { dare: 126.9, avere: 126.9, saldo: 0 },
          verbali: { dare: 36.4, avere: 36.4, saldo: 0 },
        },
      },
      righe: [
        {
          data: '2026-04-01',
          tipo: 'pagamento',
          categoria: 'canoni',
          descrizione: 'Pagamento SDD/RID fattura INR0391666',
          dare: 0,
          avere: 850.34,
          documento: { tipo: 'fattura', id: 'uuid-ald-marzo', numero: 'INR0391666' },
          prova: { tipo: 'movimento_banca', fonte: 'Banca BPM', movimento_id: 'mov-marzo', data: '2026-04-01', banca_verificata: true },
          stato: 'verificata',
          driver: { driver: 'Luigi Rossi', driver_id: 'dip-1', fonte: 'storico_assegnazioni' },
        },
        {
          data: '2026-03-17',
          tipo: 'costo',
          categoria: 'canoni',
          descrizione: 'GX037HJ Canone di locazione',
          dare: 850.34,
          avere: 0,
          documento: { tipo: 'fattura', id: 'uuid-ald-marzo', numero: 'INR0391666', fornitore: 'ALD' },
          prova: null,
          stato: 'pagata',
          driver: { driver: 'Luigi Rossi', driver_id: 'dip-1', fonte: 'storico_assegnazioni' },
        },
      ],
      verbali: [
        {
          numero_verbale: '24990108761',
          data_verbale: '2026-03-24',
          in_fattura: false,
          importo_verificato: 36.4,
          pagato: true,
          fonte_quietanza: 'PartenoPay',
          driver_competente: { driver: 'Luigi Rossi', driver_id: 'dip-1' },
          trattenute: [{ importo: 36.4, stato: 'proposta' }],
        },
      ],
      fatture_aperte: 0,
      verbali_aperti: 0,
    },
  ],
  driver: [
    { driver_id: 'dip-1', driver: 'Luigi Rossi', senza_driver: false, veicoli: ['GX037HJ'], dare: 1013.64, avere: 1013.64, saldo: 0, verbali: 1, verbali_aperti: 0, verbali_importo: 36.4, trattenute: 36.4 },
  ],
  pagamenti_senza_documento: [
    { movimento_id: 'mov-comune', data: '2026-03-10', importo: 68.9, descrizione: 'VS.DISP. FAVORE COMUNE DI NAPOLI . VIOLAZIONE CDS', controparte: 'Comune di Napoli', per: 'verbale' },
  ],
  controlli: {
    auto_senza_driver: [],
    fatture_senza_pagamento: [],
    verbali_senza_quietanza: [],
    verbali_senza_targa: 105,
    verbali_senza_targa_esempi: [{ numero_verbale: 'A25111540620' }],
    pagamenti_senza_documento: 1,
    pagamenti_dichiarati_non_verificati: 1,
  },
};

const drivers = { drivers: [{ id: 'dip-1', nome_completo: 'Luigi Rossi' }, { id: 'dip-2', nome_completo: 'Mario Bianchi' }] };

function renderPagina() {
  return render(
    <MemoryRouter>
      <PosizioneNoleggio />
    </MemoryRouter>
  );
}

describe('PosizioneNoleggio', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.put.mockReset();
    api.get.mockImplementation(url => {
      if (url.startsWith('/api/noleggio/posizione')) return Promise.resolve({ data: posizione });
      if (url === '/api/noleggio/drivers') return Promise.resolve({ data: drivers });
      return Promise.reject(new Error(`URL inatteso ${url}`));
    });
  });

  it('legge un solo motore e mostra saldo, driver, quietanza e candidati', async () => {
    renderPagina();
    await waitFor(() => expect(screen.getByTestId('posizione-noleggio')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/api/noleggio/posizione?anno=2026');
    expect(screen.getAllByText('GX037HJ').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mario Bianchi').length).toBeGreaterThan(0);
    // driver alla data e fonte quietanza compaiono aprendo i movimenti
    fireEvent.click(screen.getByRole('button', { name: /Movimenti \(2\) e verbali \(1\)/ }));
    expect(screen.getByText('PartenoPay')).toBeInTheDocument();
    expect(screen.getByText('Banca BPM')).toBeInTheDocument();
    expect(screen.getAllByText('Luigi Rossi').length).toBeGreaterThan(0);
    // i pagamenti senza documento restano candidati, con il link alla riconciliazione
    expect(screen.getByText('Verbale da agganciare')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Apri in riconciliazione/ })).toHaveAttribute(
      'href',
      '/riconciliazione/banca?movimento=mov-comune'
    );
    expect(screen.getByText(/105 verbali in archivio non dicono a quale auto/)).toBeInTheDocument();
  });

  it('assegna il driver dalla scheda auto con il motore esistente e ricarica', async () => {
    api.put.mockResolvedValue({ data: { success: true } });
    renderPagina();
    await waitFor(() => expect(screen.getByTestId('posizione-noleggio')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Assegna driver a GX037HJ'), { target: { value: 'dip-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Assegna' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/api/noleggio/veicoli/GX037HJ', {
        driver_id: 'dip-1',
        driver: 'Luigi Rossi',
      })
    );
    await waitFor(() => expect(api.get.mock.calls.filter(c => c[0].startsWith('/api/noleggio/posizione')).length).toBe(2));
  });

  it('mostra un errore con Riprova quando il backend non risponde', async () => {
    api.get.mockRejectedValue(new Error('timeout'));
    renderPagina();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('e registrata nell hub Noleggio come tab e non usa colori vietati', () => {
    const hub = readFileSync(resolve(process.cwd(), 'src/pages/hub/VeicoliHub.jsx'), 'utf8');
    expect(hub).toContain("import('../PosizioneNoleggio.jsx')");
    expect(hub).toContain("{ id: 'posizione', label: 'Posizione auto e driver'");
    const sorgente = readFileSync(resolve(process.cwd(), 'src/pages/PosizioneNoleggio.jsx'), 'utf8');
    expect(sorgente).not.toMatch(/#(3b82f6|2563eb|1d4ed8|6366f1|4f46e5|7c3aed|8b5cf6)/i);
    expect(sorgente).toContain("api.get(`/api/noleggio/posizione?anno=${anno}`)");
  });
});
