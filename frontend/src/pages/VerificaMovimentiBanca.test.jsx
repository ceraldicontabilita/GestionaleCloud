import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import VerificaMovimentiBanca from './VerificaMovimentiBanca';

vi.mock('../api', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}));

vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const categories = [
  {
    id: 'cedolino', label: 'Cedolino / dipendente', target_type: 'payslip',
    requires_target: true, help: 'Scegli il cedolino e il dipendente esatti.',
  },
  {
    id: 'fattura', label: 'Fornitore / fattura', target_type: 'invoice',
    requires_target: true, help: 'Scegli la fattura esatta del fornitore.',
  },
  {
    id: 'altro', label: 'Altro', target_type: null,
    requires_target: false, help: 'Descrivi la natura dell’operazione.',
  },
];

const indexResponse = {
  year: 2026,
  total_rows: 1,
  loaded_rows: 1,
  categories,
  automation: 'disabled_for_manual_index',
  rows: [{
    id: 'mov-salary', date: '2026-08-03', type: 'uscita', amount_cents: 150000,
    description: 'VOSTRA DISPOSIZIONE A FAVORE CERALDI VALERIO STIPENDIO LUGLIO 2026',
    index_status: 'da_classificare', decision: null,
  }],
};

describe('Eccezioni da riconciliare', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url.includes('/candidati?')) {
        return Promise.resolve({ data: {
          matching: 'manual_only',
          candidates: [{
            id: 'payslip-valerio', label: 'Valerio Ceraldi - 2026-07',
            date: '2026-07-31', amount_cents: 150000,
          }],
        } });
      }
      return Promise.resolve({ data: indexResponse });
    });
    api.put.mockResolvedValue({ data: { saved: true } });
  });

  it('mostra solo le eccezioni come decisioni umane e non vecchie proposte automatiche', async () => {
    render(<VerificaMovimentiBanca />);

    expect(await screen.findByText('Eccezioni da riconciliare')).toBeInTheDocument();
    expect(screen.getByText('Automatico con prova · manuale per eccezione')).toBeInTheDocument();
    expect(screen.getAllByText('Da classificare').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Collegare alla riga esistente')).not.toBeInTheDocument();
    expect(screen.queryByText(/Verificare Ricavi/i)).not.toBeInTheDocument();
  });

  it('non propone classificazione manuale per una riconciliazione gia provata da EC', async () => {
    api.get.mockResolvedValueOnce({ data: {
      ...indexResponse,
      rows: [{
        ...indexResponse.rows[0], index_status: 'riconciliato_banca', bank_reconciled: true,
        bank_evidence: { kind: 'assegno' },
      }],
    } });

    render(<VerificaMovimentiBanca />);
    fireEvent.change(screen.getByLabelText('Stato indice'), {
      target: { value: 'riconciliato_banca' },
    });

    expect(await screen.findByText('Riconciliato da EC')).toBeInTheDocument();
    expect(screen.getByText('Nessuna azione richiesta')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Classifica' })).not.toBeInTheDocument();
  });

  it('permette di scegliere cedolino e dipendente senza collegamenti automatici', async () => {
    render(<VerificaMovimentiBanca />);
    fireEvent.click(await screen.findByRole('button', { name: 'Classifica' }));
    fireEvent.click(screen.getByRole('button', { name: /Cedolino \/ dipendente/i }));

    const candidate = await screen.findByText('Valerio Ceraldi - 2026-07');
    fireEvent.click(candidate);
    fireEvent.click(screen.getByRole('button', { name: /Conferma scelta/i }));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/prima-nota/indice-operazioni/mov-salary',
      {
        category: 'cedolino',
        target_id: 'payslip-valerio',
        note: '',
        expected_version: 0,
      },
    ));
  });

  it('consente una classificazione senza bersaglio quando la natura non ha documento', async () => {
    render(<VerificaMovimentiBanca />);
    fireEvent.click(await screen.findByRole('button', { name: 'Classifica' }));
    fireEvent.click(screen.getByRole('button', { name: /^Altro/i }));
    fireEvent.change(screen.getByPlaceholderText('Scrivi qui una precisazione utile…'), {
      target: { value: 'Operazione da esaminare con il consulente' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Conferma scelta/i }));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/prima-nota/indice-operazioni/mov-salary',
      expect.objectContaining({
        category: 'altro', target_id: null,
        note: 'Operazione da esaminare con il consulente',
      }),
    ));
  });
});
