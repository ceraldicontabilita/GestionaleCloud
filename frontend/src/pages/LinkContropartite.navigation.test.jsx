/**
 * Audit del commercialista 03/09/2026 §6 (PR 16) — "cliccando un dato ti
 * aspetti di trovare i dati in una contropartita": ogni registro, con il
 * dato collegato, mostra il link "Vai a…" con l'href della pagina di
 * destinazione, che a sua volta legge il parametro e mette in evidenza il
 * record.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import api from '../api';
import Scadenze from './Scadenze';
import LibroGiornale from './LibroGiornale';
import BilancioVerifica from './BilancioVerifica';
import { LinkEstrattoConto } from './PrimaNota';
import {
  PannelloMovimentoRichiesto, TabellaAnalisiF24, linksContropartitaMovimento,
} from './RiconciliazioneUnificata';
import { ROTTE_CONTROPARTITA, movimentoEstrattoContoDi, rottaDocumentoOrigine } from '../components/LinkContropartita';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), defaults: { baseURL: '' } },
}));
vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));
vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => vi.fn().mockResolvedValue(true),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

const EC_ID = 'EC-2026-02-17-11.68-4b86e9dd';

describe('Rotte delle contropartite (un solo punto di definizione)', () => {
  it('usa i deep-link letti dalle pagine di destinazione', () => {
    expect(ROTTE_CONTROPARTITA.fattura('F-1')).toBe('/fatture?invoice_id=F-1');
    expect(ROTTE_CONTROPARTITA.movimentoBanca(EC_ID)).toBe(`/riconciliazione/banca?movimento=${EC_ID}`);
    expect(ROTTE_CONTROPARTITA.primaNotaBanca('pn-1')).toBe('/prima-nota#sezione=banca&selected=pn-1');
    expect(ROTTE_CONTROPARTITA.verificaConto('01.01.01')).toBe('/contabilita/verifica?conto=01.01.01');
    expect(ROTTE_CONTROPARTITA.giornaleConto('01.01.01', 2026))
      .toBe('/contabilita/giornale?conto=01.01.01&data_da=2026-01-01&data_a=2026-12-31');
    expect(rottaDocumentoOrigine({ tipo: 'fattura', id: 'F-77' }).to).toBe('/fatture?invoice_id=F-77');
    expect(rottaDocumentoOrigine({ tipo: 'corrispettivo', id: 'C-1' })).toEqual({
      to: '/api/corrispettivi/C-1/view', esterno: true, etichetta: 'Apri il corrispettivo',
    });
    expect(rottaDocumentoOrigine(null)).toBeNull();
  });

  it('riconosce tutti i nomi reali del movimento di estratto conto in Prima Nota Banca', () => {
    expect(movimentoEstrattoContoDi({ estratto_conto_id: 'a' })).toBe('a');
    expect(movimentoEstrattoContoDi({ movimento_estratto_conto_id: 'b' })).toBe('b');
    expect(movimentoEstrattoContoDi({ movimento_bancario_id: 'c' })).toBe('c');
    expect(movimentoEstrattoContoDi({ estratto_conto_ids: ['d', 'e'] })).toBe('d');
    expect(movimentoEstrattoContoDi({ riconciliato: true })).toBeNull();
  });
});

describe('Prima Nota Banca → estratto conto', () => {
  it('rende il link al movimento riconciliato con href alla riconciliazione', () => {
    render(
      <MemoryRouter>
        <LinkEstrattoConto movimento={{
          id: 'pn-1', data: '2026-02-10', importo: 31.57, categoria: 'Fatture',
          estratto_conto_id: 'EC-2026-02-10-31.57-d2700414',
          movimento_estratto_conto_id: 'EC-2026-02-10-31.57-d2700414',
        }} />
      </MemoryRouter>,
    );
    const link = screen.getByTestId('link-estratto-conto-pn-1');
    expect(link).toHaveAttribute('href', '/riconciliazione/banca?movimento=EC-2026-02-10-31.57-d2700414');
    // formatDateIT del gestionale rende gg-mm-aaaa
    expect(link).toHaveAttribute('title', expect.stringContaining('10-02-2026'));
  });

  it('non inventa un link quando la riga non ha un movimento reale collegato', () => {
    const { container } = render(
      <MemoryRouter><LinkEstrattoConto movimento={{ id: 'pn-2', riconciliato: true }} /></MemoryRouter>,
    );
    expect(container.querySelector('a')).toBeNull();
  });
});

describe('Scadenze → movimento bancario che ha pagato la fattura', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.startsWith('/api/scadenze/tutte')) {
        return Promise.resolve({
          data: {
            scadenze: [{
              id: 'F-pag', fattura_id: 'F-pag', data: '2026-03-15', tipo: 'FATTURA', source: 'fattura',
              descrizione: 'Pagamento fattura IT6IKYJABEI', fornitore: 'Amazon Business EU',
              numero_fattura: 'IT6IKYJABEI', importo: 11.68, priorita: 'bassa', pagata: true,
              giorni_mancanti: -100, urgente: false,
              pagamento: { movimento_bancario_id: EC_ID, data_pagamento: '2026-02-17', metodo: 'SDD/RID' },
              movimento_bancario_id: EC_ID,
            }, {
              id: 'F-aperta', fattura_id: 'F-aperta', data: '2026-12-01', tipo: 'FATTURA', source: 'fattura',
              descrizione: 'Pagamento fattura 9/2026', fornitore: 'Fornitore', numero_fattura: '9/2026',
              importo: 50, priorita: 'media', pagata: false, giorni_mancanti: 80, urgente: false,
            }],
            totale: 2,
            statistiche: { urgenti: 0, prossimi_7_giorni: 0, totale_importo: 50 },
          },
        });
      }
      return Promise.resolve({ data: null });
    });
  });

  it('mostra "Movimento che l\'ha pagata" con href alla riconciliazione e nasconde Paga sulla pagata', async () => {
    render(<MemoryRouter initialEntries={['/scadenze']}><Scadenze /></MemoryRouter>);

    const link = await screen.findByTestId('link-movimento-pagante-F-pag');
    expect(link).toHaveAttribute('href', `/riconciliazione/banca?movimento=${EC_ID}`);
    expect(link).toHaveAttribute('title', expect.stringContaining('17-02-2026'));
    expect(screen.getByText(/Pagata il 17-02-2026/)).toBeInTheDocument();
    expect(screen.queryByTestId('link-movimento-pagante-F-aperta')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Paga/ })).toHaveLength(1);
  });
});

describe('Libro giornale → documento di origine', () => {
  const giornale = {
    totale: 2, totale_disponibile: 2, troncato: false, totale_dare: 4751.2, totale_avere: 4751.2,
    quadratura: true,
    qualita_registro: {
      registro_valido: true, scritture_sbilanciate: 0, protocolli_duplicati: 0,
      scritture_senza_protocollo: 0, righe_non_numeriche: 0, righe_senza_conto: 0,
    },
    scritture: [
      {
        id: 's1', numero_registrazione: 1, data_documento: '2026-03-10', tipo: 'fattura_acquisto',
        descrizione: 'Fattura 77/2026 - Fornitore', totale_dare: 122, totale_avere: 122,
        fonte_documento: { tipo: 'fattura', id: 'F-77', numero: '77/2026' },
        righe: [{ conto_codice: '05.01.01', conto_nome: 'Acquisto merci', dare: 100, avere: 0 }],
      },
      {
        id: 's2', numero_registrazione: 2, data_documento: '2026-03-22', tipo: 'corrispettivo',
        descrizione: 'Corrispettivo del 2026-03-22', totale_dare: 4629.2, totale_avere: 4629.2,
        fonte_documento: { tipo: 'corrispettivo', id: 'C-1', numero: null },
        righe: [{ conto_codice: '01.01.01', conto_nome: 'Cassa', dare: 4629.2, avere: 0 }],
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.includes('/libro-giornale?')) return Promise.resolve({ data: giornale });
      if (url.includes('/libro-mastro?')) return Promise.resolve({ data: { totale_conti: 0, mastrini: [] } });
      if (url.endsWith('/controllo-60-giorni')) return Promise.resolve({ data: { conforme: true } });
      return Promise.reject(new Error(`Chiamata inattesa: ${url}`));
    });
  });

  it('apre la scrittura richiesta e collega la fattura di origine', async () => {
    render(
      <MemoryRouter initialEntries={['/contabilita/giornale?scrittura=s1']}>
        <LibroGiornale />
      </MemoryRouter>,
    );

    const link = await screen.findByTestId('link-documento-s1');
    expect(link).toHaveAttribute('href', '/fatture?invoice_id=F-77');
    expect(screen.getByTestId('filtro-contropartita')).toHaveTextContent('Scrittura s1 in evidenza');
  });

  it('collega il corrispettivo di origine (XML in nuova scheda) e passa il conto al backend', async () => {
    render(
      <MemoryRouter initialEntries={['/contabilita/giornale?conto=01.01.01&data_da=2026-01-01&data_a=2026-12-31']}>
        <LibroGiornale />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByTestId('scrittura-2'));
    const link = await screen.findByTestId('link-documento-s2');
    expect(link).toHaveAttribute('href', '/api/corrispettivi/C-1/view');
    expect(link).toHaveAttribute('target', '_blank');
    expect(api.get).toHaveBeenCalledWith(
      '/api/contabilita-gestionale/libro-giornale?data_da=2026-01-01&data_a=2026-12-31&limit=2000&conto=01.01.01',
    );
    expect(screen.getByTestId('filtro-contropartita')).toHaveTextContent('Solo le scritture del conto 01.01.01');
  });
});

describe('Bilancio di verifica → libro giornale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        conti: [{
          codice: '01.01.01', nome: 'Cassa', tipo: 'attivo', codice_ufficiale: '19.03.03',
          nome_ufficiale: 'Cassa contanti', dare: 4629.2, avere: 0, saldo_dare: 4629.2, saldo_avere: 0,
          n_movimenti: 1,
        }],
        totali: { dare: 4629.2, avere: 4629.2, saldo_dare: 4629.2, saldo_avere: 4629.2, sbilancio: 0 },
        quadratura: true, stato: 'QUADRA',
        qualita_registro: {
          quadratura_totali: true, registro_valido: true, scritture_sbilanciate: 0,
          scritture_senza_righe: 0, righe_non_numeriche: 0, righe_senza_conto: 0,
        },
        completezza_registro: {
          scritture_registrate: 1, fatture_da_registrare: 0, corrispettivi_da_registrare: 0,
          documenti_da_registrare: 0, completo: true,
        },
        riepilogo: {
          n_conti: 1, n_conti_attivo: 1, n_conti_passivo: 0, n_conti_patrimonio_netto: 0,
          n_conti_ricavo: 0, n_conti_costo: 0,
        },
        data_generazione: '2026-09-03T00:00:00Z',
      },
    });
  });

  it('con ?conto= apre il gruppo, evidenzia il conto e collega il giornale di quel conto', async () => {
    render(
      <MemoryRouter initialEntries={['/contabilita/verifica?conto=19.03.03']}>
        <BilancioVerifica />
      </MemoryRouter>,
    );

    const link = await screen.findByTestId('link-giornale-01.01.01');
    expect(link).toHaveAttribute('href', '/contabilita/giornale?conto=01.01.01&data_da=2026-01-01&data_a=2026-12-31');
    expect(screen.getByTestId('conto-01.01.01')).toHaveStyle({ background: '#fdf3d7' });
    expect(screen.getByText(/CEE 19\.03\.03/)).toBeInTheDocument();
  });
});

describe('Riconciliazione banca → fattura / prima nota, F24 → quietanza / banca', () => {
  it('costruisce i link dalle contropartite reali e marca la fattura solo proposta', () => {
    const collegato = linksContropartitaMovimento({
      movimento_id: 'EC-1', tipo: 'fattura_sdd', data: '2026-02-10', importo: -31.57,
      collegamenti: { fattura_id: 'F-9', prima_nota_banca_id: 'pn-9' },
    });
    expect(collegato.map(l => [l.key, l.to, l.etichetta])).toEqual([
      ['fattura', '/fatture?invoice_id=F-9', 'Vai alla fattura'],
      ['prima-nota', '/prima-nota#sezione=banca&selected=pn-9', 'Prima Nota Banca'],
    ]);
    const proposto = linksContropartitaMovimento({
      movimento_id: 'EC-2', tipo: 'fattura_bonifico', suggerimenti: [{ id: 'F-prop', numero: '5/2026' }],
      collegamenti: { fattura_id: null, prima_nota_banca_id: null },
    });
    expect(proposto).toHaveLength(1);
    expect(proposto[0].etichetta).toBe('Fattura proposta');
    expect(linksContropartitaMovimento({ movimento_id: 'EC-3', tipo: 'stipendio' })).toEqual([]);
  });

  it('il pannello del movimento richiesto mostra i link con href attesi', () => {
    render(
      <MemoryRouter>
        <PannelloMovimentoRichiesto
          id={EC_ID}
          richiesta={{ stato: 'ok', dati: {
            movimento_id: EC_ID, data: '2026-02-17', importo: -11.68, descrizione: 'SDD AMAZON', tipo: 'fattura_sdd',
            collegamenti: { fattura_id: 'F-pag', prima_nota_banca_id: 'pn-7', riconciliato: true },
          } }}
          onChiudi={() => {}}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('link-fattura-richiesto')).toHaveAttribute('href', '/fatture?invoice_id=F-pag');
    expect(screen.getByTestId('link-prima-nota-richiesto')).toHaveAttribute('href', '/prima-nota#sezione=banca&selected=pn-7');
    expect(screen.getByTestId('movimento-richiesto')).toHaveTextContent('17-02-2026');
    expect(screen.getByTestId('movimento-richiesto')).toHaveTextContent('SDD AMAZON');
  });

  it('nella tabella F24 collega quietanza (PDF) e addebito bancario', async () => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        totale: 1, anno: 2026,
        righe: [{
          f24_id: 'f24-a', file: 'F24_gen.pdf', periodo_competenza: '01/2026', scadenza_naturale: '2026-02-16',
          data_pagamento: '2026-02-16', giorni_ritardo: 0, stato_pagamento: 'pagato_nei_termini',
          tipo_versamento: 'ordinario', causali_inps: [], codici_tributo: ['1001'],
          documento_collegato: {
            quietanza_id: 'Q-1', protocollo_quietanza: '26010112345', quietanza_fonte: 'fiscal_documents',
            quietanza_url: '/api/fiscal/documents/Q-1/content',
            movimento_bancario_id: 'EC-2026-02-16-1500.00-aa', movimenti_bancari_ids: ['EC-2026-02-16-1500.00-aa'],
            pagamento_verificato_banca: true, data_pagamento_effettivo: '2026-02-16',
          },
          possibile_duplicazione: 'no', saldo_finale: 1500, motivazione: 'pagato nei termini',
        }],
      },
    });

    render(<MemoryRouter><TabellaAnalisiF24 anno={2026} /></MemoryRouter>);
    fireEvent.click(screen.getByTestId('btn-carica-analisi-f24'));

    const quietanza = await screen.findByTestId('link-quietanza-f24-a');
    expect(quietanza).toHaveAttribute('href', '/api/fiscal/documents/Q-1/content');
    expect(quietanza).toHaveAttribute('target', '_blank');
    expect(screen.getByTestId('link-movimento-f24-f24-a'))
      .toHaveAttribute('href', '/riconciliazione/banca?movimento=EC-2026-02-16-1500.00-aa');
  });
});
