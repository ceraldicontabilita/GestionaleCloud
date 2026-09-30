import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import { AnnoProvider } from '../contexts/AnnoContext';
import F24Scheda from './F24Scheda';
import TributoCodice, { righeIncrocio } from './TributoCodice';
import CedolinoScheda from './CedolinoScheda';
import ProtocolloScheda from './ProtocolloScheda';
import LegacyRouteResolver from './LegacyRouteResolver';
import { STATO_PROTOCOLLO } from '../lib/protocolloVista';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
// Il visualizzatore vero scarica il blob: qui basta sapere QUALE indirizzo apre.
vi.mock('../components/DocumentViewerModal', () => ({
  default: ({ fetchUrl, title, onClose }) => (
    <div data-testid="viewer-finto" data-url={fetchUrl}>{title}<button onClick={onClose}>chiudi</button></div>
  ),
}));

const montato = (percorso, path, elemento) => render(
  <AnnoProvider>
    <MemoryRouter initialEntries={[percorso]}>
      <Routes><Route path={path} element={elemento} /></Routes>
    </MemoryRouter>
  </AnnoProvider>,
);

const riga = (n, extra = {}) => ({
  id: `Q1:${n}`, document_id: 'Q1', ordinal: n, payment_year: '2026', payment_date: '2026-04-16',
  section: 'ERARIO', tax_code: n === 1 ? '1040' : '6003', description: 'Descrizione', reference_period: '03/2026',
  debit_amount: n === 1 ? 700 : 300, credit_amount: 0, protocol: '26041535212746370', filename: 'q.pdf',
  evidence_state: 'QUIETANZA_DOCUMENTALE_NON_PROVA_BANCARIA', pdf_url: null, ...extra,
});

beforeEach(() => {
  vi.clearAllMocks();
  window.innerWidth = 1400;
  localStorage.setItem('annoGlobale', '2026');
});

describe('Scheda F24 /fiscale/f24/:id', () => {
  const rispondi = ({ riscontro, quietanza = { canale: 'posta' } } = {}) => api.get.mockImplementation(url => {
    if (url.startsWith('/api/fiscal/f24-rows')) return Promise.resolve({ data: { items: [riga(1), riga(2)] } });
    if (url.startsWith('/api/f24/quietanze/')) return Promise.resolve({ data: quietanza });
    if (url.startsWith('/api/f24-riconciliazione/quietanze-banca')) {
      return Promise.resolve({ data: riscontro || { riscontrati: [] } });
    }
    return Promise.reject(new Error(`url inattesa ${url}`));
  });

  it('mostra righe, canale e saldo; l importo versato apre la quietanza', async () => {
    rispondi();
    montato('/fiscale/f24/Q1', '/fiscale/f24/:id', <F24Scheda />);
    expect(await screen.findByTestId('f24-righe-tabella')).toBeInTheDocument();
    expect(screen.getByText('Quietanza F24 del 16/04/2026')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('f24-canale')).toHaveTextContent('Posta'));
    // le righe portano al tributo canonico
    expect(screen.getAllByRole('link', { name: '1040' })[0]).toHaveAttribute('href', '/fiscale/tributi/1040');
    const apri = screen.getByTestId('f24-apri-originale');
    expect(apri).toHaveTextContent(/Importo versato .*1\.000,00/);
    fireEvent.click(apri);
    expect(screen.getByTestId('viewer-finto')).toHaveAttribute('data-url', '/api/f24-public/pdf/Q1');
  });

  it('il riscontro con la banca porta livello e motivazione', async () => {
    rispondi({ riscontro: { riscontrati: [
      { chiave: 'k1', livello: 'CERTO', data: '2026-04-16', importo: 1000, motivazione: 'importo uguale al centesimo',
        quietanze: [{ id: 'Q1' }], addebito: { link: '/riconciliazione/banca?movimento=m1', data: '2026-04-16' } },
      { chiave: 'k2', livello: 'CERTO', data: '2026-05-16', importo: 50, quietanze: [{ id: 'ALTRA' }] },
    ] } });
    montato('/fiscale/f24/Q1', '/fiscale/f24/:id', <F24Scheda />);
    const righe = await screen.findAllByTestId('riscontro-riga');
    expect(righe).toHaveLength(1);
    expect(righe[0]).toHaveTextContent('Certo');
    expect(righe[0]).toHaveTextContent('importo uguale al centesimo');
  });

  it('senza riscontro lo dice, e se la lettura fallisce la scheda resta', async () => {
    api.get.mockImplementation(url => {
      if (url.startsWith('/api/fiscal/f24-rows')) return Promise.resolve({ data: { items: [riga(1)] } });
      if (url.startsWith('/api/f24/quietanze/')) return Promise.resolve({ data: {} });
      return Promise.reject(new Error('banca giu'));
    });
    montato('/fiscale/f24/Q1', '/fiscale/f24/:id', <F24Scheda />);
    expect(await screen.findByTestId('riscontro-errore')).toHaveTextContent('Riscontro bancario non disponibile');
    expect(screen.getByTestId('f24-righe')).toBeInTheDocument();
    // il canale che non c'e non e zero ne vuoto
    expect(screen.getByTestId('f24-canale')).toHaveTextContent('Dato non disponibile');
  });

  it('un F24 sconosciuto non e una pagina vuota', async () => {
    api.get.mockResolvedValue({ data: { items: [] } });
    montato('/fiscale/f24/nessuno', '/fiscale/f24/:id', <F24Scheda />);
    expect(await screen.findByTestId('f24-non-trovato')).toBeInTheDocument();
  });

  it('su telefono le righe sono card e la legenda e in pagina', async () => {
    window.innerWidth = 390;
    rispondi();
    montato('/fiscale/f24/Q1', '/fiscale/f24/:id', <F24Scheda />);
    expect(await screen.findByTestId('f24-righe-card')).toBeInTheDocument();
    expect(screen.queryByTestId('f24-righe-tabella')).toBeNull();
    expect(screen.getByTestId('legenda-f24')).toHaveTextContent('Probabile');
  });
});

