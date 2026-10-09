import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '../../api';
import CarnetAssegni from './CarnetAssegni';

vi.mock('../../api', () => ({ default: { get: vi.fn() } }));

const CARNET = [
  {
    carnet_id: '0208770361', primo: '0208770361', ultimo: '0208770370', in_archivio: 9,
    mancanti: ['0208770370'], stati: { incassato: 9 }, ultima_data: '2025-11-14',
  },
  {
    carnet_id: '0208769071', primo: '0208769071', ultimo: '0208769080', in_archivio: 10,
    mancanti: [], stati: { incassato: 10 }, ultima_data: '2025-05-02',
  },
];

describe('CarnetAssegni', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.get.mockResolvedValue({ data: { carnet: CARNET, totale: 2 } });
  });

  it('mostra un carnet per riga, coi numeri mancanti e la data gg/mm/aaaa', async () => {
    render(<CarnetAssegni />);
    await waitFor(() => expect(screen.getByTestId('carnet-assegni')).toBeTruthy());
    expect(api.get).toHaveBeenCalledWith('/api/assegni/carnet');
    expect(screen.getByText('0208770361 – 370')).toBeTruthy();
    expect(screen.getByText('9/10')).toBeTruthy();
    expect(screen.getByText('370')).toBeTruthy();
    expect(screen.getByText('14/11/2025')).toBeTruthy();
  });

  it('il filtro tiene solo i carnet con numeri mancanti', async () => {
    render(<CarnetAssegni />);
    await waitFor(() => expect(screen.getByTestId('carnet-assegni')).toBeTruthy());
    fireEvent.click(screen.getByText('Con numeri mancanti'));
    expect(screen.queryByText('0208769071 – 080')).toBeNull();
    expect(screen.getByText('0208770361 – 370')).toBeTruthy();
  });

  it('un errore di caricamento si vede e si può riprovare', async () => {
    api.get.mockRejectedValueOnce(new Error('rete giù'));
    render(<CarnetAssegni />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText(/rete giù/)).toBeTruthy();
  });
});
