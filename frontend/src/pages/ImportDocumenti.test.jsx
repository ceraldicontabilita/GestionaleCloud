import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ImportDocumenti from './ImportDocumenti';

vi.mock('../api', () => ({ default: { post: vi.fn() } }));

describe('Import documenti - corrispettivo duplicato', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('non presenta come importato un duplicato restituito con HTTP 200', async () => {
    api.post.mockResolvedValue({
      data: {
        success: false,
        duplicate: true,
        action: 'duplicate',
        imported: 0,
        tipo_rilevato: 'corrispettivo',
        message: 'Corrispettivo duplicato ignorato: 2026-07-06 — totale 2006.30€',
      },
    });

    render(<ImportDocumenti />);

    const xml = new File(['<Corrispettivi/>'], 'corrispettivo-test.xml', {
      type: 'application/xml',
    });
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [xml] } });
    fireEvent.click(await screen.findByTestId('upload-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Nessun nuovo documento: duplicati ignorati')).toBeInTheDocument();
    expect(screen.getByText(/Corrispettivo duplicato ignorato: 2026-07-06/)).toBeInTheDocument();
    expect(screen.queryByText('Import completato!')).not.toBeInTheDocument();
  });
});
