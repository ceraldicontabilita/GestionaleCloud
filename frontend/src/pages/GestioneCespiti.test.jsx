import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import GestioneCespiti from './GestioneCespiti';

const { confirmMock, toastMock } = vi.hoisted(() => ({
  confirmMock: vi.fn(),
  toastMock: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('../components/PageLayout', () => ({
  PageLayout: ({ children }) => <div>{children}</div>,
}));
vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => confirmMock,
}));
vi.mock('sonner', () => ({ toast: toastMock }));
vi.mock('../lib/utils', async () => {
  const actual = await vi.importActual('../lib/utils');
  return { ...actual, useIsMobile: () => false };
});

const cespite = {
  id: 'asset-1',
  descrizione: 'Forno professionale',
  categoria: 'forni',
  coefficiente_ammortamento: 12,
  valore_acquisto: 3500.5,
  fondo_ammortamento: 0,
  valore_residuo: 3500.5,
  data_acquisto: '2026-06-01',
  data_entrata_funzione: null,
  piano_ammortamento: [],
};

function getResponse(url) {
  if (url === '/api/cespiti/?attivi=true') return Promise.resolve({ data: [cespite] });
  if (url === '/api/cespiti/riepilogo') {
    return Promise.resolve({
      data: {
        totali: {
          num_cespiti: 1,
          valore_acquisto: 3500.5,
          fondo_ammortamento: 0,
          valore_netto_contabile: 3500.5,
          entrata_funzione_da_verificare: 1,
        },
      },
    });
  }
  if (url === '/api/cespiti/verifica/2026') {
    return Promise.resolve({
      data: {
        stato: 'da_verificare',
        cespiti_attivi: 1,
        cespiti_ammortizzati: 0,
        entrata_funzione_da_verificare: 1,
        differenza: 0,
        critiche: [],
      },
    });
  }
  if (url === '/api/cespiti/categorie') return Promise.resolve({ data: { categorie: [] } });
  if (url === '/api/cespiti/calcolo/2026') {
    return Promise.resolve({
      data: { num_cespiti: 1, num_da_verificare: 0, totale_ammortamenti: 210 },
    });
  }
  return Promise.reject(new Error(`URL inatteso: ${url}`));
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/contabilita/cespiti']}>
      <GestioneCespiti />
    </MemoryRouter>
  );
}

describe('GestioneCespiti', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-08-06T10:00:00+02:00'));
    api.get.mockImplementation(getResponse);
    confirmMock.mockResolvedValue(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('mostra coerenza read-only, prova di entrata in funzione e centesimi', async () => {
    renderPage();

    expect(await screen.findByTestId('verifica-ammortamenti')).toHaveTextContent('0/1');
    expect(screen.getAllByText('Da verificare').length).toBeGreaterThan(0);
    expect(document.body).toHaveTextContent('3500,50');
    expect(api.get).toHaveBeenCalledWith(
      '/api/cespiti/verifica/2026',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it('lo scan fatture esegue prima la preview e scrive solo dopo conferma', async () => {
    api.post.mockImplementation(url => {
      if (url.includes('dry_run=true')) {
        return Promise.resolve({
          data: { num_potenziali_cespiti: 2, valore_totale: 4200 },
        });
      }
      return Promise.resolve({
        data: { cespiti_creati: 2, valore_totale: 4200, messaggio: 'Estratti 2 cespiti' },
      });
    });
    confirmMock.mockResolvedValue(true);
    renderPage();

    fireEvent.click(await screen.findByTestId('scan-fatture-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[0][0]).toContain('dry_run=true');
    expect(api.post.mock.calls[1][0]).toContain('dry_run=false');
    expect(confirmMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Importa proposte da fatture XML',
      })
    );
  });

  it('durante l esercizio mostra solo anteprima e non registra quote definitive', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Verifica Ammort\. 2026/ }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/cespiti/calcolo/2026'));
    expect(toastMock.info).toHaveBeenCalledWith(
      expect.stringContaining('Registrazione definitiva')
    );
    expect(api.post.mock.calls.some(([url]) => url.includes('/registra/'))).toBe(false);
  });
});
