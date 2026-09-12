import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import {
  AnnoImportazioneCard,
  DriveFattureImportCard,
} from './DriveImportControls';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('Controlli import Drive in Documenti', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra stato e provenienza senza avviare import automaticamente', async () => {
    api.get.mockResolvedValue({
      data: {
        configured: true,
        folder_id: 'folder-documenti',
        last_sync: '2026-08-11T18:48:38Z',
        total_imported: 171,
      },
    });

    render(<DriveFattureImportCard />);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/fatture/drive/status')
    );
    expect(await screen.findByText('Configurato')).toBeInTheDocument();
    expect(screen.getByText('folder-documenti')).toBeInTheDocument();
    expect(screen.getByText('171')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('carica l anno operativo senza importare file automaticamente', async () => {
    api.get.mockResolvedValue({ data: { anno: 2026 } });

    render(<AnnoImportazioneCard />);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/config-import/anno'));
    expect(await screen.findByTestId('select-anno-importazione-attivo')).toHaveValue('2026');
    expect(screen.getByRole('button', { name: 'Importa 2026 da Drive' })).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('segue lo stato del job fino al risultato senza tenere aperta la richiesta', async () => {
    vi.useFakeTimers();
    api.get
      .mockResolvedValueOnce({ data: { anno: 2025 } })
      .mockResolvedValueOnce({ data: { stato: 'in_corso', anno: 2025 } })
      .mockResolvedValueOnce({
        data: { stato: 'completato', anno: 2025, risultato: {
          anno: 2025, sync_fatture: { imported: 1 },
          sync_corrispettivi: { skipped: 'non configurato' },
          promozione_archivio: { fatture_promosse: 0, corrispettivi_promossi: 0 },
        } },
      });
    api.post.mockResolvedValue({ data: { started: true, stato: 'avvio', anno: 2025 } });

    render(<AnnoImportazioneCard />);
    expect(await screen.findByRole('button', { name: 'Importa 2025 da Drive' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Importa 2025 da Drive' }));
    await act(async () => vi.advanceTimersByTimeAsync(4000));

    expect(await screen.findByTestId('esito-import-anno')).toHaveTextContent('Esito import 2025');
    expect(api.get).toHaveBeenCalledWith('/api/config-import/importa-anno/stato');
    vi.useRealTimers();
  });
});
