import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import {
  EditorPosReale,
  ModalImportTotaliPos,
  parseTotaliPosTesto,
} from './CoerenzaPOSCorrispettivi';

vi.mock('../api', () => ({
  default: { put: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

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
