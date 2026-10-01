import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import api from '../api';
import EstrattiContoOriginali from './EstrattiContoOriginali';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

describe('Estratti conto caricati', () => {
  it('elenca banca e Nexi e apre il file originale', async () => {
    api.get.mockImplementation(url => (url.endsWith('/originali')
      ? Promise.resolve({ data: { estratti: [
        { id: 'abc', nome: 'Elenco.csv', tipo: 'banca', data: '2026-09-26T21:00:00Z' },
        { id: 'nexi_statement:x', nome: 'Estratto_Conto (8).pdf', tipo: 'nexi', data: '2025-12-31', totale: 2758.32 },
      ] } })
      : new Promise(() => {})));

    render(<EstrattiContoOriginali />);
    expect(await screen.findByText('Elenco.csv')).toBeInTheDocument();
    expect(screen.getByText('Carta Nexi')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('estratto-originale-nexi_statement:x'));
    expect(api.get).toHaveBeenCalledWith(
      '/api/originale/estratto/nexi_statement%3Ax',
      expect.anything(),
    );
  });
});
