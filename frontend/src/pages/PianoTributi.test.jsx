import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import PianoTributi from './PianoTributi';

vi.mock('../components/DocumentViewerModal', () => ({ default: ({ fetchUrl, onClose }) => <div role="dialog" data-url={fetchUrl}><button onClick={onClose}>Chiudi quietanza</button></div> }));

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));

const dati = {
  anno: 2026, multi: false,
  voci: [{
    voce: { id: 'rit', etichetta: 'Ritenute lavoro dipendente', gruppo: 'Lavoro', codici: ['1001'], obbligatorio: true, periodo: 'mese' },
    caselle: [
      { periodo: '4', etichetta_periodo: '04/2026', stato: 'pagato', etichetta_stato: 'Pagato in banca', scadenza: '2026-05-18', modelli: [] },
      { periodo: '5', etichetta_periodo: '05/2026', stato: 'manca_f24', etichetta_stato: 'F24 scaduto, nessun pagamento', scadenza: '2026-06-16', modelli: [] },
    ],
  }],
  conteggi: { pagato: 1 },
  etichette: { manca_f24: 'F24 scaduto, nessun pagamento' },
  mancano: [{ voce: 'Ritenute lavoro dipendente', codici: ['1001'], periodo: '05/2026', scadenza: '2026-06-16', giorni_scaduto: 100, stato: 'manca_f24' }],
  fuori_piano: [], modelli_doppi: 0,
};

describe('Piano tributi: card cliccabili', () => {
  beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: dati }); });

  it('le card del riepilogo filtrano le caselle e «Mostra tutto» toglie il filtro', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    await screen.findByText('Ritenute lavoro dipendente', { selector: 'strong' });
    expect(screen.getByLabelText(/04\/2026: Pagato in banca/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Mancano o scaduti/ }));
    expect(screen.getByTestId('piano-filtro-attivo')).toHaveTextContent('Mancano o scaduti');
    expect(screen.queryByLabelText(/04\/2026: Pagato in banca/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/05\/2026: F24 scaduto/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mostra tutto' }));
    expect(screen.queryByTestId('piano-filtro-attivo')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/04\/2026: Pagato in banca/)).toBeInTheDocument();
  });

  it('una card «Da guardare subito» apre il tributo per codice', async () => {
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    const card = await screen.findByTestId('piano-card-mancante');
    expect(card).toHaveAttribute('href', '/situazione-fiscale/tributi-per-codice?cerca=1001');
  });
});

describe('Piano IVA: credito e LIPE', () => {
  it('mostra il credito riportato, spiega il mancato versamento e apre la LIPE', async () => {
    api.get.mockResolvedValue({ data: {
      ...dati, mancano: [], conteggi: { iva_a_credito: 1 },
      voci: [{ voce: { id: 'iva_mensile', etichetta: 'IVA mensile (6001-6012)', gruppo: 'Erario', codici: ['6001', '6002'], periodo: 'mese', obbligatorio: false },
        caselle: [{ periodo: '01', etichetta_periodo: '01/2026', stato: 'iva_a_credito', etichetta_stato: 'Nessun versamento dovuto · a credito', modelli: [], credito: '40',
          iva: { fonte: 'LIPE', verificato: true, credito_iniziale_cents: 10000, credito_mese_precedente_cents: 0,
            credito_anno_precedente_cents: 10000, riporto_annuale_indicato: true, iva_vendite_cents: 6000, iva_acquisti_cents: 0,
            debito_mese_cents: 6000, credito_mese_cents: 0, altre_rettifiche_cents: 0, credito_residuo_cents: 4000, da_versare_cents: 0,
            documento: { nome: 'LIPE di gennaio.pdf', pdf_url: '/api/originale/documento/lipe-test' } },
        }] }],
    } });
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /IVA mensile.*01\/2026/ }));
    expect(screen.getByTestId('piano-iva-riporto')).toHaveTextContent('Credito residuo da riportare');
    expect(screen.getByTestId('piano-iva-riporto')).toHaveTextContent('40,00');
    expect(screen.getByText(/Nessun pagamento richiesto/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Apri LIPE' }));
    expect(screen.getByRole('dialog')).toHaveAttribute('data-url', '/api/originale/documento/lipe-test');
  });
});

