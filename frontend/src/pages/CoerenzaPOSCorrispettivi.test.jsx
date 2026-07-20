import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import {
  BadgeRiconciliatoBanca,
  EditorPosReale,
  ModalImportTotaliPos,
  calcolaSaldoXmlPos,
  formatEuroConSegno,
  parseTotaliPosTesto,
} from './CoerenzaPOSCorrispettivi';

vi.mock('../api', () => ({
  default: { put: vi.fn(), post: vi.fn() },
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
      data: '2026-07-05', pos_manuale: 0, pos_manuale_presente: false,
    }} />);

    expect(screen.getByLabelText('POS reale terminale 2026-07-05')).toHaveValue('');
    expect(screen.queryByLabelText('Salva POS reale 2026-07-05')).not.toBeInTheDocument();
  });

  it('nasconde Salva se il valore e gia persistito e lo mostra solo dopo una modifica', () => {
    render(<EditorPosReale g={{
      data: '2026-07-05', pos_manuale: 1098.40, pos_manuale_presente: true,
    }} />);

    const input = screen.getByLabelText('POS reale terminale 2026-07-05');
    expect(screen.queryByLabelText('Salva POS reale 2026-07-05')).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: '1100,00' } });
    expect(screen.getByLabelText('Salva POS reale 2026-07-05')).toBeInTheDocument();
  });

  it('salva il valore manuale senza modificare il dato XML', async () => {
    const onSaved = vi.fn();
    render(<EditorPosReale g={{
      data: '2026-07-05', pos_manuale: 1098.40, pos_manuale_presente: true,
      xml_elettronico: 1152.70,
    }} onSaved={onSaved} />);

    const input = screen.getByLabelText('POS reale terminale 2026-07-05');
    expect(input).toHaveValue('1098,40');
    fireEvent.change(input, { target: { value: '1.125,50' } });
    // Formato operativo semplice: nessun separatore migliaia nell'input.
    fireEvent.change(input, { target: { value: '1125,50' } });
    fireEvent.click(screen.getByLabelText('Salva POS reale 2026-07-05'));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pos-corrispettivi/chiusura-giornaliera',
      {
        data: '2026-07-05',
        importo: 1125.50,
        note: 'Inserimento manuale da Coerenza POS',
      },
    ));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText('Salva POS reale 2026-07-05')).not.toBeInTheDocument();
  });

  it('accetta zero come valore manuale esplicito', async () => {
    render(<EditorPosReale g={{
      data: '2026-07-06', pos_manuale: 0, pos_manuale_presente: false,
    }} />);

    fireEvent.change(screen.getByLabelText('POS reale terminale 2026-07-06'), {
      target: { value: '0,00' },
    });
    fireEvent.keyDown(screen.getByLabelText('POS reale terminale 2026-07-06'), {
      key: 'Enter', code: 'Enter',
    });

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/pos-corrispettivi/chiusura-giornaliera',
      expect.objectContaining({ data: '2026-07-06', importo: 0 }),
    ));
  });
});
