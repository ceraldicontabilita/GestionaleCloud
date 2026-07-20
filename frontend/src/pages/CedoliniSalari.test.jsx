import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import CedoliniSalari from './CedoliniSalari';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

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

  it('non presenta come riconciliata una vecchia associazione da rivedere', async () => {
    api.get.mockResolvedValueOnce({
      data: [{
        id: 'legacy', dipendente_nome: 'Mario Rossi', anno: 2026, mese: 3,
        importo_busta: 1000, importo_bonifico: 900,
        riconciliato: false, riconciliazione_precedente_da_rivedere: true,
      }],
    });
    render(<CedoliniSalari />);
    expect(await screen.findByText('Associazione precedente da rivedere')).toBeInTheDocument();
    expect(screen.queryByText('Riconciliato con estratto conto')).not.toBeInTheDocument();
  });

  it('importa il foglio bonifici e ricarica le righe', async () => {
    api.post.mockResolvedValueOnce({ data: { created: 2, duplicates: 1 } });
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    const file = new File(['excel sintetico'], 'bonifici.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    fireEvent.change(screen.getByLabelText('Importa buste e bonifici Excel'), {
      target: { files: [file] },
    });

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][0]).toBe('/api/prima-nota-salari/import-bonifici');
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });
});
