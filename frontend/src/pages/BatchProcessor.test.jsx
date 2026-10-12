import React from 'react';
import { render, act, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import api from '../api';
import BatchProcessor from './BatchProcessor';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

describe('Elaborazione batch', () => {
  it('avvia solo il recupero esplicito dal 2003', async () => {
    api.get.mockResolvedValue({ data: { historical: null } });
    api.post.mockResolvedValue({ data: {} });
    const view = render(<MemoryRouter><BatchProcessor /></MemoryRouter>);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Avvia recupero storico' })); });
    expect(api.post).toHaveBeenCalledWith('/api/email-download/start-full-download?data_inizio=2003-01-01');
    expect(api.post).toHaveBeenCalledTimes(1);
    view.unmount();
    vi.clearAllMocks();
  });
  it('consente la ripresa esplicita con lo stesso cursore dopo un riavvio', async () => {
    api.get.mockResolvedValue({ data: { historical: { in_progress: true, richiesto_dal: '2003-01-01' } } });
    api.post.mockResolvedValue({ data: {} });
    const view = render(<MemoryRouter><BatchProcessor /></MemoryRouter>);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Riprendi recupero storico' })); });
    expect(api.post).toHaveBeenCalledWith('/api/email-download/start-full-download?data_inizio=2003-01-01');
    view.unmount();
    vi.clearAllMocks();
  });
  it('aprire la pagina non avvia job o scritture' , async () => {
    vi.useFakeTimers();
    const view = render(<MemoryRouter><BatchProcessor /></MemoryRouter>);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(api.post).not.toHaveBeenCalled();
    view.unmount();
    vi.useRealTimers();
  });
});
