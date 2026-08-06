import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import CalendarioFiscale from './CalendarioFiscale';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const scadenzaAperta = {
  id: 'iva_liq_2026_07',
  anno: 2026,
  data: '2026-08-20',
  descrizione: 'Liquidazione IVA 07/2026',
  tipo: 'IVA',
  completato: false,
  provenienza_stato: 'nessuna_evidenza',
  livello_evidenza: 'nessuna',
  applicabilita: 'ordinaria',
};

const scadenzaDocumentata = {
  id: 'ritenute_2026_07',
  anno: 2026,
  data: '2026-08-20',
  descrizione: 'Versamento ritenute 07/2026',
  tipo: 'RITENUTE',
  completato: true,
  completato_da: 'quietanza_f24',
  provenienza_stato: 'quietanza_f24',
  livello_evidenza: 'documentale',
  applicabilita: 'ordinaria',
};

const calendario = {
  data: {
    success: true,
    anno: 2026,
    totale_scadenze: 2,
    completate: 1,
    prossime_5: [scadenzaAperta],
    imminenti_7_giorni: [],
    scadenze: [scadenzaAperta, scadenzaDocumentata],
    modalita_lettura: 'sola_lettura',
    scritture_eseguite: 0,
    fonte_scadenze: 'https://www1.agenziaentrate.gov.it/servizi/scadenzario/main.php?lang=it',
  },
};

const notifiche = {
  data: {
    success: true,
    urgenti: [],
    riepilogo: { critiche: 0, alta_priorita: 0, normali: 0 },
  },
};

const renderPage = () => render(
  <MemoryRouter>
    <CalendarioFiscale />
  </MemoryRouter>
);

describe('CalendarioFiscale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.includes('/api/fiscalita/calendario/2026')) return Promise.resolve(calendario);
      if (url.includes('/api/fiscalita/notifiche-scadenze')) return Promise.resolve(notifiche);
      return Promise.reject(new Error(`URL inatteso: ${url}`));
    });
    api.post.mockResolvedValue({ data: { success: true } });
  });

  it('carica in sola lettura e distingue quietanza da assenza di evidenza', async () => {
    renderPage();

    expect(await screen.findByText(/Lettura sicura/)).toBeInTheDocument();
    expect(screen.getByText('Quietanza F24')).toBeInTheDocument();
    expect(screen.getByText('Nessuna evidenza')).toBeInTheDocument();
    expect(screen.getByText('Protetta da F24')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.get).toHaveBeenCalledWith('/api/fiscalita/calendario/2026');
  });

  it('mantiene visibile il calendario se fallisce soltanto il riepilogo notifiche', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/fiscalita/calendario/2026')) return Promise.resolve(calendario);
      return Promise.reject(new Error('servizio notifiche non disponibile'));
    });

    renderPage();

    expect(await screen.findByText('Liquidazione IVA 07/2026')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('servizio notifiche non disponibile');
  });

  it('la conferma manuale specifica anno e provenienza invece di mutare durante il GET', async () => {
    renderPage();
    const button = await screen.findByRole('button', { name: 'Conferma con prova' });
    fireEvent.click(button);

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      expect.stringContaining('/api/fiscalita/calendario/completa/iva_liq_2026_07?anno=2026&note=')
    ));
  });
});