describe('Vista tributo /fiscale/tributi/:codice', () => {
  const voce = (extra = {}) => ({
    chiave: 'erario|6003|2026|3', codice: '6003', descrizione: 'IVA marzo', anno: 2026, mese: 3, periodo: '03/2026',
    inviato_cents: 0, quietanza_cents: 120000, ravvedimento_cents: 0, credito_cents: 0, residuo_cents: 0,
    stato: 'PAGATO', stato_label: 'Pagato (quietanza)', ultimo_pagamento: '2026-04-16',
    documenti: [{ tipo: 'quietanza', data: '2026-04-16', protocollo: 'P1', pdf_url: '/api/f24-public/pdf/Q9', importo_cents: 120000 }],
    ...extra,
  });
  const incroci = {
    confronti_iva_mensile: [
      { lipe_id: 'l3', codice_tributo: '6003', anno: 2026, mese: 3, mese_nome: 'Marzo', dovuto_da_lipe: 1200, versato_f24: 1200,
        differenza: 0, stato: 'OK', nota: null, f24_versamenti: [{ id: 'Q9', quietanza: true, importo: 1200, data_versamento: '2026-04-16', protocollo: 'P1', periodo: '03/2026' }] },
      { lipe_id: 'l4', codice_tributo: '6004', anno: 2026, mese: 4, mese_nome: 'Aprile', dovuto_da_lipe: 500, versato_f24: 0,
        differenza: 500, stato: 'MANCANTE', f24_versamenti: [] },
    ],
    irap_riscontro: [], iva_annuale_riscontro: [],
  };
  const rispondi = () => api.get.mockImplementation(url => {
    if (url.startsWith('/api/f24/tributi')) return Promise.resolve({ data: { voci: [voce(), voce({ chiave: 'x', codice: '60031', periodo: 'altro' })] } });
    if (url.startsWith('/api/fiscale/incroci')) return Promise.resolve({ data: incroci });
    return Promise.reject(new Error(`url inattesa ${url}`));
  });

  it('usa l anno globale e tiene solo il codice richiesto', async () => {
    rispondi();
    montato('/fiscale/tributi/6003', '/fiscale/tributi/:codice', <TributoCodice />);
    expect(await screen.findByTestId('tributo-tabella')).toBeInTheDocument();
    const chiamata = api.get.mock.calls.find(([u]) => u.startsWith('/api/f24/tributi'))[0];
    expect(chiamata).toContain('anno=2026');
    expect(chiamata).toContain('cerca=6003');
    // "60031" contiene "6003" ma non e lo stesso codice
    expect(screen.getAllByTestId(/^riga-/)).toHaveLength(1);
    expect(screen.getByTestId('filtro-anno-vista')).toHaveTextContent('Anno 2026');
  });

  it('«Tutti gli anni» toglie il limite e resta nell indirizzo', async () => {
    rispondi();
    montato('/fiscale/tributi/6003', '/fiscale/tributi/:codice', <TributoCodice />);
    await screen.findByTestId('tributo-tabella');
    fireEvent.click(screen.getByRole('button', { name: 'Tutti gli anni' }));
    await waitFor(() => {
      const ultime = api.get.mock.calls.filter(([u]) => u.startsWith('/api/f24/tributi')).pop()[0];
      expect(ultime).not.toContain('anno=');
    });
  });

  it('l importo versato apre la quietanza e porta alla scheda F24', async () => {
    rispondi();
    montato('/fiscale/tributi/6003', '/fiscale/tributi/:codice', <TributoCodice />);
    const apri = await screen.findByTestId('apri-quietanza-erario|6003|2026|3');
    expect(apri).toHaveTextContent('1.200,00');
    fireEvent.click(apri);
    expect(screen.getByTestId('viewer-finto')).toHaveAttribute('data-url', '/api/f24-public/pdf/Q9');
    expect(screen.getByTestId('scheda-f24-erario|6003|2026|3')).toHaveAttribute('href', '/fiscale/f24/Q9');
  });

  it('IVA mensile: incrocio con la LIPE, con lo stato in parole e il versamento apribile', async () => {
    rispondi();
    montato('/fiscale/tributi/6003', '/fiscale/tributi/:codice', <TributoCodice />);
    const blocco = await screen.findByTestId('incroci-righe');
    expect(blocco).toHaveTextContent('Marzo 2026');
    expect(blocco).toHaveTextContent('Torna');
    expect(blocco).not.toHaveTextContent('Aprile');
    fireEvent.click(screen.getByTestId('apri-versamento-Q9'));
    expect(screen.getByTestId('viewer-finto')).toHaveAttribute('data-url', '/api/f24-public/pdf/Q9');
  });

  it('codice senza pagamenti: messaggio con la via d uscita, non una tabella vuota', async () => {
    api.get.mockResolvedValue({ data: { voci: [] } });
    montato('/fiscale/tributi/9999', '/fiscale/tributi/:codice', <TributoCodice />);
    expect(await screen.findByTestId('tributo-vuoto')).toHaveTextContent('Tutti gli anni');
    expect(screen.queryByTestId('tributo-incroci')).toBeNull();
  });

  it('righeIncrocio: IRAP 3800 e IVA annuale 6099 hanno la stessa forma', () => {
    const dati = {
      irap_riscontro: [{ codice_tributo: '3800', anno_imposta: 2024, document_id: 'd1', rigo: 'IR26', importo_dichiarato: 5164, importo_versato: 0, differenza: 5164, stato: 'MANCANTE', f24_versamenti: [] }],
      iva_annuale_riscontro: [{ codice_tributo: '6099', anno_imposta: 2024, document_id: 'd2', rigo: 'VX1', importo_dichiarato: 0, importo_versato: 0, differenza: 0, stato: 'OK', f24_versamenti: [] }],
      confronti_iva_mensile: [],
    };
    expect(righeIncrocio(dati, '3800')[0]).toMatchObject({ periodo: "Anno d'imposta 2024", stato: 'MANCANTE', dovuto: 5164 });
    expect(righeIncrocio(dati, '6099')).toHaveLength(1);
    expect(righeIncrocio(dati, '1040')).toEqual([]);
  });
});

