import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import DriveDocumentIndex from './DriveDocumentIndex';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const validation = {
  all_true: true,
  counts: { documents: 941, f24_documents: 320, f24_rows: 1297, declarations: 60 },
  checks: {
    document_ids_unique: true,
    document_hashes_unique: true,
    drive_paths_unique: true,
    all_f24_documents_exist: true,
    all_f24_sha_match_document: true,
    all_f24_paths_match_document: true,
    f24_amounts_nonnegative: true,
    all_declarations_link_exactly_one_document: true,
  },
};

describe('Indice documentale Drive', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(url => {
      if (url.endsWith('/status')) return Promise.resolve({ data: { documents: 941, validation } });
      if (url.endsWith('/overview')) return Promise.resolve({ data: { validation } });
      if (url.endsWith('/f24')) return Promise.resolve({ data: { results: [{
        document: { document_id: 'DOC-1', filename: 'f24.pdf' },
        payment_year: '2026', payment_date: '16/03/2026', protocol: 'P1',
        tax_rows: 2, tax_codes: ['1001'], total_debit: 100, total_credit: 0,
        evidence_state: 'MODELLO_F24_NON_PROVA_BANCARIA',
      }] } });
      return Promise.resolve({ data: { results: [] } });
    });
  });

  it('mostra la quadratura booleana e non importa dati', async () => {
    render(<DriveDocumentIndex />);
    expect(await screen.findByText('Verifica booleana: TUTTO VERO')).toBeInTheDocument();
    expect(screen.getByText('941')).toBeInTheDocument();
    expect(screen.getByText('1297')).toBeInTheDocument();
    expect(screen.getByText('Il modello F24 non equivale al pagamento bancario.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('naviga ai documenti F24 mantenendo distinta la prova bancaria', async () => {
    render(<DriveDocumentIndex />);
    await screen.findByText('Verifica booleana: TUTTO VERO');
    fireEvent.click(screen.getByRole('button', { name: /F24 e tributi/i }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/documenti/drive/index/f24', expect.any(Object)
    ));
    expect(await screen.findByText('f24.pdf')).toBeInTheDocument();
    expect(screen.getByText(/pagamento bancario non confermato/i)).toBeInTheDocument();
  });
});
