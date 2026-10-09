import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ControlloMensile, { periodoDa } from './ControlloMensile';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

// Totali di Cassa e XML gia' sommati dal server (prima_nota_module/controllo_mensile.py).
const periodo = (periodo, valori = {}) => ({
  periodo,
  corrispettivi_xml: 0, contanti_xml: 0, xml_senza_contanti: 0, documenti_commerciali: 0,
  annulli: 0, pagato_non_riscosso: 0, pagato_non_riscosso_count: 0, ammontare_annulli: 0,
  ammontare_annulli_count: 0, corrispettivi_cassa: 0, differenza_contanti: 0, versamenti: 0,
  entrate_cassa: 0, uscite_cassa: 0, saldo_cassa: 0, movimenti_cassa: 0, righe_xml: 0,
  ...valori,
});
const gennaio = {
  corrispettivi_xml: 100, documenti_commerciali: 2, xml_senza_contanti: 1,
  corrispettivi_cassa: 100, differenza_contanti: null, versamenti: 20,
  entrate_cassa: 100, uscite_cassa: 20, saldo_cassa: 80, movimenti_cassa: 2, righe_xml: 1,
};
const riepilogoAnno = {
  data: {
    anno: 2026, mese: null,
    periodi: Array.from({ length: 12 }, (_, i) => periodo(
      `2026-${String(i + 1).padStart(2, '0')}`, i === 0 ? gennaio : {},
    )),
    totale: periodo(null, gennaio),
  },
};
const riepilogoGennaio = {
  data: {
    anno: 2026, mese: 1,
    periodi: Array.from({ length: 31 }, (_, i) => periodo(
      `2026-01-${String(i + 1).padStart(2, '0')}`,
      i === 1 ? { corrispettivi_xml: 100, documenti_commerciali: 2, xml_senza_contanti: 1,
        corrispettivi_cassa: 100, differenza_contanti: null, entrate_cassa: 100 }
        : i === 2 ? { versamenti: 20, uscite_cassa: 20, saldo_cassa: -20 } : {},
    )),
    totale: periodo(null, gennaio),
    versamenti_dettaglio: [
      { id: 'v1', data: '2026-01-03', categoria: 'Versamento', tipo: 'uscita', importo: 20 },
    ],
  },
};
const controlloPos = {
  data: {
    giorni: [
      {
        data: '2026-01-02',
        xml_elettronico: 70,
        pos_manuale: 65,
        pos_per_circuito: { numia: 65, sumup: null },
        accredito_banca: 65,
        diff_serale: 5,
        diff_accredito: 0,
        stato_serale: 'ok',
        stato_accredito: 'ok',
      },
    ],
  },
};
const registro = {
  data: {
    completezza_registro: {
      scritture_registrate: 1,
      fatture_da_registrare: 3,
      corrispettivi_da_registrare: 4,
      documenti_da_registrare: 7,
      completo: false,
    },
  },
};

function rispostaPerUrl(url) {
  if (url.startsWith('/api/prima-nota/controllo-mensile?anno=2026&mese=')) {
    return Promise.resolve(riepilogoGennaio);
  }
  if (url.startsWith('/api/prima-nota/controllo-mensile?anno=2026')) {
    return Promise.resolve(riepilogoAnno);
  }
  if (url.includes('/api/pos-corrispettivi/controllo-due-fasi')) {
    return Promise.resolve(controlloPos);
  }
  if (url.includes('/api/contabilita-gestionale/bilancio-verifica')) {
    return Promise.resolve(registro);
  }
  return Promise.reject(new Error(`URL inatteso: ${url}`));
}

