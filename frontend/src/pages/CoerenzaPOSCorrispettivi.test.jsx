import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import {
  default as CoerenzaPOSCorrispettivi,
  BadgeRiconciliatoBanca,
  EditorPosReale,
  ModalImportTotaliPos,
  calcolaSaldoXmlPos,
  formatEuroConSegno,
  parseTotaliPosTesto,
  CellaCircuito,
} from './CoerenzaPOSCorrispettivi';

vi.mock('../api', () => ({
  default: { get: vi.fn(), put: vi.fn(), post: vi.fn() },
}));

vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('Segno differenza XML meno POS reale', () => {
  it('mostra positivo quando XML e maggiore del POS reale', () => {
    expect(formatEuroConSegno(793.20 - 792.60)).toBe('€ +0,60');
  });

  it('mantiene il segno negativo quando XML non copre il POS reale', () => {
    expect(formatEuroConSegno(792.60 - 793.20)).toBe('€ -0,60');
  });

  it('somma solo i giorni confrontabili e restituisce la direzione complessiva', () => {
    expect(calcolaSaldoXmlPos([
      { pos_manuale_presente: true, stato_serale: 'ok', diff_serale: 11.89 },
      { pos_manuale_presente: true, stato_serale: 'ok', diff_serale: -3.00 },
      { pos_manuale_presente: true, stato_serale: 'in_attesa_xml', diff_serale: -100 },
      { pos_manuale_presente: false, stato_serale: 'no_dati', diff_serale: 50 },
    ])).toEqual({ saldo: 8.89, direzione: 'piu', giorni: 2 });
  });

  it('segnala complessivamente in meno senza proporre modifiche ai dati storici', () => {
    expect(calcolaSaldoXmlPos([
      { pos_manuale_presente: true, stato_serale: 'differenza_in_piu_da_registrare', diff_serale: -0.60 },
    ])).toEqual({ saldo: -0.60, direzione: 'meno', giorni: 1 });
  });
});

describe('Evidenza di riconciliazione bancaria', () => {
  it('mostra il badge soltanto quando il backend certifica il match reale', () => {
    const { rerender } = render(<BadgeRiconciliatoBanca riconciliato={false} />);
    expect(screen.queryByText('✓ Riconciliato banca')).not.toBeInTheDocument();

    rerender(<BadgeRiconciliatoBanca riconciliato />);
    expect(screen.getByText('✓ Riconciliato banca')).toBeInTheDocument();
  });
});

