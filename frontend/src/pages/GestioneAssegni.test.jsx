import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';

import GestioneAssegni, {
  assegnoInteramenteAssociato,
  fatturePerFornitore,
  filtraAssegni,
  importiCoincidonoAlCentesimo,
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

describe('Selezione guidata fornitore e fattura', () => {
  const fatture = [
    {
      id: 'fatt-kimbo-1', supplier_name: 'KIMBO S.P.A.', supplier_vat: 'IT00123456789',
      invoice_number: '0070021988', invoice_date: '2026-06-29', importo_residuo: 1498.96,
    },
    {
      id: 'fatt-altro', supplier_name: 'ALTRO FORNITORE SRL', supplier_vat: 'IT00987654321',
      invoice_number: '77', invoice_date: '2026-06-30', importo_residuo: 1498.96,
    },
  ];

  it('usa identita fornitore e centesimi esatti senza mescolare fatture omonime', () => {
    expect(fatturePerFornitore(fatture, 'KIMBO S.P.A.', 'IT00123456789'))
      .toHaveLength(1);
    expect(importiCoincidonoAlCentesimo(1498.96, '1498.960')).toBe(true);
    expect(importiCoincidonoAlCentesimo(1498.96, 1498.95)).toBe(false);
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
    expect(screen.getByText('Nessuna fattura collegata')).toBeInTheDocument();
    expect(screen.getByTestId('choose-invoice-a1')).toHaveTextContent('Scegli fattura');
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

  it('seleziona il fornitore, mostra solo le sue fatture e compila la data dal documento', async () => {
    const assegno = {
      id: 'a-kimbo', numero: '0208769323', stato: 'incassato', importo: 1498.96,
      beneficiario: '', data_incasso: '2026-05-28',
    };
    const fatture = [
      {
        id: 'fatt-kimbo', supplier_name: 'KIMBO S.P.A.', supplier_vat: 'IT00123456789',
        invoice_number: '0070021988', invoice_date: '2026-06-29', importo_residuo: 1498.96,
      },
      {
        id: 'fatt-saima', supplier_name: 'SAIMA S.P.A.', supplier_vat: 'IT00987654321',
        invoice_number: '1/1557', invoice_date: '2026-01-07', importo_residuo: 1498.96,
      },
    ];
    api.get.mockImplementation(url => {
      if (url.includes('/supporto/fatture-disponibili')) return Promise.resolve({ data: fatture });
      return rispostaPagina([assegno])(url);
    });
    api.put.mockResolvedValue({ data: { success: true } });

    renderPagina();
    fireEvent.click(await screen.findByTestId('edit-a-kimbo'));
    fireEvent.change(screen.getByLabelText('Cerca e seleziona fornitore'), {
      target: { value: 'KIMBO S.P.A.' },
    });

    const selezione = await screen.findByLabelText('Fattura del fornitore');
    await waitFor(() => expect(selezione.querySelectorAll('option')).toHaveLength(2));
    expect(selezione).toHaveTextContent('0070021988');
    expect(selezione).not.toHaveTextContent('1/1557');
    fireEvent.change(selezione, { target: { value: 'fatt-kimbo' } });
    expect(screen.getByText(/Data fattura:/)).toHaveTextContent('29-06-2026');

    fireEvent.click(screen.getByTitle('Salva'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/assegni/a-kimbo/fatture-collegate',
      { fatture: [{ fattura_id: 'fatt-kimbo', quota: 1498.96 }] },
    ));
  });

  it('espone la scelta manuale senza collegare in automatico i casi ambigui', async () => {
    api.get.mockImplementation(rispostaPagina([
      { id: 'auto', numero: '0208770649', stato: 'incassato', importo: 977.38 },
      {
        id: 'ambiguo', numero: '0208770650', stato: 'incassato', importo: 977.38,
        associazione_ambigua: true,
      },
    ]));

    renderPagina();

    await screen.findByTestId('assegni-table');
    expect(screen.getByTestId('choose-invoice-auto')).toHaveTextContent('Scegli fattura');
    expect(screen.getByTestId('choose-invoice-ambiguo')).toHaveTextContent('Scegli fattura');
    expect(screen.getByText('Più candidati: scegli manualmente')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('choose-invoice-auto'));
    expect(await screen.findByLabelText('Cerca e seleziona fornitore')).toBeInTheDocument();
  });

  it('riprocessa estratto conto e fatture senza aprire una scelta manuale', async () => {
    api.get.mockImplementation(rispostaPagina([
      { id: 'a1', numero: '0208770649', stato: 'incassato', importo: 977.38 },
    ]));
    api.post.mockResolvedValue({
      data: {
        success: true,
        estratto_conto: { movimenti_analizzati: 1 },
        fatture: {
          analizzati: 1, collegati: 1, in_attesa_fattura: 0, ambigui: 0,
        },
      },
    });

    renderPagina();
    fireEvent.click(await screen.findByTestId('riprocessa-collegamenti-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/assegni/riprocessa-collegamenti?anno=2026'
    ));
    expect(await screen.findByTestId('riprocessamento-result')).toHaveTextContent(
      'Collegati: 1'
    );
    expect(screen.getByTestId('choose-invoice-a1')).toBeInTheDocument();
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

  it('mostra le fatture aperte del fornitore inserito e salva il collegamento', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/supporto/fatture-disponibili')) {
        return Promise.resolve({ data: [{
          id: 'fatt-kimbo', invoice_number: 'K-100', invoice_date: '2026-05-20',
          supplier_name: 'KIMBO S.P.A.', total_amount: 1498.96, pagato: false,
        }] });
      }
      return rispostaPagina([{
        id: 'ass-kimbo', numero: '0208769323', stato: 'incassato',
        importo: 1498.96, beneficiario: 'KIMBO',
      }])(url);
    });
    api.put.mockResolvedValue({ data: { success: true } });

    renderPagina();
    fireEvent.click(await screen.findByTestId('edit-ass-kimbo'));
    fireEvent.click(screen.getByRole('button', {
      name: 'Scegli fatture del fornitore KIMBO',
    }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('fornitore=KIMBO'),
    ));
    const fatturaProposta = await screen.findByText(/K-100|Nessuna fattura disponibile per assegno/);
    expect(fatturaProposta).toHaveTextContent('K-100');
    fireEvent.click(fatturaProposta);
    fireEvent.click(screen.getByTestId('salva-fatture-btn'));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/assegni/ass-kimbo/fatture-collegate',
      { fatture: [{ fattura_id: 'fatt-kimbo', quota: 1498.96 }] },
    ));
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
