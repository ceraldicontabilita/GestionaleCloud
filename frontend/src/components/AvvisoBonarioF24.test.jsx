import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api', () => ({ default: { post: vi.fn() } }));

import api from '../api';
import AvvisoBonarioF24, { ESITI_AVVISO } from './AvvisoBonarioF24';

const source = readFileSync(resolve(process.cwd(), 'src/components/AvvisoBonarioF24.jsx'), 'utf8');
const riconciliazione = readFileSync(resolve(process.cwd(), 'src/pages/RiconciliazioneUnificata.jsx'), 'utf8');

describe('Interroga avviso bonario (PR 11)', () => {
  it('copre i cinque esiti del controllo e usa la palette salvia/sabbia', () => {
    expect(Object.keys(ESITI_AVVISO)).toEqual([
      'COPERTO', 'PAGATO_SENZA_QUIETANZA', 'DA_PAGARE', 'NON_TROVATO', 'IMPORTO_DIVERSO',
    ]);
    expect(source).toContain("'/api/f24/avviso-bonario/controllo'");
    expect(source).not.toMatch(/#(0f2744|2563eb|1e40af|dbeafe|4f46e5|7c3aed)/i);
    expect(source).toContain('Nessun dato viene modificato');
  });

  it('e montato nel tab F24 della pagina Riconciliazione', () => {
    expect(riconciliazione).toContain("import AvvisoBonarioF24 from '../components/AvvisoBonarioF24'");
    expect(riconciliazione.match(/<AvvisoBonarioF24 \/>/g)).toHaveLength(2);
  });

  it('invia le righe e mostra esito, contropartite e riepilogo', async () => {
    api.post.mockResolvedValueOnce({
      data: {
        riepilogo: { totale_avviso: 1455.21, totale_coperto: 0, totale_pagato_senza_quietanza: 1455.21, totale_scoperto: 0 },
        fonti: { f24: 19, quietanze: 301, movimenti_f24_banca: 9 },
        righe: [{
          codice_tributo: '1001', descrizione_tributo: 'Ritenute su retribuzioni', periodo: '10/2019', importo: 1455.21,
          esito: 'PAGATO_SENZA_QUIETANZA', differenza: 0, motivazione: 'addebito compatibile',
          righe_f24: [{ f24_id: '149f', file_name: '2019-12-20__F24_000.pdf', data_versamento_it: '20/12/2019', saldo_modello: 2738.28, importo_righe: 1455.21, stato_evidenza: 'DA_PAGARE', pdf_url: '/api/f24-riconciliazione/commercialista/149f/pdf' }],
          quietanze: [],
          addebiti_banca: [{ movimento_id: 'mov-1', data_it: '20/12/2019', importo: 2738.28, agganciato: false, link: '/riconciliazione/banca?movimento=mov-1', descrizione: 'I24 AGENZIA ENTRATE' }],
          cedolini_hr: { periodo: '10/2019', n_cedolini: 9, natura: 'irpef', totale: null, trattenute_totali: 4239.58, attendibile: false, motivo: 'voci_non_estratte_nei_cedolini_hr', link: '/hr/' },
        }],
      },
    });

    render(<MemoryRouter><AvvisoBonarioF24 /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Codice tributo riga 1'), { target: { value: '1001' } });
    fireEvent.change(screen.getByLabelText('Periodo riga 1'), { target: { value: '10/2019' } });
    fireEvent.change(screen.getByLabelText('Importo riga 1'), { target: { value: '1455,21' } });
    fireEvent.click(screen.getByTestId('btn-interroga-avviso'));

    await waitFor(() => expect(screen.getByTestId('avviso-tabella-esiti')).toBeTruthy());
    expect(api.post).toHaveBeenCalledWith('/api/f24/avviso-bonario/controllo', expect.objectContaining({
      righe: [{ codice_tributo: '1001', periodo: '10/2019', importo: 1455.21, anno_imposta: null }],
    }));
    // badge dell'esito nella riga + etichetta del riepilogo
    expect(screen.getAllByText('Pagato senza quietanza').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId('avviso-f24-149f').textContent).toContain('20/12/2019');
    expect(screen.getByTestId('avviso-banca-mov-1').textContent).toContain('compatibile, non agganciato');
    expect(screen.getByText('apri movimento').getAttribute('href')).toBe('/riconciliazione/banca?movimento=mov-1');
    expect(screen.getByTestId('avviso-cedolini-hr').textContent).toContain('voci_non_estratte_nei_cedolini_hr');
    expect(screen.getByTestId('avviso-riepilogo').textContent).toContain('19 F24');
  });

  it('non chiama il backend senza righe complete', () => {
    api.post.mockClear();
    render(<MemoryRouter><AvvisoBonarioF24 /></MemoryRouter>);
    fireEvent.click(screen.getByTestId('btn-interroga-avviso'));
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('almeno una riga');
  });
});