describe('Importazione massiva POS', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.post.mockResolvedValue({ data: { salvati: 2, errori: 0 } });
  });

  it('legge date e importi con virgola senza accettare duplicati', () => {
    expect(parseTotaliPosTesto('2026-07-01;1685,80\n2026-07-02;1666.90')).toEqual([
      { data: '2026-07-01', importo: 1685.80 },
      { data: '2026-07-02', importo: 1666.90 },
    ]);
    expect(() => parseTotaliPosTesto('2026-07-01;1\n2026-07-01;2')).toThrow('Data duplicata');
  });

  it('invia tutte le giornate in una sola richiesta autenticata', async () => {
    const onSaved = vi.fn();
    render(<ModalImportTotaliPos onClose={vi.fn()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText('Totali POS giornalieri'), {
      target: { value: '2026-07-01;1685,80\n2026-07-02;1666,90' },
    });
    fireEvent.click(screen.getByLabelText('Conferma importazione POS'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/pos-corrispettivi/chiusure-giornaliere/batch',
      {
        righe: [
          { data: '2026-07-01', importo: 1685.80 },
          { data: '2026-07-02', importo: 1666.90 },
        ],
        note: 'Import Numia: solo acquisti approvati',
      },
    ));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});

describe('Editor POS reale del terminale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.put.mockResolvedValue({ data: { message: 'salvato' } });
  });

  it('parte vuoto quando il POS manuale non e ancora stato inserito', () => {
    render(<EditorPosReale g={{
      data: '2026-07-05', pos_per_circuito: { numia: null },
    }} />);

    expect(screen.getByLabelText('POS NUMIA reale 2026-07-05')).toHaveValue('');
    expect(screen.queryByLabelText('Salva POS NUMIA 2026-07-05')).not.toBeInTheDocument();
  });

  it('nasconde Salva se il valore e gia persistito e lo mostra solo dopo una modifica', () => {
    render(<EditorPosReale g={{
      data: '2026-07-05', pos_per_circuito: { numia: 1098.40 },
    }} />);

    const input = screen.getByLabelText('POS NUMIA reale 2026-07-05');
    expect(screen.queryByLabelText('Salva POS NUMIA 2026-07-05')).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: '1100,00' } });
    expect(screen.getByLabelText('Salva POS NUMIA 2026-07-05')).toBeInTheDocument();
  });

  it('salva il valore manuale senza modificare il dato XML', async () => {
    const onSaved = vi.fn();
    render(<EditorPosReale g={{
      data: '2026-07-05', pos_per_circuito: { numia: 1098.40 },
      xml_elettronico: 1152.70,
    }} onSaved={onSaved} />);

    const input = screen.getByLabelText('POS NUMIA reale 2026-07-05');
    expect(input).toHaveValue('1098,40');
    fireEvent.change(input, { target: { value: '1.125,50' } });
    // Formato operativo semplice: nessun separatore migliaia nell'input.
    fireEvent.change(input, { target: { value: '1125,50' } });
    fireEvent.click(screen.getByLabelText('Salva POS NUMIA 2026-07-05'));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pos-corrispettivi/chiusura-giornaliera',
      {
        data: '2026-07-05',
        importo: 1125.50,
        gestore: 'numia',
        note: 'Inserimento manuale NUMIA da Coerenza POS',
      },
    ));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText('Salva POS NUMIA 2026-07-05')).not.toBeInTheDocument();
  });

  it('accetta zero come valore manuale esplicito', async () => {
    render(<EditorPosReale g={{
      data: '2026-07-06', pos_per_circuito: { numia: null },
    }} />);

    fireEvent.change(screen.getByLabelText('POS NUMIA reale 2026-07-06'), {
      target: { value: '0,00' },
    });
    fireEvent.keyDown(screen.getByLabelText('POS NUMIA reale 2026-07-06'), {
      key: 'Enter', code: 'Enter',
    });

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pos-corrispettivi/chiusura-giornaliera',
      expect.objectContaining({ data: '2026-07-06', importo: 0 }),
    ));
  });
});

