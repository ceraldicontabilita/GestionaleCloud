import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Tributi from './Tributi';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

const voce = (extra = {}) => ({
  chiave: 'sezione_erario|1040|2026|3', codice: '1040', sezione: 'sezione_erario', sezione_label: 'Erario',
  descrizione: 'Ritenute su redditi di lavoro autonomo', natura: 'tributo', anno: 2026, mese: 3, periodo: '03/2026',
  inviato_cents: 0, quietanza_cents: 70000, ravvedimento_cents: 0, banca_cents: 0, credito_cents: 0,
  atteso_cents: 70000, residuo_cents: 0, scadenza: '2026-04-16', ultimo_pagamento: '2026-04-16', in_ritardo: false,
  stato: 'PAGATO', stato_label: 'Pagato (quietanza)',
  documenti: [
    { tipo: 'quietanza', data: '2026-04-16', protocollo: '26041535212746370/000001', importo_cents: 49000, credito_cents: 0, pdf_url: '/api/originale/f24/q1', copie: 1 },
    { tipo: 'ritenuta', numero_fattura: '12', fornitore: 'STUDIO B', data: '2026-03-20', importo_cents: 28000, scadenza: '2026-04-16',
      versata: true, data_pagamento: '2026-04-16', quietanza_protocollo: '26041535212746370/000001', link: '/fatture?invoice_id=f1' },
  ],
  ...extra,
});

const risposta = {
  voci: [
    voce(),
    voce({ chiave: 'sezione_erario|1040|2026|8', periodo: '08/2026', quietanza_cents: 0, atteso_cents: 31000, residuo_cents: 31000,
      stato: 'SCADUTO', stato_label: 'Scaduto, non pagato', ultimo_pagamento: null, documenti: [] }),
    voce({ chiave: 'sezione_erario|6099|2025|', codice: '6099', descrizione: 'IVA annuale', periodo: '2025', quietanza_cents: 0,
      atteso_cents: 0, credito_cents: 39510, stato: 'CREDITO', stato_label: 'A credito, compensato', ultimo_pagamento: null,
      documenti: [{ tipo: 'credito', data: '2026-05-18', protocollo: 'P2', importo_cents: 0, credito_cents: 39510,
        compensato_con: [{ codice: '9001', periodo: '2023', importo_cents: 39510 }] }] }),
  ],
  totali: { quietanza_cents: 70000, ravvedimento_cents: 0, credito_cents: 39510, residuo_cents: 31000, voci: 3, codici: 2, aperte: 1 },
  facets: { anni: [2026, 2025], stati: [{ id: 'PAGATO', label: 'Pagato (quietanza)' }], sezioni: [{ id: 'sezione_erario', label: 'Erario' }] },
};

