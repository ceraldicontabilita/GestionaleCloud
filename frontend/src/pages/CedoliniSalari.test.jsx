import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import CedoliniSalari from './CedoliniSalari';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

describe('CedoliniSalari', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: [
        { id: '1', dipendente_nome: 'Mario Rossi', anno: 2026, mese: 3, importo_busta: 1000 },
        { id: '2', dipendente_nome: 'Anna Bianchi', anno: 2024, mese: 11, importo_busta: 900 },
      ],
    });
  });

  it('carica e mostra tutti gli anni per impostazione predefinita', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.getByText('Anna Bianchi')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/prima-nota-salari/salari');
    expect(screen.getByRole('heading')).toHaveTextContent('tutti gli anni');
  });

  it('permette di filtrare un singolo anno', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Anno cedolini'), { target: { value: '2024' } });
    expect(screen.queryByText('Mario Rossi')).not.toBeInTheDocument();
    expect(screen.getByText('Anna Bianchi')).toBeInTheDocument();
  });
});