describe('Vista canonica POS e banca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.includes('/verifica-coerenza')) {
        return Promise.resolve({ data: {
          riepilogo: {}, riepilogo_giornaliero: [], anomalie: [], anomalie_count: 0,
        } });
      }
      if (url.includes('/riepilogo-mensile')) {
        return Promise.resolve({ data: {
          mesi: [{
            mese: 7, nome: 'Lug', totale_corrispettivi: 150,
            contanti: 45, elettronico_xml: 105, pos_terminale: 100,
            differenza_xml_pos: 5, pos_accreditato: 100,
            differenza_pos_banca: 0, stato: 'ok',
          }],
          totali: {
            elettronico_xml: 105, pos_terminale: 100,
            differenza_xml_pos: 5, pos_accreditato: 100,
            differenza_pos_banca: 0,
          },
        } });
      }
      return Promise.resolve({ data: {
        statistiche: {
          fase2_ok: 1, fase2_pos_totale: 100, fase2_accrediti_totale: 100,
          fase2_saldo_finale: 0, fase2_movimenti_banca: 1,
          fase2_movimenti_banca_raw: 3, fase2_duplicati_banca_unificati: 2,
        },
        giorni: [], riepilogo_settimanale: [],
      } });
    });
  });

  it('espone le fonti duplicate unificate e le due differenze mensili', async () => {
    render(<CoerenzaPOSCorrispettivi />);

    expect(await screen.findByText(/Fonti bancarie duplicate unificate:/)).toHaveTextContent('2');
    fireEvent.click(screen.getByRole('button', { name: 'Mensile' }));

    expect(screen.getByText('POS TERMINALE')).toBeInTheDocument();
    expect(screen.getByText('DIFF. XML−POS')).toBeInTheDocument();
    expect(screen.getByText('ACCREDITO BANCA')).toBeInTheDocument();
    expect(screen.getByText('DIFF. BANCA−POS')).toBeInTheDocument();
  });

  it('apre dai contatori la lista esatta dei giorni con problemi', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/verifica-coerenza')) return Promise.resolve({ data: {
        riepilogo: {}, riepilogo_giornaliero: [], anomalie: [], anomalie_count: 0,
      } });
      if (url.includes('/riepilogo-mensile')) return Promise.resolve({ data: { mesi: [], totali: {} } });
      if (url.includes('/sumup/')) return Promise.resolve({ data: { configured: false } });
      return Promise.resolve({ data: {
        statistiche: { fase2_ok: 1, fase2_mancante: 1, fase2_saldo_finale: -25 },
        giorni: [
          { data: '2026-08-01', stato_serale: 'ok', stato_accredito: 'ok', stato_corrispettivo: 'ok', pos_manuale_presente: true },
          { data: '2026-08-02', stato_serale: 'ok', stato_accredito: 'mancante', stato_corrispettivo: 'ok', pos_manuale_presente: true },
        ],
        riepilogo_settimanale: [],
      } });
    });
    window.HTMLElement.prototype.scrollIntoView = vi.fn();

    render(<CoerenzaPOSCorrispettivi />);

    expect(await screen.findByRole('button', { name: /XML mancanti/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Accrediti circuito mancanti/ })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /Saldo da verificare/ }));
    expect(await screen.findByText('1 / 2 giorni')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Solo problemi' })).toHaveStyle({ background: '#0f2744' });
    await waitFor(() => expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled());
  });
});

describe('CellaCircuito', () => {
  // Un circuito che non ha risposto non vale zero: mostrarlo come 0,00
  // affermerebbe che quel terminale non ha incassato, che e' un'altra cosa.
  const rendi = (posPerCircuito, circuito) =>
    render(
      <table><tbody><tr>
        <CellaCircuito g={{ pos_per_circuito: posPerCircuito }} circuito={circuito} />
      </tr></tbody></table>
    );

  it('mostra l\'importo del circuito quando il dato c\'e\'', () => {
    rendi({ numia: 500, sumup: 100 }, 'sumup');
    expect(screen.getByText(/100/)).toBeInTheDocument();
  });

  it('mostra la fonte reale del circuito', () => {
    render(
      <table><tbody><tr>
        <CellaCircuito
          g={{
            pos_per_circuito: { numia: 867.30 },
            fonte_pos_per_circuito: { numia: 'estratto_conto_numia' },
          }}
          circuito="numia"
        />
      </tr></tbody></table>
    );
    expect(screen.getByText('Estratto BPM')).toBeInTheDocument();
  });

  it('distingue lo zero dichiarato dal dato mancante', () => {
    const { unmount } = rendi({ numia: 500, sumup: 0 }, 'sumup');
    expect(screen.getByText(/0,00/)).toBeInTheDocument();
    expect(screen.queryByText('in attesa')).toBeNull();
    unmount();

    rendi({ numia: 500, sumup: null }, 'sumup');
    expect(screen.getByText('in attesa')).toBeInTheDocument();
  });

  it('non esplode se il dettaglio per circuito non arriva', () => {
    render(
      <table><tbody><tr>
        <CellaCircuito g={{}} circuito="numia" />
      </tr></tbody></table>
    );
    expect(screen.getByText('in attesa')).toBeInTheDocument();
  });
});