describe('Tributi', () => {
  it('su telefono le righe diventano card, senza tabella larga', async () => {
    window.innerWidth = 390;
    api.get.mockResolvedValue({ data: risposta });
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    expect(await screen.findByTestId('tributi-card')).toBeInTheDocument();
    expect(screen.queryByTestId('tabella-tributi')).toBeNull();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    window.innerWidth = 1400;
    api.get.mockResolvedValue({ data: risposta });
  });

  it('ordina per codice con le colonne pagato, ravvedimento, credito e resta da pagare', async () => {
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    expect(await screen.findByTestId('tabella-tributi')).toBeInTheDocument();
    expect(screen.getByText('Resta da pagare', { selector: 'th' })).toBeInTheDocument();
    expect(screen.getByText('Con ravvedimento', { selector: 'th' })).toBeInTheDocument();
    expect(screen.getByText('A credito / compensato', { selector: 'th' })).toBeInTheDocument();
    expect(screen.getByText('Scaduto, non pagato')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/f24/tributi?');
  });

  it('il clic sulla riga mostra quietanza e ritenuta pagata con i riferimenti', async () => {
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('riga-sezione_erario|1040|2026|3'));
    const ritenuta = await screen.findByTestId('riferimento-ritenuta');
    expect(ritenuta).toHaveTextContent('STUDIO B');
    expect(ritenuta).toHaveTextContent('Pagata il 16/04/2026 · quietanza protocollo 26041535212746370/000001');
    expect(screen.getByTestId('riferimento-quietanza')).toHaveTextContent('protocollo 26041535212746370/000001');
  });

  it('il credito dice che cosa ha compensato', async () => {
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('riga-sezione_erario|6099|2025|'));
    expect(await screen.findByTestId('riferimento-credito')).toHaveTextContent('Ha pagato in compensazione: 9001 2023');
  });

  it('i filtri vanno al server', async () => {
    render(<MemoryRouter initialEntries={['/tributi?cerca=1040']}><Tributi /></MemoryRouter>);
    await screen.findByTestId('tabella-tributi');
    expect(api.get).toHaveBeenCalledWith('/api/f24/tributi?cerca=1040');
    fireEvent.change(screen.getByLabelText('Anno di riferimento'), { target: { value: '2026' } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/f24/tributi?anno=2026&cerca=1040'));
  });

  it('segnala lo stesso tributo versato due volte', async () => {
    const doppio = { ...risposta, voci: [{ ...risposta.voci[0], chiave: 'sezione_tributi_locali|3918|2026|', codice: '3918',
      periodo: '2026', versato_due_volte_cents: 357400 }] };
    api.get.mockResolvedValue({ data: doppio });
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    expect(await screen.findByText('Versato due volte')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('riga-sezione_tributi_locali|3918|2026|'));
    expect(await screen.findByTestId('versato-due-volte')).toHaveTextContent('3.574,00');
  });

  it('un F24 a saldo zero è pagato in compensazione, non scartato', async () => {
    const zero = { ...risposta, voci: [voce({ chiave: 'sezione_erario|1012|2020|9', codice: '1012', periodo: '09/2020',
      quietanza_cents: 0, compensazione_cents: 39573, atteso_cents: 0, stato: 'COMPENSATO', stato_label: 'Pagato in compensazione (F24 a zero)',
      documenti: [{ tipo: 'compensazione', data: '2020-10-05', protocollo: '20100536070838682-000001', importo_cents: 39573,
        credito_cents: 0, saldo_delega_cents: 0, origini: ['drive'], crediti_usati: [{ codice: '1631', periodo: '09/2020', importo_cents: 96000 }] }] })] };
    api.get.mockResolvedValue({ data: zero });
    render(<MemoryRouter initialEntries={['/tributi']}><Tributi /></MemoryRouter>);
    expect(await screen.findByText(/compensato € 395,73/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('riga-sezione_erario|1012|2020|9'));
    const rif = await screen.findByTestId('riferimento-compensazione');
    expect(rif).toHaveTextContent('Pagato in compensazione (F24 a saldo zero)');
    expect(rif).toHaveTextContent('arrivata da Drive');
    expect(rif).toHaveTextContent('nessun addebito in banca');
  });

  it('registro versamenti: codici per mese, mesi non pervenuti, crediti e deleghe per origine', async () => {
    const mesi = n => Array.from({ length: 12 }, (_, i) => ({ mese: i + 1, debito_cents: i + 1 === n ? 100000 : 0, credito_cents: 0 }));
    const registro = {
      anno: 2026, anni: [2026, 2020], mesi: ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'],
      codici: [{ chiave: 'sezione_erario|1001', codice: '1001', descrizione: 'Ritenute lavoro dipendente', mesi: mesi(2),
        debito_cents: 100000, credito_cents: 0, mancanti: [3, 6] }],
      crediti: [{ chiave: 'sezione_erario|6099|2025', codice: '6099', anno_riferimento: 2025, descrizione: 'IVA annuale',
        utilizzato_cents: 39510, utilizzi: [{ data: '2026-05-18', protocollo: 'P2', importo_cents: 39510, utilizzato_progressivo_cents: 39510,
          compensazione_totale: true, origini: ['posta'], debiti_compensati: [{ codice: '9001', periodo: '2023', importo_cents: 39510 }] }] }],
      deleghe: [{ chiave: 'k1', data: '2026-05-18', protocollo: 'P2', saldo_cents: 0, debito_cents: 39510, credito_cents: 39510,
        compensazione_totale: true, origini: ['drive', 'posta'], righe: [] }],
      totali: { deleghe: 1, compensate_saldo_zero: 1, debito_cents: 39510, credito_cents: 39510, saldo_cents: 0, codici_con_mancanti: 1 },
      origini: [{ id: 'posta', label: 'Posta', deleghe: 1 }, { id: 'drive', label: 'Drive', deleghe: 1 }],
    };
    api.get.mockImplementation(url => Promise.resolve({ data: url.startsWith('/api/f24/tributi/versamenti') ? registro : risposta }));
    render(<MemoryRouter initialEntries={['/tributi?vista=versamenti']}><Tributi /></MemoryRouter>);
    expect(await screen.findByTestId('tabella-versamenti')).toBeInTheDocument();
    expect(screen.getByTestId('mancanti-sezione_erario|1001')).toHaveTextContent('Non pervenuto: marzo, giugno');
    fireEvent.click(screen.getByText('Crediti e compensazioni'));
    expect(await screen.findByTestId('credito-sezione_erario|6099|2025')).toHaveTextContent('Ha pagato: 9001 2023');
    fireEvent.click(screen.getByText('Deleghe F24'));
    expect(await screen.findByText('Saldo zero · tutto in compensazione')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Arrivato da'), { target: { value: 'drive' } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/f24/tributi/versamenti?origine=drive'));
  });

  it('scadenzario: in ritardo e ravveduto, con la motivazione', async () => {
    const scad = { anni: [2020], per_stato: [{ id: 'RAVVEDUTO', label: 'Pagato in ritardo, ravveduto', n: 1 }],
      voci: [{ chiave: 'sezione_erario|1012|2020|7', codice: '1012', periodo: '07/2020', stato: 'RAVVEDUTO',
        stato_label: 'Pagato in ritardo, ravveduto', scadenza: '2020-08-20', ultimo_pagamento: '2020-10-05', pagato_cents: 39573,
        pagamenti: [{ data: '2020-10-05', protocollo: 'P', importo_cents: 39573, giorni_ritardo: 46, compensazione_totale: true,
          motivazione: 'pagato il 05/10/2020, 46 giorni dopo la scadenza 20/08/2020' }] }] };
    api.get.mockImplementation(url => Promise.resolve({ data: url.startsWith('/api/f24/tributi/scadenzario') ? scad : risposta }));
    render(<MemoryRouter initialEntries={['/tributi?vista=scadenzario']}><Tributi /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('scad-sezione_erario|1012|2020|7'));
    expect(await screen.findByTestId('scad-pagamento')).toHaveTextContent('46 giorni di ritardo');
    expect(screen.getByTestId('scad-pagamento')).toHaveTextContent('in compensazione');
  });
});
