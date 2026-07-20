import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import { EditorPosReale } from './CoerenzaPOSCorrispettivi';

vi.mock('../api', () => ({
  default: { put: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

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
