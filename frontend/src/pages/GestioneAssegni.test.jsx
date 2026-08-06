import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';

import GestioneAssegni, {
  assegnoInteramenteAssociato,
  filtraAssegni,
  normalizzaBeneficiarioAssegno,
  totaleQuoteFatture,
} from './GestioneAssegni';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

const ASSEGNI = [
  { id: 'a1', numero: '208769333', importo: 1097.47, beneficiario: '-' },
  { id: 'a2', numero: '208770635', importo: 644.21, beneficiario: 'FORNITORE TEST' },
  { id: 'a3', numero: '0208771000-01', importo: null, beneficiario: null, stato: 'vuoto' },
];

describe('Filtri pagina assegni', () => {
  it('non tratta i segnaposto come un vero beneficiario', () => {
    expect(normalizzaBeneficiarioAssegno('-')).toBe('');
    expect(normalizzaBeneficiarioAssegno('N/A')).toBe('');
    expect(normalizzaBeneficiarioAssegno('FORNITORE TEST')).toBe('FORNITORE TEST');
  });

  it('filtra per importo esatto accettando il formato italiano', () => {
    expect(filtraAssegni(ASSEGNI, { importoEsatto: '1.097,47' }).map(a => a.id)).toEqual(['a1']);
  });

  it('mostra i fogli del carnet anche prima di inserire importo e beneficiario', () => {
    expect(filtraAssegni(ASSEGNI).map(a => a.id)).toContain('a3');
    expect(filtraAssegni(ASSEGNI, { importoMin: '1' }).map(a => a.id)).not.toContain('a3');
  });

  it('inizia a filtrare il numero solo dopo tre cifre', () => {
    expect(filtraAssegni(ASSEGNI, { numeroAssegno: '20' })).toHaveLength(3);
    expect(filtraAssegni(ASSEGNI, { numeroAssegno: '933' }).map(a => a.id)).toEqual(['a1']);
  });
});

describe('Copertura assegno con fatture collegate', () => {
  it('considera completo l’assegno da 652,74 associato alla fattura da 652,74', () => {
    const collegate = [{ id: 'fattura-1', quota: 652.74 }];

    expect(totaleQuoteFatture(collegate)).toBeCloseTo(652.74, 2);
    expect(assegnoInteramenteAssociato(652.74, collegate)).toBe(true);
  });

  it('consente altre fatture soltanto finché resta un importo da coprire', () => {
    expect(assegnoInteramenteAssociato(652.74, [{ quota: 331.04 }])).toBe(false);
    expect(
      assegnoInteramenteAssociato(652.74, [{ quota: 331.04 }, { quota: 321.70 }])
    ).toBe(true);
  });
});

const renderPagina = () => render(
  <MemoryRouter>
    <GestioneAssegni />
  </MemoryRouter>
);

const rispostaPagina = assegni => url => {
  if (url.includes('/learning/stats-avanzate')) return Promise.resolve({ data: {} });
  if (url.includes('/stats?')) {
    return Promise.resolve({ data: { totale: assegni.length, per_stato: {} } });
  }
  return Promise.resolve({ data: assegni });
};

describe('Stati e resa responsive della pagina Assegni', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1280 });
  });

  it('mostra lo stato di caricamento', () => {
    api.get.mockImplementation(() => new Promise(() => {}));

    renderPagina();

    expect(screen.getByText('Caricamento...')).toBeInTheDocument();
  });

  it('mostra un errore esplicito anche quando il backend nega il permesso', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Non autenticato' } } });

    renderPagina();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Impossibile caricare assegni e statistiche: Non autenticato'
    );
  });

  it('mostra lo stato vuoto senza inventare righe', async () => {
    api.get.mockImplementation(rispostaPagina([]));

    renderPagina();

    expect(await screen.findByText('Nessun assegno presente')).toBeInTheDocument();
    expect(screen.queryByTestId('assegni-table')).not.toBeInTheDocument();
  });

  it('usa la tabella su desktop', async () => {
    api.get.mockImplementation(rispostaPagina([
      { id: 'a1', numero: '0208770985', stato: 'incassato', importo: 9760 },
    ]));

    renderPagina();

    const lista = await screen.findByTestId('assegni-table');
    await waitFor(() => expect(lista.querySelector('table')).not.toBeNull());
    expect(screen.getByText('Da ricavare dalla fattura')).toBeInTheDocument();
    expect(screen.getByText('Data EC mancante')).toBeInTheDocument();
    expect(screen.getByText('Attende fattura/XML')).toBeInTheDocument();
    expect(screen.getByText('Non calcolata')).toBeInTheDocument();
  });

  it('espone fornitore numero fattura data fattura e data incasso', async () => {
    api.get.mockImplementation(rispostaPagina([{
      id: 'a2', numero: '0208770986', stato: 'incassato', importo: 562.24,
      fornitore_fattura: 'Fornitore Verificato S.r.l.', numero_fattura: '120',
      data_fattura: '2026-06-15', data_incasso: '2026-06-30',
      evidenza_estratto_conto_id: 'ec-1', fattura_collegata: 'f-1',
    }]));

    renderPagina();

    expect(await screen.findByText(/Fornitore Verificato/)).toBeInTheDocument();
    expect(screen.getByText('Fatt. 120')).toBeInTheDocument();
    expect(screen.getByText('15-06-2026')).toBeInTheDocument();
    expect(screen.getByText('30-06-2026')).toBeInTheDocument();
    expect(screen.getByText('Estratto conto')).toBeInTheDocument();
  });

  it('non propone scelte manuali e attende dati univoci nei casi ambigui', async () => {
    api.get.mockImplementation(rispostaPagina([
      { id: 'auto', numero: '0208770649', stato: 'incassato', importo: 977.38 },
      {
        id: 'ambiguo', numero: '0208770650', stato: 'incassato', importo: 977.38,
        associazione_ambigua: true,
      },
    ]));

    renderPagina();

    await screen.findByTestId('assegni-table');
    expect(screen.queryByTestId('fatture-auto')).not.toBeInTheDocument();
    expect(screen.queryByTestId('fatture-ambiguo')).not.toBeInTheDocument();
    expect(screen.getByText('Attende dati univoci')).toBeInTheDocument();
  });

  it('segnala i collegamenti storici che superano il totale fattura', async () => {
    api.get.mockImplementation(rispostaPagina([{
      id: 'conflitto', numero: '0208770988', stato: 'incassato', importo: 646.72,
      numero_fattura: '56/D', associazione_conflittuale: true,
    }]));

    renderPagina();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Collegamento storico da verificare'
    );
  });

  it('usa card senza tabella su schermo mobile', async () => {
    window.innerWidth = 375;
    api.get.mockImplementation(rispostaPagina([
      { id: 'a1', numero: '0208770985', stato: 'incassato', importo: 9760 },
    ]));

    renderPagina();

    const lista = await screen.findByTestId('assegni-table');
    await waitFor(() => expect(lista.querySelector('table')).toBeNull());
    expect(lista).toHaveStyle({ display: 'flex', flexDirection: 'column' });
  });
});
