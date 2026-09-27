import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Pianificazione, { ordinaEventiRecentiPrima } from './Pianificazione';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const eventi = [
  { id: 'vecchio', title: 'Riunione di gennaio', scheduled_date: '2026-01-10T09:00:00', event_type: 'meeting', status: 'scheduled' },
  { id: 'nuovo', title: 'Scadenza di settembre', scheduled_date: '2026-09-20T09:00:00', event_type: 'deadline', status: 'scheduled' },
  { id: 'medio', title: 'Promemoria di maggio', scheduled_date: '2026-05-05T09:00:00', event_type: 'reminder', status: 'scheduled' },
];

describe('Pianificazione', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('mostra prima gli eventi piu recenti', async () => {
    expect(ordinaEventiRecentiPrima(eventi).map(e => e.id)).toEqual(['nuovo', 'medio', 'vecchio']);

    api.get.mockResolvedValue({ data: eventi });
    render(<Pianificazione />);

    const primo = await screen.findByText(/Scadenza di settembre/);
    const tutti = screen.getAllByText(/di (settembre|maggio|gennaio)/);
    expect(tutti[0]).toBe(primo);
    expect(tutti[2]).toHaveTextContent('Riunione di gennaio');
  });

  it('un errore di caricamento non e un agenda vuota', async () => {
    api.get.mockRejectedValue(new Error('servizio non disponibile'));
    render(<Pianificazione />);

    const errore = await screen.findByTestId('pianificazione-errore');
    expect(errore).toHaveTextContent('servizio non disponibile');
    expect(within(errore).getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
    expect(screen.queryByText('Nessun evento in agenda')).not.toBeInTheDocument();
  });
});