describe('Scheda busta paga /personale/cedolini/:id', () => {
  const busta = (extra = {}) => ({
    id: 'c1', dipendente: 'ROSSI MARIO', periodo: 'Giugno 2025', tipo: 'mensile', canale: 'drive', netto: 1500,
    netto_fonte: 'cella', lordo: 2000, totale_trattenute: 500, pagato: false, sostituito: false, filename: 'rossi.pdf',
    versione: { variante: 2, stampa_di_controllo: false, rettificato: true, n_versioni_totali: 2, versioni_scartate: [],
      storico_netto: [{ prima: 1400, dopo: 1500, at: '2025-07-02T10:00:00+00:00' }], da_decidere: false },
    versioni_gruppo: [
      { id: 'c0', netto: 1400, stampa_di_controllo: true, variante: null, filename: 'bozza.pdf', corrente: false },
      { id: 'c1', netto: 1500, stampa_di_controllo: false, variante: 2, filename: 'rossi.pdf', corrente: true },
    ],
    decisione: { esito: 'vincitore', motivo: 'la busta definitiva batte la stampa di controllo', vincitore: 'c1' },
    pdf_disponibile: true, pdf_url: '/api/cedolini/c1/pdf', ...extra,
  });

  it('mostra netto, fonte, canale, versione e apre l originale', async () => {
    api.get.mockResolvedValue({ data: busta() });
    montato('/personale/cedolini/c1', '/personale/cedolini/:id', <CedolinoScheda />);
    expect(await screen.findByTestId('cedolino-scheda')).toBeInTheDocument();
    expect(screen.getByTestId('cedolino-canale')).toHaveTextContent('Drive');
    expect(screen.getByTestId('cedolino-netto-fonte')).toHaveTextContent('Letto dalla cella del netto');
    expect(screen.getByTestId('cedolino-variante')).toHaveTextContent('Variante 2');
    expect(screen.getByTestId('cedolino-decisione')).toHaveTextContent('la busta definitiva batte la stampa di controllo');
    expect(screen.getAllByTestId('cedolino-versione')).toHaveLength(2);
    expect(screen.getByTestId('cedolino-storico')).toHaveTextContent('02/07/2025');
    fireEvent.click(screen.getByTestId('cedolino-apri-originale'));
    expect(screen.getByTestId('viewer-finto')).toHaveAttribute('data-url', '/api/cedolini/c1/pdf');
  });

  it('netto assente = Dato non disponibile, mai zero; senza PDF lo dice', async () => {
    api.get.mockResolvedValue({ data: busta({ netto: null, lordo: null, totale_trattenute: null, netto_fonte: 'non_letto_da_lul',
      canale: null, pdf_disponibile: false, pdf_url: null, versioni_gruppo: [], decisione: null,
      versione: { variante: null, stampa_di_controllo: false, rettificato: false, n_versioni_totali: null, storico_netto: [] } }) });
    montato('/personale/cedolini/c1', '/personale/cedolini/:id', <CedolinoScheda />);
    const scheda = await screen.findByTestId('cedolino-scheda');
    expect(screen.getAllByText('Dato non disponibile').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId('cedolino-netto-fonte')).toHaveTextContent('senza cella del netto');
    expect(scheda).not.toHaveTextContent('0,00');
    expect(screen.getByTestId('cedolino-apri-originale-assente')).toHaveTextContent('Originale non disponibile');
  });

  it('busta sostituita: si vede, con il motivo nelle versioni', async () => {
    api.get.mockResolvedValue({ data: busta({ sostituito: true }) });
    montato('/personale/cedolini/c1', '/personale/cedolini/:id', <CedolinoScheda />);
    expect(await screen.findByTestId('badge-sostituita')).toHaveTextContent('Sostituita');
  });

  it('404 = busta non trovata', async () => {
    api.get.mockRejectedValue({ response: { status: 404 } });
    montato('/personale/cedolini/zz', '/personale/cedolini/:id', <CedolinoScheda />);
    expect(await screen.findByTestId('cedolino-non-trovato')).toBeInTheDocument();
  });
});

