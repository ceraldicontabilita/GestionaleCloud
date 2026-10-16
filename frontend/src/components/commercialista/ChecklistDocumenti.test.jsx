import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../../api';
import ChecklistDocumenti from './ChecklistDocumenti.jsx';

vi.mock('../../api', () => ({ default: { get: vi.fn() } }));

const periodo = { valido: true, anno: 2026, meseRotta: 0, dal: '2026-01-01', al: '2026-12-31' };
const risposta = {
  aggiornato_il: '2026-10-16T10:00:00Z',
  riepilogo: { dato_esistente: 1, dato_incompleto: 1, dato_mancante: 1 },
  items: [
    { key: 'f24', richiesto: 'F24, ricevute e quietanze', domanda: 'Sono presenti?', stato: 'dato_incompleto', risposta: 'Dato incompleto.', fonti: [{ etichetta: 'Gestionale', conteggio: 2 }], parti: { presenti: 1, totali: 2 }, nota: 'Prove distinte.', route: '/f24' },
    { key: 'lipe', richiesto: 'LIPE', domanda: 'È presente?', stato: 'dato_esistente', risposta: 'Dato esistente.', fonti: [] },
    { key: 'cu', richiesto: 'CU', domanda: 'È presente?', stato: 'dato_mancante', risposta: 'Dato non trovato.', fonti: [] },
  ],
};

describe('Checklist documenti del commercialista', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.get.mockResolvedValue({ data: risposta });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('mostra stati e aggiorna automaticamente la stessa fonte', async () => {
    render(<ChecklistDocumenti periodo={periodo} />);
    await waitFor(() => expect(screen.getByText('F24, ricevute e quietanze')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/api/commercialista/checklist-documenti/2026/0?dal=2026-01-01&al=2026-12-31');
    expect(screen.getByText('DATO INCOMPLETO')).toBeInTheDocument();

    await act(async () => { vi.advanceTimersByTime(60_000); });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it('filtra solo i dati mancanti', async () => {
    render(<ChecklistDocumenti periodo={periodo} />);
    await waitFor(() => screen.getByText('CU'));
    fireEvent.click(screen.getByRole('button', { name: 'Mancanti' }));
    expect(screen.getByText('CU')).toBeInTheDocument();
    expect(screen.queryByText('LIPE')).not.toBeInTheDocument();
  });
});
