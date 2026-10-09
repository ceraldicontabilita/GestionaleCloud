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
      overview: { total: 197, counts: { verbali: 132, tributi_locali: 7, riscossione: 31, personale: 27, famiglia: 0 }, requires_review: 2 },
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
      overview: { total: 197, counts: { verbali: 132, tributi_locali: 7, riscossione: 31, personale: 27, famiglia: 1 }, requires_review: 2 },
    } });

    render(<AttiAmministrativi />);
    fireEvent.click(await screen.findByRole('button', { name: /TARI/i }));

    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/documenti/amministrativi', {
      params: { limit: 500, area: 'tributi_locali' },
    }));
    expect(screen.getByText(/Nessun risultato per i filtri selezionati/)).toBeInTheDocument();
  });

  it('apre Personale Famiglia e mostra l esclusione contabile', async () => {
    api.get.mockResolvedValueOnce({ data: {
      total: 0, counts: {}, requires_review: 0, items: [],
      overview: { total: 174, counts: { verbali: 132, tributi_locali: 6, riscossione: 8, personale: 27, famiglia: 1 }, requires_review: 5 },
    } }).mockResolvedValueOnce({ data: {
      total: 1, counts: { famiglia: 1 }, requires_review: 0,
      overview: { total: 174, counts: { verbali: 132, tributi_locali: 6, riscossione: 8, personale: 27, famiglia: 1 }, requires_review: 5 },
      items: [{
        id: 'DOC-D3ED', administrative_area: 'famiglia', filename: 'DOC_20240600051909_20240719_171752.pdf',
        category_label: 'TARI', status: 'CARICATO_UNICO', accounting_excluded: true,
        source_context: { archive_path: 'TRIBUTI LOCALI/TARI/2025/documento.pdf' },
        parsed_metadata: { contribuente: 'Ceraldi Antonietta', codice_contribuente: '1804135', anno_tributo: '2024', immobile: 'Via Cavallerizza 46, Napoli' },
      }],
    } });

    render(<AttiAmministrativi />);
    fireEvent.click(await screen.findByRole('button', { name: /Personale \/ Famiglia/i }));

    expect(await screen.findByText('Ceraldi Antonietta')).toBeInTheDocument();
    expect(screen.getByText('Escluso dalla contabilità aziendale')).toBeInTheDocument();
    expect(screen.getByText(/non entrano in bilanci, costi aziendali, Prima Nota o riconciliazioni/)).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/documenti/amministrativi', {
      params: { limit: 500, area: 'famiglia' },
    }));
  });
});
