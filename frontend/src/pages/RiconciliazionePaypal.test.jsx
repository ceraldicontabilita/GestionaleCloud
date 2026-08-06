import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';
import RiconciliazionePaypal from './RiconciliazionePaypal';

const viewport = vi.hoisted(() => ({ mobile: false }));

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

vi.mock('../hooks/useData', () => ({
  useIsMobile: () => viewport.mobile,
}));

vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

const transactions = [
  {
    transaction_id: 'TX-VALID', data: '2026-07-12', tipo: 'pagamento_web',
    descrizione: 'Servizio validato', nome_controparte: 'Fornitore Uno', lordo: -20.99,
    stato_collegamento_fattura: 'associata_validata',
    fattura_associata: { fattura_id: 'F1', numero: 'INV-1', fornitore: 'Fornitore Uno' },
  },
  {
    transaction_id: 'TX-OLD', data: '2026-07-13', tipo: 'pagamento_web',
    descrizione: 'Collegamento storico', nome_controparte: 'Fornitore Due', lordo: -42.62,
    stato_collegamento_fattura: 'da_rivalidare',
    fattura_associata: { fattura_id: 'F2', numero: 'INV-2', fornitore: 'Fornitore Sbagliato' },
  },
];

const source = {
  id: 'paypal-api-2026-07', source_type: 'api', tipo_documento: 'API',
  periodo_inizio: '2026-07-01', periodo_fine: '2026-07-31',
  totale_transazioni: 27, totale_pagamenti: 17,
  riepilogo: { pagamenti_inviati: 2136.56, depositi_accrediti: null, saldo_finale: null },
  documento_presente: false,
};

const bankMovement = {
  id: 'BANK-1', data: '2026-07-15', descrizione: 'ADDEBITO PAYPAL EUROPE',
  importo: -20.99, riconciliato_paypal: true, paypal_transaction_id: 'TX-VALID',
};

const mockSuccessfulRequests = () => {
  api.get.mockImplementation(url => {
    if (url.includes('/dashboard')) return Promise.resolve({ data: {
      total_statements: 0, total_transactions: transactions.length,
      totale_speso: -63.61, totale_pagamenti: 2, movimenti_banca_paypal: 44,
    } });
    if (url.includes('/transactions')) return Promise.resolve({ data: { transactions } });
    if (url.includes('/report')) return Promise.resolve({ data: {
      totale_transazioni: 2, totale_speso: -63.61, per_fornitore: [],
    } });
    if (url.includes('/statements')) return Promise.resolve({ data: {
      statements: [], fonti: [source], totale: 0, totale_periodi_api: 1,
    } });
    if (url.includes('/bank-movements')) return Promise.resolve({ data: {
      movimenti: [bankMovement], totale_banca_paypal: 1, riconciliati: 1, da_associare: 0,
    } });
    if (url.includes('/paypal-api/status')) return Promise.resolve({ data: { api_configurata: true } });
    return Promise.resolve({ data: {} });
  });
};

const renderPage = (entry = '/riconciliazione/paypal') => render(
  <MemoryRouter initialEntries={[entry]}>
    <RiconciliazionePaypal />
  </MemoryRouter>
);

describe('Pagina PayPal: fonti, stati e filtri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    viewport.mobile = false;
  });

  it('rende esplicito lo stato di caricamento', () => {
    api.get.mockImplementation(() => new Promise(() => {}));

    renderPage();

    expect(screen.getByRole('status')).toHaveTextContent('Caricamento dati PayPal');
  });

  it('mostra un errore di servizio senza presentare dati incompleti come certi', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));

    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Alcuni dati PayPal non sono stati caricati');
  });

  it('mostra la PayPal API come fonte senza inventare un PDF', async () => {
    mockSuccessfulRequests();

    renderPage('/riconciliazione/paypal?tab=documenti');

    expect(await screen.findByText('PayPal API')).toBeInTheDocument();
    expect(screen.getByText('Nessun file: fonte API')).toBeInTheDocument();
    expect(screen.getByText('27')).toBeInTheDocument();
    expect(screen.getByText('17')).toBeInTheDocument();
  });

  it('filtra i collegamenti storici da rivalidare', async () => {
    mockSuccessfulRequests();
    renderPage('/riconciliazione/paypal?tab=transazioni');

    expect(await screen.findByText('Servizio validato')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Stato collegamento fattura'), {
      target: { value: 'da_rivalidare' },
    });

    expect(screen.queryByText('Servizio validato')).not.toBeInTheDocument();
    expect(screen.getByText('Collegamento storico')).toBeInTheDocument();
    expect(screen.getAllByText('Da rivalidare')).toHaveLength(2);
  });

  it('usa card e non la tabella transazioni su mobile', async () => {
    viewport.mobile = true;
    mockSuccessfulRequests();

    renderPage('/riconciliazione/paypal?tab=transazioni');

    expect(await screen.findByTestId('paypal-transaction-cards')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('paypal-transactions-table')).not.toBeInTheDocument());
  });

  it('usa card anche per movimenti bancari e fonti su mobile', async () => {
    viewport.mobile = true;
    mockSuccessfulRequests();

    const { unmount } = renderPage('/riconciliazione/paypal?tab=estratti');
    expect(await screen.findByTestId('paypal-bank-cards')).toBeInTheDocument();
    expect(screen.queryByTestId('paypal-bank-table')).not.toBeInTheDocument();
    expect(screen.getByText('ADDEBITO PAYPAL EUROPE')).toBeInTheDocument();
    unmount();

    renderPage('/riconciliazione/paypal?tab=documenti');
    expect(await screen.findByTestId('paypal-source-cards')).toBeInTheDocument();
    expect(screen.queryByTestId('paypal-source-table')).not.toBeInTheDocument();
    expect(screen.getByText('Nessun file: fonte API')).toBeInTheDocument();
  });

  it('riprocessa automaticamente storico, banca e fatture per l anno globale', async () => {
    mockSuccessfulRequests();
    api.post.mockResolvedValue({ data: {
      collegamenti_prima: { associate: 1 },
      banca: { riconciliati: 1 },
      collegamenti_dopo: { finalizzate: 1 },
    } });
    renderPage();

    const button = await screen.findByTestId('reprocess-paypal-btn');
    fireEvent.click(button);

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/paypal-statements/riprocessa?anno=2026'
    ));
  });
});