describe('Piano tributi: atteso dal prospetto paghe', () => {
  it('apre la quietanza autonoma senza presentarla come modello F24', async () => {
    api.get.mockResolvedValue({ data: {
      ...dati, mancano: [],
      voci: [{ ...dati.voci[0], caselle: [{
        periodo: '03', etichetta_periodo: '03/2026', stato: 'pagato_quietanza',
        etichetta_stato: 'Pagato (quietanza)', scadenza: '2026-04-16', importo: '100.00',
        modelli: [{ f24_id: null, documento_id: 'q-mar', tipo_documento: 'quietanza',
          data_versamento: '2026-04-16', protocollo: 'PROTO-MARZO', debito_cents: 10000,
          credito_cents: 0, pdf_url: '/api/originale/quietanza/q-mar', movimenti: [], quietanze: ['q-mar'] }],
      }] }],
    } });
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /03\/2026: Pagato/ }));
    expect(screen.getByRole('dialog')).toHaveAttribute('data-url', '/api/originale/quietanza/q-mar');
    fireEvent.click(screen.getByRole('button', { name: 'Chiudi quietanza' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText(/Nessun F24 in archivio/)).not.toBeInTheDocument();
  });

  it('mostra l\'importo atteso dalle buste sulla casella e la differenza con l\'F24 nel dettaglio', async () => {
    api.get.mockResolvedValue({ data: {
      anno: 2026, oggi: '2026-09-26', conteggi: { pagato: 1 }, etichette: { pagato: 'Pagato (banca)' }, mancano: [], fuori_piano: [],
      voci: [{
        voce: { id: 'inps_cxx', gruppo: 'INPS', etichetta: 'Gestione separata (CXX)', codici: ['CXX'], periodo: 'mese', obbligatorio: false },
        caselle: [{
          periodo: '06', etichetta_periodo: '06/2026', stato: 'pagato', etichetta_stato: 'Pagato (banca)', scadenza: '2026-07-16',
          modelli: [], importo: '1050.90', credito: null, giorni_ritardo: 0, giorni_scaduto: null, modelli_doppi: 0,
          atteso_da_buste: { importo: '1050.90', importo_cents: 105090, differenza_cents: 0, prospetto_id: 'p1' },
        }],
      }],
    } });
    render(<MemoryRouter><PianoTributi /></MemoryRouter>);
    expect(await screen.findByTestId('atteso-da-buste')).toHaveTextContent('atteso');
    fireEvent.click(screen.getByRole('button', { name: /Gestione separata \(CXX\) 06\/2026/ }));
    expect(await screen.findByTestId('atteso-da-buste-dettaglio')).toHaveTextContent('uguale, al centesimo');
  });
});

it('la LIPE del terzo trimestre resta in attesa della scadenza, senza invito prematuro', async () => {
  api.get.mockResolvedValue({ data: { ...dati, mancano: [],
    voci: [{ voce: { id: 'iva_mensile', etichetta: 'IVA mensile', gruppo: 'Erario', codici: ['6008'], periodo: 'mese' },
      caselle: [{ periodo: '08', etichetta_periodo: '08/2026', stato: 'iva_compensazione_comunicata', etichetta_stato: 'Compensazione comunicata', modelli: [],
        iva: { fonte: 'Gestione IVA', verificato: false, credito_residuo_cents: null,
          presentazione_lipe: { anno: 2026, trimestre: 3, scadenza: '2026-11-30', puoi_scaricare: false,
            messaggio: 'LIPE trimestrale: attesa fino alla scadenza di presentazione', fonte_url: 'https://www1.agenziaentrate.gov.it/servizi/scadenzario/main.php' } },
      }] }],
  } });
  render(<MemoryRouter><PianoTributi /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: /08\/2026: Compensazione/ }));
  expect(screen.getByTestId('lipe-scadenza-trimestrale')).toHaveTextContent('30/11/2026');
  expect(screen.queryByText('Apri Gestione IVA per acquisire e confrontare la LIPE')).not.toBeInTheDocument();
});
