import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import { AnnoProvider, AnnoSelector, useAnnoGlobale } from './AnnoContext';

vi.mock('../api', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}));

function CurrentYear() {
  const { anno } = useAnnoGlobale();
  return <span data-testid="anno-corrente">{anno}</span>;
}

describe('AnnoContext globale', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { anno: 2026 } });
    api.put.mockResolvedValue({ data: { anno: 2025 } });
  });

  it('allinea il filtro frontend all anno operativo del backend', async () => {
    localStorage.setItem('annoGlobale', '2025');
    render(<AnnoProvider><CurrentYear /></AnnoProvider>);

    await waitFor(() => expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2026'));
    expect(api.get).toHaveBeenCalledWith('/api/config-import/anno');
    expect(localStorage.getItem('annoGlobale')).toBe('2026');
  });

  it('propaga al backend il cambio effettuato dal selettore globale', async () => {
    render(<AnnoProvider><AnnoSelector /><CurrentYear /></AnnoProvider>);
    await waitFor(() => expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2026'));

    fireEvent.change(screen.getByTestId('anno-globale-selector'), { target: { value: '2025' } });

    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/config-import/anno', { anno: 2025 }));
    expect(screen.getByTestId('anno-corrente')).toHaveTextContent('2025');
  });
});
