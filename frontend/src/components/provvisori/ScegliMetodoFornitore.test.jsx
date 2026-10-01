import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../../api';
import ScegliMetodoFornitore from './ScegliMetodoFornitore';

vi.mock('../../api', () => ({ default: { post: vi.fn() } }));

const fattura = { fattura_id: 'a', fornitore: 'F.LLI SOMMELLA', fattura_numero: '880', importo: 7.95, fornitore_piva: 'IT111' };
const altre = [
  { fattura_id: 'b', importo: 10, fornitore_piva: 'IT111' },
  { fattura_id: 'c', importo: 20, fornitore_piva: 'IT111' },
];

describe('ScegliMetodoFornitore', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('imposta il metodo del fornitore e manda anche le altre fatture nella stessa Prima Nota', async () => {
    api.post.mockResolvedValue({ data: { message: 'ok', esiti: [], scartate: 0 } });
    const onFatto = vi.fn();
    render(<ScegliMetodoFornitore fattura={fattura} altre={altre} onClose={() => {}} onFatto={onFatto} />);

    expect(screen.getByText(/Come hai pagato F.LLI SOMMELLA/)).toBeInTheDocument();
    expect(screen.getByText(/le altre/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /Banca/ }));
    fireEvent.click(screen.getByRole('button', { name: /Attendi banca \(3\)/ }));

    await waitFor(() => expect(onFatto).toHaveBeenCalled());
    expect(api.post).toHaveBeenCalledWith('/api/prima-nota/provvisori/imposta-metodo-fornitore', {
      fattura_id: 'a', metodo: 'banca', altre_fattura_ids: ['b', 'c'],
    });
  });

  it('senza la spunta sulle altre, sposta solo questa fattura', async () => {
    api.post.mockResolvedValue({ data: {} });
    render(<ScegliMetodoFornitore fattura={fattura} altre={altre} onClose={() => {}} onFatto={() => {}} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Registra in Cassa' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toEqual({ fattura_id: 'a', metodo: 'cassa', altre_fattura_ids: [] });
  });

  it('un metodo gia\' diverso non si cambia di nascosto: lo dice e chiede il cambio', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: "Il fornitore ha gia' il metodo «bonifico»: per cambiarlo conferma." } } });
    api.post.mockResolvedValueOnce({ data: {} });
    const onFatto = vi.fn();
    render(<ScegliMetodoFornitore fattura={fattura} altre={[]} onClose={() => {}} onFatto={onFatto} />);
    fireEvent.click(screen.getByRole('button', { name: 'Registra in Cassa' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cambia il metodo del fornitore' }));
    await waitFor(() => expect(onFatto).toHaveBeenCalled());
    expect(api.post.mock.calls[1][1]).toMatchObject({ cambia_metodo: true });
  });
});
