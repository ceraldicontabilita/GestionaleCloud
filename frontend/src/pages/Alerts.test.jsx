import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';
import Alerts from './Alerts';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

describe('Lista alert operativi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        alerts: [{
          id: 'A-1', titolo: 'Fornitore da completare',
          dettaglio: 'Manca il metodo di pagamento verificato.',
          severita: 'warning', modulo: 'fornitori', link: '/fornitori?search=Alfa',
          created_at: '2026-08-23T10:00:00Z',
        }],
        stats: { totale_filtrato: 1 },
        pagination: { has_more: false },
      },
    });
  });

  it('apre il filtro esatto e spiega cosa manca e cosa fare', async () => {
    render(<MemoryRouter initialEntries={['/dashboard/alerts?modulo=fornitori']}><Alerts /></MemoryRouter>);

    expect(await screen.findByText('Modulo: fornitori')).toBeInTheDocument();
    expect(screen.getByText('Manca il metodo di pagamento verificato.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Apri il caso e verifica/i })).toHaveAttribute('href', '/fornitori?search=Alfa');
    expect(api.get).toHaveBeenCalledWith('/api/alerts/lista', expect.objectContaining({
      params: expect.objectContaining({ stato: 'aperto', modulo: 'fornitori', offset: 0, limit: 50 }),
    }));
  });

  it('pagina senza perdere i casi gia caricati', async () => {
    api.get
      .mockResolvedValueOnce({ data: { alerts: [{ id: 'A-1', titolo: 'Primo' }], stats: { totale_filtrato: 2 }, pagination: { has_more: true } } })
      .mockResolvedValueOnce({ data: { alerts: [{ id: 'A-2', titolo: 'Secondo' }], stats: { totale_filtrato: 2 }, pagination: { has_more: false } } });
    render(<MemoryRouter initialEntries={['/dashboard/alerts']}><Alerts /></MemoryRouter>);
    await screen.findByText('Primo');
    fireEvent.click(screen.getByRole('button', { name: 'Mostra altri casi' }));
    expect(await screen.findByText('Secondo')).toBeInTheDocument();
    expect(screen.getByText('Primo')).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/alerts/lista', expect.objectContaining({ params: expect.objectContaining({ offset: 1 }) })));
  });
});
