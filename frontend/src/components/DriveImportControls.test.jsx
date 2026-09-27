import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('legge la cartella unica e dice quanti file restano, senza avviare import', async () => {
    api.get.mockResolvedValue({
      data: {
        attiva: true,
        giro_in_corso: false,
        ultimo_giro: {
          updated_at: '2026-09-26T23:48:14Z',
          last_result: { letti: 50, elaborati: 50, errori: 0, doppioni_cestinati: 0, restanti: 186 },
        },
        registro: { ELABORATE: 2215, ERRORI: 68 },
      },
    });

    render(<DriveFattureImportCard />);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/documenti/cartella-unica/stato')
    );
    expect(await screen.findByText('Attiva')).toBeInTheDocument();
    expect(screen.getByText('186')).toBeInTheDocument();
    expect(screen.getByText(/2215 file elaborati in tutto/)).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/api/fatture/drive/status');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('importa tutto: svuota la cartella e poi dice cosa resta', async () => {
    api.get
      .mockResolvedValueOnce({ data: { attiva: true, giro_in_corso: false, ultimo_giro: {}, registro: {} } })
      .mockResolvedValue({ data: {
        attiva: true, giro_in_corso: false,
        ultimo_giro: { last_result: { elaborati: 36, errori: 0, restanti: 0 } }, registro: {},
      } });
    api.post.mockResolvedValue({ data: { avviato: true, tutto: true } });

    // Il componente aspetta 5 secondi veri prima di rileggere lo stato: con
    // l'orologio finto il test non dipende dalla lentezza del runner della CI.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<DriveFattureImportCard />);
      // Finche' lo stato non e' caricato il pulsante e' disabilitato: sul
      // runner lento della CI il clic arrivava prima e andava perso.
      const pulsante = await screen.findByRole('button', { name: 'Importa tutto da Drive' });
      await waitFor(() => expect(pulsante).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(pulsante);

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/documenti/cartella-unica/giro?tutto=true'),
      { timeout: 5000 });
      await vi.advanceTimersByTimeAsync(5000);
      expect(await screen.findByText(/In cartella restano 0 file/, {}, { timeout: 5000 }))
        .toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  }, 15000);

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
    api.get
      .mockResolvedValueOnce({ data: { anno: 2025 } })
      .mockResolvedValueOnce({
        data: { stato: 'completato', anno: 2025, risultato: {
          anno: 2025, drive: { elaborati: 1, errori: 0, restanti: 0 },
          promozione_archivio: { fatture_promosse: 0, corrispettivi_promossi: 0 },
        } },
      });
    api.post.mockResolvedValue({ data: { started: true, stato: 'avvio', anno: 2025 } });

    render(<AnnoImportazioneCard />);
    expect(await screen.findByRole('button', { name: 'Importa 2025 da Drive' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Importa 2025 da Drive' }));

    expect(await screen.findByTestId('esito-import-anno', {}, { timeout: 4000 }))
      .toHaveTextContent('Esito import 2025');
    expect(api.get).toHaveBeenCalledWith('/api/config-import/importa-anno/stato');
  });
});
