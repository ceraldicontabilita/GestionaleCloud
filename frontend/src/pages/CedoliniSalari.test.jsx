import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

  it('organizza i dati per dipendente e mantiene tutti gli anni', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.getByText('Anna Bianchi')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/prima-nota-salari/salari-ricostruiti');
    expect(screen.getByRole('heading')).toHaveTextContent('per dipendente');
  });

  it('permette di filtrare un singolo anno', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Anno cedolini'), { target: { value: '2024' } });
    expect(screen.queryByText('Mario Rossi')).not.toBeInTheDocument();
    expect(screen.getByText('Anna Bianchi')).toBeInTheDocument();
  });

  it('mantiene due cedolini distinti dello stesso mese e somma gli importi ricostruiti', async () => {
    api.get.mockResolvedValueOnce({
      data: [
        { id: 'busta-1', dipendente: 'Mario Rossi', anno: 2026, mese: 3, importo_busta: 1000 },
        { id: 'busta-2', dipendente: 'Mario Rossi', anno: 2026, mese: 3, importo_busta: 400 },
      ],
    });
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.getByText('Marzo')).toBeInTheDocument();
    const riepilogo = screen.getByText('Marzo').closest('tr');
    expect(within(riepilogo).getAllByText('€ 1.400,00')).toHaveLength(2);
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
    expect(await screen.findByText('Associazione da rivedere')).toBeInTheDocument();
    expect(screen.queryByText('Riconciliato con estratto conto')).not.toBeInTheDocument();
  });

  it('non espone un import Excel locale nella pagina di consultazione', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.queryByRole('link', { name: /Importa buste e bonifici Excel/i })).not.toBeInTheDocument();
    expect(screen.getByText(/acquisiti esclusivamente da Documenti/i)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('non espone upload del cedolino dalla pagina di consultazione', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.queryByRole('link', { name: /Importa cedolino/i })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('non espone upload del bonifico dalla pagina di consultazione', async () => {
    render(<CedoliniSalari />);
    await waitFor(() => expect(screen.getByText('Mario Rossi')).toBeInTheDocument());
    expect(screen.queryByRole('link', { name: /Importa bonifico/i })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
