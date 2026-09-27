import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ControlloMensile, { contantiCorrispettivi, diffContantiCassa } from './ControlloMensile';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const cassa = {
  data: {
    movimenti: [
      { data: '2026-01-02', categoria: 'Corrispettivi', tipo: 'entrata', importo: 100 },
      { data: '2026-01-03', categoria: 'Versamento', tipo: 'uscita', importo: 20 },
    ],
  },
};
const corrispettivi = {
  data: [
    {
      data: '2026-01-02',
      totale: 100,
      numero_documenti: 2,
      pagato_elettronico: 9999,
      pagato_non_riscosso: 0,
      totale_ammontare_annulli: 0,
    },
  ],
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
  if (url.includes('/api/prima-nota/cassa')) return Promise.resolve(cassa);
  if (url.includes('/api/corrispettivi?')) return Promise.resolve(corrispettivi);
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
  it('confronta la Cassa con la sola quota contanti, non col totale XML', async () => {
    // Totale XML 100, di cui 30 in contanti: in Cassa entrano 30 e basta.
    api.get.mockImplementation(url => {
      if (url.includes('/api/prima-nota/cassa')) {
        return Promise.resolve({ data: { movimenti: [
          { data: '2026-01-02', categoria: 'Corrispettivi', tipo: 'entrata', importo: 30 },
        ] } });
      }
      if (url.includes('/api/corrispettivi?')) {
        return Promise.resolve({ data: [{
          data: '2026-01-02', totale: 100, pagato_contanti: 30, pagato_elettronico: 70,
        }] });
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

  it('contanti e differenza: helper puri', () => {
    expect(contantiCorrispettivi([{ pagato_contanti: 30 }, { pagato_contanti: '12.5' }]))
      .toEqual({ totale: 42.5, senzaContanti: 0 });
    expect(diffContantiCassa([{ totale: 100, pagato_contanti: 30 }], 30)).toBe(0);
    expect(diffContantiCassa([{ totale: 100, pagato_contanti: 30 }], 100)).toBe(-70);
    // Un XML senza quota contanti non si confronta: non e' una differenza.
    expect(diffContantiCassa([{ totale: 100 }], 30)).toBeNull();
    // Cassa senza nessun XML: tutta la Cassa e' da spiegare.
    expect(diffContantiCassa([], 30)).toBe(-30);
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