describe('ControlloMensile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(rispostaPerUrl);
  });

  it('usa il motore POS canonico e non ricostruisce gli accrediti dal browser', async () => {
    render(<ControlloMensile />);

    const gennaio = await screen.findByTestId('row-month-1');
    expect(within(gennaio).getByText('€ 70,00')).toBeInTheDocument();
    expect(within(gennaio).getAllByText('€ 65,00')).toHaveLength(2);

    const urls = api.get.mock.calls.map(([url]) => url);
    expect(urls).toContain('/api/pos-corrispettivi/controllo-due-fasi?anno=2026');
    expect(urls).toContain('/api/contabilita-gestionale/bilancio-verifica?anno=2026');
    expect(urls.some(url => url.includes('/api/bank-statement/movements'))).toBe(false);
    expect(urls.some(url => url.includes('limit=500'))).toBe(false);
    // Cassa e corrispettivi arrivano sommati: nessuna riga scaricata.
    expect(urls).toContain('/api/prima-nota/controllo-mensile?anno=2026');
    expect(urls.some(url => url.includes('/api/prima-nota/cassa'))).toBe(false);
    expect(urls.some(url => url.includes('/api/corrispettivi?'))).toBe(false);
    expect(urls.some(url => /limit=\d{4,}/.test(url))).toBe(false);
    expect(screen.getByText(/Fatture da registrare/)).toBeInTheDocument();
    expect(screen.getByText(/Fatture da registrare 3/)).toBeInTheDocument();
  });

  it('non tratta XML maggiore del POS reale come errore se il backend lo certifica ok', async () => {
    render(<ControlloMensile />);

    await screen.findByTestId('row-month-1');
    expect(screen.queryByText(/Ci sono discrepanze/)).not.toBeInTheDocument();
  });

  it('mostra POS banca e differenza anche nel dettaglio giornaliero', async () => {
    render(<ControlloMensile />);
    fireEvent.click(await screen.findByTestId('view-month-1'));

    const table = await screen.findByTestId('monthly-table');
    expect(within(table).getByText('Accreditato su BPM')).toBeInTheDocument();
    expect(within(table).getByText('BPM − Numia')).toBeInTheDocument();
    expect(within(table).getByText("POS SumUp, dall'app")).toBeInTheDocument();
    expect(await screen.findByTestId('row-2026-01-02')).toBeInTheDocument();
    expect(api.get.mock.calls.some(([url]) =>
      url.includes('controllo-due-fasi?data_da=2026-01-01&data_a=2026-01-31')
    )).toBe(true);
    expect(api.get).toHaveBeenCalledWith('/api/prima-nota/controllo-mensile?anno=2026&mese=1');
  });

  it('segnala una fonte canonica non disponibile senza presentare zeri come certi', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/pos-corrispettivi/controllo-due-fasi')) {
        return Promise.reject(new Error('motore non disponibile'));
      }
      return rispostaPerUrl(url);
    });

    render(<ControlloMensile />);

    expect(await screen.findByText(/Errore nel caricamento di: Controllo POS-banca/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('row-month-1')).toBeInTheDocument());
  });
  it('confronta la Cassa con la sola quota contanti: la differenza e\' del server', async () => {
    // Totale XML 100, di cui 30 in contanti: in Cassa entrano 30 e basta.
    const valori = { corrispettivi_xml: 100, contanti_xml: 30, corrispettivi_cassa: 30,
      differenza_contanti: 0, entrate_cassa: 30, saldo_cassa: 30 };
    api.get.mockImplementation(url => {
      if (url.startsWith('/api/prima-nota/controllo-mensile?anno=2026&mese=1')) {
        return Promise.resolve({ data: {
          periodi: [periodo('2026-01-02', valori)], totale: periodo(null, valori),
          versamenti_dettaglio: [],
        } });
      }
      if (url.startsWith('/api/prima-nota/controllo-mensile')) {
        return Promise.resolve({ data: {
          periodi: [periodo('2026-01', valori)], totale: periodo(null, valori),
        } });
      }
      return rispostaPerUrl(url);
    });
    render(<ControlloMensile />);

    await screen.findByTestId('row-month-1');
    expect(screen.queryByText(/Ci sono discrepanze/)).not.toBeInTheDocument();
    expect(screen.getByText(/nessun mese da verificare/)).toBeInTheDocument();

    fireEvent.click(await screen.findByTestId('view-month-1'));
    const giorno = await screen.findByTestId('row-2026-01-02');
    expect(within(giorno).queryByText('Da verificare')).not.toBeInTheDocument();
  });

  it('un periodo assente dal riepilogo vale zero, non inventa dati', () => {
    expect(periodoDa({ periodi: [] }, '2026-03')).toMatchObject({
      periodo: '2026-03', corrispettivi_xml: 0, saldo_cassa: 0, differenza_contanti: 0,
    });
    expect(periodoDa({ periodi: [periodo('2026-03', { versamenti: 5 })] }, '2026-03').versamenti).toBe(5);
  });

  it('separa Numia e SumUp: la banca BPM si confronta col solo Numia', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/pos-corrispettivi/controllo-due-fasi')) {
        return Promise.resolve({ data: { giorni: [{
          data: '2026-01-02', xml_elettronico: 1629.5, pos_manuale: 1588.6,
          pos_per_circuito: { numia: 867.3, sumup: 721.3 },
          accredito_banca: 867.3, diff_serale: 40.9, diff_accredito: 0,
          stato_serale: 'ok', stato_accredito: 'ok',
        }] } });
      }
      return rispostaPerUrl(url);
    });
    render(<ControlloMensile />);

    const gennaio = await screen.findByTestId('row-month-1');
    expect(within(gennaio).getAllByText('€ 867,30')).toHaveLength(2);
    expect(within(gennaio).getByText('€ 721,30')).toBeInTheDocument();
    expect(within(gennaio).getAllByText('Chiuso')).toHaveLength(2);
  });
});
