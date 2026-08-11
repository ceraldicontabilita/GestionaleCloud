import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
});
