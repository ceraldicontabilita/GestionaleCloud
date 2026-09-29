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
    { tipo: 'quietanza', data: '2026-04-16', protocollo: '26041535212746370/000001', importo_cents: 49000, credito_cents: 0, pdf_url: '/api/f24-public/pdf/q1', copie: 1 },
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
});
