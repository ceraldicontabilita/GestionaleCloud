import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Bilancio from './Bilancio';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '' },
  },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({ pathname: '/contabilita/bilancio' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}));
vi.mock('sonner', () => ({
  toast: { warning: vi.fn(), error: vi.fn() },
}));

const statoPatrimoniale = {
  attivo: {
    disponibilita_liquide: { cassa: 100, banca: 600, totale: 700 },
    crediti: { crediti_vs_clienti: 100, totale: 100 },
    immobilizzazioni: { da_cespiti: 200, da_voci_manuali: 0, totale: 200 },
    totale_attivo: 1000,
  },
  passivo: {
    debiti: { debiti_vs_fornitori: 300, totale: 300 },
    fondo_tfr: 100,
    patrimonio_netto: 600,
    patrimonio_netto_dettaglio_manuale: 0,
    totale_passivo: 1000,
  },
};

const contoEconomico = {
  ricavi: { corrispettivi: 800, corrispettivi_lordi: 976, totale_ricavi: 800 },
  costi: { acquisti: 500, note_credito: 0, costi_netti: 500, totale_costi: 500 },
  risultato: { utile_perdita: 300, margine_percentuale: 37.5, tipo: 'utile' },
  statistiche: { num_corrispettivi: 10, num_fatture_ricevute: 4, num_note_credito: 0 },
};

function rispostaApi(url) {
  if (url.startsWith('/api/bilancio/stato-patrimoniale')) return Promise.resolve({ data: statoPatrimoniale });
  if (url.startsWith('/api/bilancio/conto-economico')) return Promise.resolve({ data: contoEconomico });
  if (url === '/api/voci-bilancio/2026') {
    return Promise.resolve({
      data: {
        voci: [{ id: 'voce-1', codice_cee: '23.01.01', descrizione: 'Capitale sociale', note: '', importo: 1000 }],
        totale_immobilizzazioni: 0,
        totale_patrimonio_netto: 1000,
      },
    });
  }
  if (url === '/api/voci-bilancio/codici-disponibili') return Promise.resolve({ data: { codici: [] } });
  return Promise.reject(new Error(`Chiamata inattesa: ${url}`));
}

describe('Bilancio', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(rispostaApi);
    window.confirm = vi.fn(() => false);
  });

  it('mostra Stato Patrimoniale quadrato con immobilizzazioni e Fondo TFR', async () => {
    render(<Bilancio />);

    expect(await screen.findByText('Immobilizzazioni')).toBeInTheDocument();
    expect(screen.getByText('Fondo TFR')).toBeInTheDocument();
    expect(screen.getByText('TOTALE ATTIVO').parentElement).toHaveTextContent('€ 1.000,00');
    expect(screen.getByText('TOTALE PASSIVO').parentElement).toHaveTextContent('€ 1.000,00');
    expect(api.get).toHaveBeenCalledWith('/api/bilancio/stato-patrimoniale?anno=2026');
    expect(api.get).toHaveBeenCalledWith('/api/bilancio/conto-economico?anno=2026');
  });

  it('mostra un errore esplicito e permette di riprovare', async () => {
    api.get.mockImplementation(url => {
      if (
        url.startsWith('/api/bilancio/stato-patrimoniale') ||
        url.startsWith('/api/bilancio/conto-economico')
      ) {
        return Promise.reject(new Error('servizio non disponibile'));
      }
      return rispostaApi(url);
    });

    render(<Bilancio />);

    expect(await screen.findByText(/Impossibile caricare il Bilancio/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('non elimina una voce manuale senza conferma', async () => {
    render(<Bilancio />);

    const elimina = await screen.findByTestId('elimina-voce-bilancio-voce-1');
    fireEvent.click(elimina);

    expect(window.confirm).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(api.delete).not.toHaveBeenCalled());
  });
});