describe('Scheda protocollo /protocollo/:id', () => {
  const scheda = (extra = {}) => ({
    numero: '2023/000123', data_protocollo: '2023-05-04', data_documento: null, tipo_documento: 'TARI',
    direzione: 'ENTRATA', controparte: 'Comune di Napoli', pratica: null, importo: 210.5, nome_file: 'tari.pdf',
    canale: 'drive', ambito: 'personale_familiare', accounting_excluded: true, stato: 'attivo', oggetto: 'Avviso TARI 2023',
    collegati: { sola_lettura: true, escluso_dalla_contabilita: true, documenti: [] }, ...extra,
  });

  it('legge la scheda dell API di MINI-07 con anno e progressivo interi', async () => {
    api.get.mockResolvedValue({ data: scheda() });
    montato('/protocollo/2023/000123', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    const corpo = await screen.findByTestId('protocollo-scheda');
    expect(api.get).toHaveBeenCalledWith('/api/protocollo-personale/2023/123');
    expect(corpo).toHaveTextContent('2023/000123');
    expect(corpo).toHaveTextContent('04/05/2023');
    expect(corpo).toHaveTextContent('210,50');
    // la data del documento non c'e: non e zero e non e vuota
    expect(corpo).toHaveTextContent('Dato non disponibile');
    expect(screen.getByTestId('protocollo-ambito')).toHaveTextContent('fuori dai conti');
    expect(screen.getByTestId('protocollo-nessun-collegato')).toBeInTheDocument();
    expect(screen.getByTestId('legenda-protocollo')).toHaveTextContent('non entrano mai nei conti');
  });

  it('anche con l id in un solo segmento (/protocollo/2023%2F000123)', async () => {
    api.get.mockResolvedValue({ data: scheda() });
    montato('/protocollo/2023%2F000123', '/protocollo/:id', <ProtocolloScheda />);
    await screen.findByTestId('protocollo-scheda');
    expect(api.get).toHaveBeenCalledWith('/api/protocollo-personale/2023/123');
  });

  it('i documenti collegati portano alla sezione esistente, senza copiare dati', async () => {
    api.get.mockResolvedValue({ data: scheda({ collegati: { sola_lettura: true, documenti: [
      { tipo: 'Verbale', collezione: 'verbali_noleggio', id: 'v1', rotta: '/verbali-noleggio/V1', via: 'impronta_sha256' },
    ] } }) });
    montato('/protocollo/2023/000123', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    const collegato = await screen.findByTestId('protocollo-collegato');
    expect(collegato).toHaveTextContent('Verbale');
    expect(screen.getByRole('link', { name: 'Apri nella sua sezione' })).toHaveAttribute('href', '/verbali-noleggio/V1');
  });

  it('un protocollo rimosso si vede, con il motivo', async () => {
    api.get.mockResolvedValue({ data: scheda({ stato: 'rimosso', rimosso_motivo: 'duplicato del 2023/000122' }) });
    montato('/protocollo/2023/000123', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    expect(await screen.findByText("Rimosso dall'archivio")).toBeInTheDocument();
    expect(screen.getByText(/duplicato del 2023\/000122/)).toBeInTheDocument();
  });

  it('numero non valido: non trovato, senza chiamare la rete', async () => {
    montato('/protocollo/COLLAUDO', '/protocollo/:id', <ProtocolloScheda />);
    expect(await screen.findByTestId('protocollo-non-trovato')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('404 con codice NON_TROVATO = non trovato; 404 senza codice (API non montata) = non disponibile', async () => {
    api.get.mockRejectedValueOnce({ response: { status: 404, data: { detail: { code: 'NON_TROVATO' } } } });
    const prima = montato('/protocollo/2023/000999', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    expect(await screen.findByTestId('protocollo-non-trovato')).toBeInTheDocument();
    prima.unmount();
    api.get.mockRejectedValueOnce({ response: { status: 404, data: { detail: 'Not Found' } } });
    montato('/protocollo/2023/000998', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    expect(await screen.findByTestId('protocollo-non-disponibile')).toBeInTheDocument();
  });

  it('un errore del server ha parole', async () => {
    api.get.mockRejectedValue({ response: { status: 500, data: { detail: { message: 'database occupato' } } } });
    montato('/protocollo/2023/000123', '/protocollo/:anno/:progressivo', <ProtocolloScheda />);
    expect(await screen.findByTestId('protocollo-errore')).toHaveTextContent('database occupato');
  });

  it('la lettura si puo sostituire (carica)', async () => {
    const carica = vi.fn().mockResolvedValue({ stato: STATO_PROTOCOLLO.NON_TROVATO });
    montato('/protocollo/2023/000001', '/protocollo/:anno/:progressivo', <ProtocolloScheda carica={carica} />);
    await screen.findByTestId('protocollo-non-trovato');
    expect(carica).toHaveBeenCalledWith('2023/000001');
  });
});

describe('Vecchi indirizzi', () => {
  const Dove = () => <div data-testid="dove">{useLocation().pathname + useLocation().search}</div>;
  const vai = percorso => render(
    <MemoryRouter initialEntries={[percorso]}>
      <Routes>
        <Route path="/fiscale/*" element={<Dove />} />
        <Route path="/personale/*" element={<Dove />} />
        <Route path="/tributi" element={<Dove />} />
        <Route path="*" element={<LegacyRouteResolver />} />
      </Routes>
    </MemoryRouter>,
  );

  it.each([
    ['/f24/abc', '/fiscale/f24/abc'],
    ['/tributi/1040?anno=tutti', '/fiscale/tributi/1040?anno=tutti'],
    ['/cedolini/c9', '/personale/cedolini/c9'],
  ])('%s rimanda a %s', async (vecchio, nuovo) => {
    vai(vecchio);
    expect((await screen.findByTestId('dove')).textContent).toBe(nuovo);
  });

  it('/fiscale/tributi nudo torna alla pagina Tributi', async () => {
    render(
      <MemoryRouter initialEntries={['/fiscale/tributi']}>
        <Routes>
          <Route path="/tributi" element={<Dove />} />
          <Route path="*" element={<LegacyRouteResolver />} />
        </Routes>
      </MemoryRouter>,
    );
    expect((await screen.findByTestId('dove')).textContent).toBe('/tributi');
  });
});
