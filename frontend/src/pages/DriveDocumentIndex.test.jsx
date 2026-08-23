import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

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
  const renderIndex = (route = '/documenti/drive') => render(
    <MemoryRouter initialEntries={[route]}><DriveDocumentIndex /></MemoryRouter>
  );
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
    renderIndex();
    expect(await screen.findByText('Verifica booleana: TUTTO VERO')).toBeInTheDocument();
    expect(screen.getByText('941')).toBeInTheDocument();
    expect(screen.getByText('1297')).toBeInTheDocument();
    expect(screen.getByText('Il modello F24 non equivale al pagamento bancario.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('naviga ai documenti F24 mantenendo distinta la prova bancaria', async () => {
    renderIndex();
    await screen.findByText('Verifica booleana: TUTTO VERO');
    fireEvent.click(screen.getByRole('button', { name: /F24 e tributi/i }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/documenti/drive/index/f24', expect.any(Object)
    ));
    expect(await screen.findByText('f24.pdf')).toBeInTheDocument();
    expect(screen.getByText(/pagamento bancario non confermato/i)).toBeInTheDocument();
  });

  it('apre dai contatori la lista esatta dei casi', async () => {
    renderIndex();
    await screen.findByText('Verifica booleana: TUTTO VERO');

    fireEvent.click(screen.getByRole('button', { name: 'Apri 1297 righe tributo' }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/documenti/drive/index/f24', expect.any(Object)
    ));
    expect(await screen.findByText('f24.pdf')).toBeInTheDocument();
  });

  it('mostra un errore esplicito quando l archivio Drive non e configurato', async () => {
    api.get.mockRejectedValueOnce({ response: { data: { detail: 'Indice Drive non configurato' } } });
    renderIndex();
    expect(await screen.findByRole('alert')).toHaveTextContent('Indice Drive non configurato');
  });

  it('apre una cartella cliccata come indice tabellare leggibile', async () => {
    api.get.mockImplementation(url => {
      if (url.endsWith('/status')) return Promise.resolve({ data: { documents: 1, validation } });
      if (url.endsWith('/overview')) return Promise.resolve({ data: { validation } });
      if (url.endsWith('/search')) return Promise.resolve({ data: { results: [{
        document_id: 'DOC-A', subject: 'Pane Giuseppina', year: '2023',
        display_title: 'Domanda Rottamazione-quater', document_type_label: 'Definizione agevolata AdeR',
        filename: 'PNAGPP58D48F839K_R-DA-2023.pdf', summary: 'Richiesta presentata ad AdeR',
        status: 'VERIFICATO', drive_path: 'CARTELLE ESATTORIALI/file.pdf',
      }] } });
      return Promise.resolve({ data: { results: [] } });
    });
    renderIndex('/documenti/drive?folder=CARTELLE%20ESATTORIALI');
    expect(await screen.findByText(/Contenuto cartella:/)).toBeInTheDocument();
    expect(await screen.findByText('Pane Giuseppina')).toBeInTheDocument();
    expect(screen.getByText('Domanda Rottamazione-quater')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Correggi / associa' })).toBeInTheDocument();
  });
});
