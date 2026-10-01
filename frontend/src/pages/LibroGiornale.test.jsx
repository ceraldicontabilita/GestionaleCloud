import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import LibroGiornale from './LibroGiornale';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const giornale = {
  totale: 1,
  totale_disponibile: 1,
  troncato: false,
  totale_dare: 84,
  totale_avere: 84,
  quadratura: true,
  qualita_registro: {
    registro_valido: true,
    scritture_sbilanciate: 0,
    protocolli_duplicati: 0,
    scritture_senza_protocollo: 0,
    righe_non_numeriche: 0,
    righe_senza_conto: 0,
  },
  scritture: [{
    id: 's1', numero_registrazione: 1, data: '2026-01-02', tipo: 'fattura',
    descrizione: 'Registrazione test', totale_dare: 84, totale_avere: 84, righe: [],
  }],
};

const mastro = {
  totale_conti: 1,
  totale_dare: 84,
  totale_avere: 84,
  quadratura: true,
  mastrini: [],
};

const proveFiscali = {
  anno: 2026,
  periodi: [{
    periodo: '2026-01',
    stato_iva: 'PAGATA_E_VERIFICATA',
    f24: [{
      f24_id: 'F24-1', filename: 'F24 gennaio.pdf',
      messaggio: 'IVA versata con F24: quietanza e movimento bancario verificati',
      f24_url: '/api/f24/pdf/F24-1', quietanza_url: '/api/f24-riconciliazione/quietanze/Q-1',
      movimento_bancario_id: 'EC-1', quietanza_presente: true, banca_verificata: true,
    }],
    avvisi_ade: [{
      id: 'A-1', filename: 'Lettera gennaio 2026.pdf',
      url: '/api/documenti/documento/A-1/download', associazione_certa: true,
      messaggio_pagamento: 'Pagamento richiesto da Agenzia delle Entrate pagato — vedi quietanza',
      quietanza_url: '/api/f24-riconciliazione/quietanze/Q-1',
    }],
  }],
};

function mockResponses({ controlloFallisce = false } = {}) {
  api.get.mockImplementation(url => {
    if (url.includes('/libro-giornale/prove-fiscali?')) return Promise.resolve({ data: proveFiscali });
    if (url.includes('/libro-giornale?')) return Promise.resolve({ data: giornale });
    if (url.includes('/libro-mastro?')) return Promise.resolve({ data: mastro });
    if (url.endsWith('/controllo-60-giorni')) {
      return controlloFallisce
        ? Promise.reject(new Error('controllo non disponibile'))
        : Promise.resolve({ data: { conforme: true } });
    }
    return Promise.reject(new Error(`Chiamata inattesa: ${url}`));
  });
}

describe('LibroGiornale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockResponses();
    window.confirm = vi.fn(() => false);
  });

  it('mostra il registro anche se il controllo accessorio dei 60 giorni fallisce', async () => {
    mockResponses({ controlloFallisce: true });

    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);

    expect(await screen.findByText('1 scritture')).toBeInTheDocument();
    expect(screen.getByText('Registrazione test')).toBeInTheDocument();
  });

  it('mostra un errore esplicito senza dati obsoleti se Giornale o Mastro falliscono', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));

    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);

    expect(await screen.findByText(/Impossibile caricare Libro Giornale e Libro Mastro/)).toBeInTheDocument();
    expect(screen.queryByText('Registrazione test')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('segnala qualita non valida e vista troncata', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/libro-giornale?')) {
        return Promise.resolve({
          data: {
            ...giornale,
            troncato: true,
            totale_disponibile: 9,
            quadratura: false,
            qualita_registro: {
              ...giornale.qualita_registro,
              registro_valido: false,
              scritture_sbilanciate: 1,
            },
          },
        });
      }
      if (url.includes('/libro-mastro?')) return Promise.resolve({ data: mastro });
      return Promise.resolve({ data: { conforme: true } });
    });

    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);

    expect(await screen.findByText(/mostrate 1 scritture su 9/)).toBeInTheDocument();
    expect(screen.getByTestId('alert-qualita-giornale')).toHaveTextContent('1 scritture sbilanciate');
  });

  it('non espone il reimport dalla pagina del registro definitivo', async () => {
    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);
    await screen.findByText('1 scritture');
    expect(screen.queryByTestId('import-giornale')).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('mostra F24, quietanza, movimento e lettera ADE nella vista relazionale', async () => {
    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);
    await screen.findByText('1 scritture');

    fireEvent.click(screen.getByTestId('toggle-prove-fiscali'));

    expect(screen.getByText('2026-01 · IVA pagata e verificata')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Apri F24/ })).toHaveAttribute('href', '/api/f24/pdf/F24-1');
    expect(screen.getAllByRole('link', { name: /Vedi quietanza/ })[0])
      .toHaveAttribute('href', '/api/f24-riconciliazione/quietanze/Q-1');
    expect(screen.getByRole('link', { name: /Vedi movimento pagante/ }))
      .toHaveAttribute('href', '/prima-nota#sezione=banca&selected=EC-1');
    expect(screen.getByRole('link', { name: /Apri lettera/ }))
      .toHaveAttribute('href', '/api/documenti/documento/A-1/download');
    expect(screen.getByText(/Pagamento richiesto da Agenzia delle Entrate pagato/)).toBeInTheDocument();
  });

  it('nasconde per leggere le coppie stornata + storno, che restano nel registro', async () => {
    const riga = (id, n, tipo, stato, descr) => ({
      id, numero_registrazione: n, data: '2026-01-02', tipo, stato, descrizione: descr,
      totale_dare: 5169, totale_avere: 5169, righe: [],
    });
    api.get.mockImplementation(url => {
      if (url.includes('/libro-giornale/prove-fiscali?')) return Promise.resolve({ data: proveFiscali });
      if (url.includes('/libro-giornale?')) {
        return Promise.resolve({ data: { ...giornale, totale: 3, totale_disponibile: 3, scritture: [
          riga('a', 530, 'corrispettivo', 'stornato', 'Corrispettivo del 2026-01-02 (provvisorio)'),
          riga('b', 1099, 'corrispettivo', 'registrato', 'Corrispettivo del 2026-01-02'),
          riga('c', 1100, 'storno_corrispettivo', 'registrato', 'Storno Corrispettivo del 2026-01-02'),
        ] } });
      }
      if (url.includes('/libro-mastro?')) return Promise.resolve({ data: mastro });
      return Promise.resolve({ data: { conforme: true } });
    });

    render(<MemoryRouter><LibroGiornale /></MemoryRouter>);

    expect(await screen.findByText('Corrispettivo del 2026-01-02')).toBeInTheDocument();
    expect(screen.queryByText(/provvisorio/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Storno Corrispettivo/)).not.toBeInTheDocument();
    expect(screen.getByTestId('nascondi-stornate')).toHaveTextContent('Nascondi le 2 scritture stornate');

    fireEvent.click(screen.getByRole('checkbox'));       // nessuna scrittura e' mai cancellata
    expect(screen.getByText(/provvisorio/)).toBeInTheDocument();
    expect(screen.getByText(/^Storno Corrispettivo/)).toBeInTheDocument();
  });
});
