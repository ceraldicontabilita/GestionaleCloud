import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AttiAmministrativi from './AttiAmministrativi';
import api from '../api';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));

describe('AttiAmministrativi', () => {
  it('separa prova documentale, pagamento e stato del rapporto', async () => {
    api.get.mockResolvedValueOnce({ data: {
      total: 1,
      counts: { verbali: 0, tributi_locali: 0, riscossione: 0, personale: 1 },
      requires_review: 0,
      overview: { total: 197, counts: { verbali: 132, tributi_locali: 7, riscossione: 31, personale: 27 }, requires_review: 2 },
      items: [{
        id: 'doc-1', category: 'dimissioni_telematiche', category_label: 'Modulo dimissioni telematiche',
        administrative_area: 'personale', filename: 'RSSMRA_Dimissione.pdf', status: 'da_verificare',
        source_context: { archive_path: '01_DOCUMENTI_PDF/dimissioni/RSSMRA_Dimissione.pdf' },
        parsed_metadata: { lavoratore_cf: 'RSSMRA80A01F839X', data_decorrenza_recesso: '2026-07-01', codice_modulo: '12345678901234567' },
      }],
    } });

    render(<AttiAmministrativi />);
    expect(await screen.findByText('RSSMRA80A01F839X')).toBeInTheDocument();
    expect(screen.getByText(/Nessuno di questi documenti prova da solo il pagamento/)).toBeInTheDocument();
    expect(screen.getByText(/decorrenza 2026-07-01/)).toBeInTheDocument();
    expect(screen.getByText('197')).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/documenti/amministrativi', {
      params: { limit: 500 },
    }));
  });

  it('apre la sezione dedicata dalla card senza mantenere filtri incompatibili', async () => {
    api.get.mockResolvedValue({ data: {
      total: 0, counts: {}, requires_review: 0, items: [],
      overview: { total: 197, counts: { verbali: 132, tributi_locali: 7, riscossione: 31, personale: 27 }, requires_review: 2 },
    } });

    render(<AttiAmministrativi />);
    fireEvent.click(await screen.findByRole('button', { name: /TARI/i }));

    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/documenti/amministrativi', {
      params: { limit: 500, area: 'tributi_locali' },
    }));
    expect(screen.getByText(/Nessun risultato per i filtri selezionati/)).toBeInTheDocument();
  });
});
