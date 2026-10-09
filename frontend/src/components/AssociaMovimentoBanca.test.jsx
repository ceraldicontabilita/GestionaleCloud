import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import AssociaMovimentoBanca from './AssociaMovimentoBanca';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const fattura = { fattura_id: 'fatt-1', fattura_numero: '12', fornitore: 'STUDIO ROSSI', importo: 1268.8 };

describe('AssociaMovimentoBanca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: {
      residuo: 1058.8,
      candidati: [
        { id: 'acconto', data: '2026-05-10', importo: -1000, descrizione: 'BONIFICO', prove: [],
          conferma: 'parziale', spiegazione: 'acconto: restano 58,80 € da pagare', quota_cents: 100000 },
        { id: 'lordo', data: '2026-05-11', importo: -1268.8, descrizione: 'BONIFICO', prove: [],
          conferma: 'eccede', spiegazione: "il movimento supera di 210,00 € il residuo della fattura (e' il totale con la ritenuta, non il netto da pagare)", quota_cents: 105880 },
      ],
    } });
    api.post.mockResolvedValue({ data: { success: true } });
  });

  it('dice perche un movimento non si puo confermare e manda la quota di un acconto', async () => {
    render(<AssociaMovimentoBanca fattura={fattura} onChiudi={vi.fn()} onAssociato={vi.fn()} />);
    expect(await screen.findByText(/da pagare al fornitore/)).toBeInTheDocument();
    expect(screen.getByTestId('esito-lordo')).toHaveTextContent('ritenuta');
    const bottoni = screen.getAllByRole('button', { name: /È questo|È un acconto/ });
    const eccede = bottoni.find(b => b.title && b.title.includes('supera'));
    expect(eccede).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'È un acconto' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/operazioni-da-confermare/smart/riconcilia-manuale',
      expect.objectContaining({ associazioni: [{ id: 'fatt-1', quota_cents: 100000 }] }),
    ));
  });
});
