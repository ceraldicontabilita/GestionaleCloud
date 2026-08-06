import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import ImportDocumenti, { classificaEsitoUpload } from './ImportDocumenti';

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

  it('mostra come errore un workflow fallito restituito con HTTP 200', () => {
    expect(classificaEsitoUpload({
      success: false,
      message: 'Errore parsing F24',
    })).toEqual({
      status: 'error',
      message: 'Errore parsing F24',
    });
  });

  it('mantiene lo ZIP intero e lo affida ai controlli del backend', async () => {
    api.post.mockResolvedValue({
      data: {
        success: true,
        tipo_rilevato: 'archivio_zip',
        imported: 2,
        message: 'ZIP elaborato: 2 importati, 0 duplicati, 0 errori, 0 ignorati',
      },
    });
    render(<ImportDocumenti />);

    const zip = new File(['PK-test'], 'documenti.zip', { type: 'application/zip' });
    fireEvent.change(screen.getByTestId('zip-file-input'), { target: { files: [zip] } });

    expect(await screen.findByText('1 file in coda')).toBeInTheDocument();
    expect(screen.getByText('documenti.zip')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, formData] = api.post.mock.calls[0];
    expect(url).toBe('/api/documenti/upload-auto');
    expect(formData.get('file').name).toBe('documenti.zip');
    expect((await screen.findAllByText('Archivio ZIP')).length).toBeGreaterThan(0);
  });
});
