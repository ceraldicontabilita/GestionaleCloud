import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DoppioniFornitori from './DoppioniFornitori';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./ui/ConfirmDialog', () => ({ useConfirm: () => vi.fn().mockResolvedValue(true) }));

const gruppo = {
  motivo: 'Nome solo simile, non uguale: serve conferma.',
  fornitori: [
    { id: 366, nome: 'ENOTECA CONTE S.R.L.', partita_iva: null, codice_fiscale: null, usi: 0 },
    { id: 88, nome: 'ENOTECA DANTE S.R.L.', partita_iva: '07024451218', codice_fiscale: null, usi: 4 },
  ],
};

describe('DoppioniFornitori', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('non compare se l’elenco e’ riservato (403)', async () => {
    api.get.mockRejectedValue({ response: { status: 403 } });
    const { container } = render(<DoppioniFornitori />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="doppioni-fornitori"]')).toBeNull();
  });

  it('elenca i candidati con il motivo e unisce solo dopo la scelta', async () => {
    api.get.mockResolvedValue({ data: { count: 1, gruppi: [gruppo] } });
    api.post.mockResolvedValue({ data: { success: true } });
    const onMerged = vi.fn();
    render(<DoppioniFornitori onMerged={onMerged} />);
    fireEvent.click(await screen.findByTestId('doppioni-fornitori-toggle'));
    expect(screen.getByText(/Nome solo simile/)).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByText('Tieni questo')[1]);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/suppliers/duplicati/merge', {
        target_id: '88',
        duplicate_id: '366',
      })
    );
    await waitFor(() => expect(onMerged).toHaveBeenCalled());
  });
});
